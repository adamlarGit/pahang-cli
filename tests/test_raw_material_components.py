"""Unit tests for RawMaterialFilter and RawMaterialTransformer stage components."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import CameraConfig, ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.testsheet.models import PhotoRange, SubstationTestsheetPackage
from src.workflows.raw_material import (
    CopyInstruction,
    ExtractInstruction,
    ExtractedPackageData,
    RawMaterialExtractor,
    RawMaterialFilter,
    RawMaterialLoader,
    RawMaterialTransformer,
    TransformationPlan,
)


@pytest.fixture
def mock_env(tmp_path: Path) -> ProjectEnvironment:
    meta = ProjectMetadata(
        key="pahang_2026",
        name="Pahang 2026 Test",
        po_number="PO42289580",
        state="Pahang",
        voltage_type="11kV",
        year="2026",
        cycle="2",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    return ProjectEnvironment(metadata=meta, storage=storage)


def test_filter_extract_photo_number_diverse_patterns() -> None:
    filter_stage = RawMaterialFilter()

    # Standard patterns
    assert filter_stage.extract_photo_number("FLIR0123.jpg", "FLIR") == 123
    assert filter_stage.extract_photo_number("FLIR0010.jpg", "FLIR") == 10
    assert filter_stage.extract_photo_number("IMG_0100.jpg", "IMG_") == 100
    assert filter_stage.extract_photo_number("IMG_0100.jpg", "IMG") == 100

    # Date-stamped filenames (YYYYMMDD sequence)
    assert filter_stage.extract_photo_number("IMG_20260724_0042.jpg", "IMG") == 42
    assert filter_stage.extract_photo_number("IMG_20260724_0042.jpg", "IMG_") == 42
    assert filter_stage.extract_photo_number("FLIR_20260515_0007.jpg", "FLIR_") == 7

    # Prefix mismatches and non-digit filenames
    assert filter_stage.extract_photo_number("IMG_0100.jpg", "FLIR") is None
    assert filter_stage.extract_photo_number("FLIR.jpg", "FLIR") is None


def test_filter_matching_photos_success_and_warnings() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    photos = [
        Path("/tmp/FLIR0010.jpg"),
        Path("/tmp/FLIR0011.jpg"),
        Path("/tmp/FLIR0050.jpg"),
    ]
    photo_range = PhotoRange(start_num=10, end_num=12)

    matched = filter_stage.filter_matching_photos(
        photos=photos,
        prefix="FLIR",
        photo_range=photo_range,
        tech_name="IR",
        substation_folder_name="001",
        warnings=warnings,
    )

    assert len(matched) == 2
    assert matched[0] == (Path("/tmp/FLIR0010.jpg"), 10)
    assert matched[1] == (Path("/tmp/FLIR0011.jpg"), 11)
    # Missing FLIR0012 should produce warning
    assert any("IR photo FLIR0012 missing for PE 001" in w for w in warnings)


def test_filter_matching_photos_reversed_range() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    photos = [Path("/tmp/IMG_0105.jpg")]
    photo_range = PhotoRange(start_num=110, end_num=100)

    matched = filter_stage.filter_matching_photos(
        photos=photos,
        prefix="IMG_",
        photo_range=photo_range,
        tech_name="DG",
        substation_folder_name="002",
        warnings=warnings,
    )

    assert len(matched) == 1
    assert matched[0] == (Path("/tmp/IMG_0105.jpg"), 105)


def test_filter_matching_photos_invalid_range_warnings() -> None:
    filter_stage = RawMaterialFilter()

    # None range
    warnings_none: list[str] = []
    filter_stage.filter_matching_photos(
        photos=[Path("/tmp/FLIR0001.jpg")],
        prefix="FLIR",
        photo_range=None,
        tech_name="IR",
        substation_folder_name="003",
        warnings=warnings_none,
    )
    assert "IR photo range not specified or incomplete." in warnings_none[0]

    # No photo matches
    warnings_empty: list[str] = []
    photo_range = PhotoRange(start_num=10, end_num=12)
    filter_stage.filter_matching_photos(
        photos=[Path("/tmp/FLIR0099.jpg")],
        prefix="FLIR",
        photo_range=photo_range,
        tech_name="IR",
        substation_folder_name="003",
        warnings=warnings_empty,
    )
    assert "No IR photos matched range [10-12]" in warnings_empty[0]


def test_filter_verify_pe_alignment() -> None:
    filter_stage = RawMaterialFilter()

    pkg = SubstationTestsheetPackage(
        substation_number=1,
        station="RAUB",
        month="01. MAY",
        date_str="01-05-2026",
        testsheet_path=Path("/tmp/001.xlsx"),
        unsorted_raw_data_dir=Path("/tmp/UNSORTED RAW DATA"),
    )

    # Valid alignment
    existing_tuples = {("001", "01-05-2026")}
    filter_stage.verify_pe_alignment([pkg], existing_tuples)

    # Missing alignment
    with pytest.raises(RuntimeError, match="TOTAL PE.xlsx alignment pre-check failed"):
        filter_stage.verify_pe_alignment([pkg], {("002", "01-05-2026")})


def test_transformer_build_plan(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    transformer = RawMaterialTransformer()

    pkg = SubstationTestsheetPackage(
        substation_number=5,
        station="RAUB",
        month="05. MAY",
        date_str="15-05-2026",
        testsheet_path=tmp_path / "005. SSU CHEROH.xlsx",
        unsorted_raw_data_dir=tmp_path / "UNSORTED RAW DATA",
    )

    filtered_ir = [(tmp_path / "FLIR0010.jpg", 10)]
    filtered_dg = [(tmp_path / "IMG_20260724_0042.jpg", 42)]

    plan = transformer.build_plan(
        environment=mock_env,
        package=pkg,
        filtered_ir=filtered_ir,
        filtered_dg=filtered_dg,
    )

    assert plan.substation_folder_name == "005"
    assert plan.ir_count == 1
    assert plan.dg_count == 1

    expected_base = mock_env.storage.get_raw_material_dir() / "RAUB" / "05. MAY" / "15-05-2026" / "005" / "RAW DATA"
    assert expected_base / "IR" in plan.directories_to_create
    assert expected_base / "DG" in plan.directories_to_create
    assert expected_base / "US+TEV" in plan.directories_to_create

    assert len(plan.copy_instructions) == 2
    ir_inst = [i for i in plan.copy_instructions if i.tech_name == "IR"][0]
    assert ir_inst.dest_path == expected_base / "IR" / "FLIR0010.jpg"
    assert ir_inst.photo_number == 10

    dg_inst = [i for i in plan.copy_instructions if i.tech_name == "DG"][0]
    assert dg_inst.dest_path == expected_base / "DG" / "IMG_20260724_0042.jpg"
    assert dg_inst.photo_number == 42


def test_filter_ir_photos_dual_pair_mode() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []
    cam_cfg = CameraConfig(
        ir_mode="dual_pair",
        ir_prefix="IR_",
        dc_prefix="DC_",
        dc_offset=1,
        dg_prefix="IMG_",
    )

    photos = [
        Path("/tmp/IR_0001.jpg"),
        Path("/tmp/DC_0002.jpg"),
        Path("/tmp/IR_0002.jpg"),
        Path("/tmp/DC_0003.jpg"),
        Path("/tmp/IR_0099.jpg"),
        Path("/tmp/DC_0100.jpg"),
    ]
    photo_range = PhotoRange(start_num=1, end_num=2)

    matched = filter_stage.filter_ir_photos(
        photos=photos,
        camera_config=cam_cfg,
        photo_range=photo_range,
        substation_folder_name="001",
        warnings=warnings,
    )

    assert len(matched) == 4
    matched_paths = [p for p, _ in matched]
    assert Path("/tmp/IR_0001.jpg") in matched_paths
    assert Path("/tmp/DC_0002.jpg") in matched_paths
    assert Path("/tmp/IR_0002.jpg") in matched_paths
    assert Path("/tmp/DC_0003.jpg") in matched_paths
    assert len(warnings) == 0


def test_filter_ir_photos_dual_pair_missing_warning() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []
    cam_cfg = CameraConfig(
        ir_mode="dual_pair",
        ir_prefix="IR_",
        dc_prefix="DC_",
        dc_offset=1,
    )

    # Missing DC_0002 for IR 1, and missing IR 2 entirely
    photos = [
        Path("/tmp/IR_0001.jpg"),
    ]
    photo_range = PhotoRange(start_num=1, end_num=2)

    matched = filter_stage.filter_ir_photos(
        photos=photos,
        camera_config=cam_cfg,
        photo_range=photo_range,
        substation_folder_name="001",
        warnings=warnings,
    )

    assert len(matched) == 1
    assert any("IR photo for number 2 (IR_2*)" in w or "IR_0002" in w or "missing" in w.lower() for w in warnings)


def test_filter_dg_photos_p_series_and_custom_prefix() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []
    cam_cfg = CameraConfig(dg_prefix="P")

    photos = [
        Path("/tmp/P1000042.JPG"),
        Path("/tmp/P1000043.JPG"),
        Path("/tmp/P1000099.JPG"),
    ]
    photo_range = PhotoRange(start_num=42, end_num=43)

    matched = filter_stage.filter_dg_photos(
        photos=photos,
        camera_config=cam_cfg,
        photo_range=photo_range,
        substation_folder_name="001",
        warnings=warnings,
    )

    assert len(matched) == 2
    matched_paths = [p for p, _ in matched]
    assert Path("/tmp/P1000042.JPG") in matched_paths
    assert Path("/tmp/P1000043.JPG") in matched_paths
    assert len(warnings) == 0


def test_extractor_scans_us_tev_archives(tmp_path: Path) -> None:
    extractor = RawMaterialExtractor()
    unsorted_dir = tmp_path / "UNSORTED RAW DATA"
    us_tev_dir = unsorted_dir / "US+TEV"
    us_tev_dir.mkdir(parents=True)

    zip_file = us_tev_dir / "20260815T094744_083-MEDAN-WARISAN-2.zip"
    zip_file.touch()

    pkg = SubstationTestsheetPackage(
        substation_number=83,
        station="KUANTAN",
        month="01. AUGUST",
        date_str="15-08-2026",
        testsheet_path=tmp_path / "083. MEDAN WARISAN 2.xlsx",
        unsorted_raw_data_dir=unsorted_dir,
    )

    warnings: list[str] = []
    extracted = extractor.extract_package_data(pkg, warnings)

    assert hasattr(extracted, "us_tev_archives")
    assert zip_file in extracted.us_tev_archives


def test_filter_us_tev_archive_success_matching() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    archives = [
        Path("/tmp/20260815T094744_083-MEDAN-WARISAN-2.zip"),
        Path("/tmp/20260815T100204_084-MEDAN-WARISAN-1.zip"),
        Path("/tmp/20260815T120154_089-UIA.zip"),
    ]

    matched_83 = filter_stage.filter_us_tev_archive(archives, 83, warnings)
    assert matched_83 == Path("/tmp/20260815T094744_083-MEDAN-WARISAN-2.zip")

    matched_89 = filter_stage.filter_us_tev_archive(archives, 89, warnings)
    assert matched_89 == Path("/tmp/20260815T120154_089-UIA.zip")
    assert len(warnings) == 0


def test_filter_us_tev_archive_ignores_archive_suffix() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    archives = [
        Path("/tmp/20260804T092211_001_KG-RPS-ASLI-BILUT.zip"),
        Path("/tmp/20260804T092211_KG-RPS-ASLI-BILUT_Archive.zip"),
    ]

    matched = filter_stage.filter_us_tev_archive(archives, 1, warnings)
    assert matched == Path("/tmp/20260804T092211_001_KG-RPS-ASLI-BILUT.zip")
    assert len(warnings) == 0


def test_filter_us_tev_archive_cardinality_failure() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    archives = [
        Path("/tmp/20260804T092211_001_KG-RPS-ASLI-BILUT.zip"),
        Path("/tmp/20260804T092211_001_KG-RPS-ASLI-BILUT_EXTRA.zip"),
    ]

    with pytest.raises(RuntimeError, match="Multiple US\\+TEV archives matched PE 001"):
        filter_stage.filter_us_tev_archive(archives, 1, warnings)


def test_filter_us_tev_archive_missing_resilience_warning() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    archives = [
        Path("/tmp/20260815T094744_083-MEDAN-WARISAN-2.zip"),
    ]

    matched = filter_stage.filter_us_tev_archive(archives, 88, warnings)
    assert matched is None
    assert any("No US+TEV archive found" in w and "088" in w for w in warnings)


def test_transformer_build_plan_with_us_tev(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    transformer = RawMaterialTransformer()

    pkg = SubstationTestsheetPackage(
        substation_number=83,
        station="KUANTAN",
        month="01. AUGUST",
        date_str="15-08-2026",
        testsheet_path=tmp_path / "083. MEDAN WARISAN 2.xlsx",
        unsorted_raw_data_dir=tmp_path / "UNSORTED RAW DATA",
    )

    filtered_ir = [(tmp_path / "FLIR0010.jpg", 10)]
    filtered_dg = [(tmp_path / "IMG_0100.jpg", 100)]
    matched_us_tev = tmp_path / "20260815T094744_083-MEDAN-WARISAN-2.zip"

    plan = transformer.build_plan(
        environment=mock_env,
        package=pkg,
        filtered_ir=filtered_ir,
        filtered_dg=filtered_dg,
        matched_us_tev=matched_us_tev,
    )

    assert plan.us_tev_count == 1
    assert len(plan.extract_instructions) == 1
    extract_inst = plan.extract_instructions[0]
    assert extract_inst.source_archive == matched_us_tev
    expected_dest = mock_env.storage.get_raw_material_dir() / "KUANTAN" / "01. AUGUST" / "15-08-2026" / "083" / "RAW DATA" / "US+TEV" / "20260815T094744_083-MEDAN-WARISAN-2"
    assert extract_inst.dest_dir == expected_dest
    assert extract_inst.substation_folder_name == "083"


def test_loader_executes_extraction_and_idempotent_overwrite(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    import zipfile

    loader = RawMaterialLoader()

    # Create dummy zip file
    zip_path = tmp_path / "sample_survey.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("index.html", "<html>Test</html>")
        z.writestr("survey_metadata.js", "var survey_metadata = {};")
        z.writestr("SWG/feeder.html", "<html>Feeder</html>")

    dest_dir = tmp_path / "RAW MATERIAL" / "KUANTAN" / "01. AUGUST" / "15-08-2026" / "083" / "RAW DATA" / "US+TEV" / "sample_survey"
    dest_dir.mkdir(parents=True)
    (dest_dir / "old_stale.txt").write_text("stale data", encoding="utf-8")

    plan = TransformationPlan(
        directories_to_create=(dest_dir.parent,),
        copy_instructions=(),
        extract_instructions=(
            ExtractInstruction(
                source_archive=zip_path,
                dest_dir=dest_dir,
                substation_folder_name="083",
            ),
        ),
        substation_folder_name="083",
        ir_count=0,
        dg_count=0,
        us_tev_count=1,
    )

    counts = loader.execute_plan(mock_env, plan)
    assert counts == (0, 0, 1)

    # Verify old stale file is gone (clean overwrite)
    assert not (dest_dir / "old_stale.txt").exists()

    # Verify unzipped assets exist
    assert (dest_dir / "index.html").exists()
    assert (dest_dir / "survey_metadata.js").exists()
    assert (dest_dir / "SWG" / "feeder.html").exists()





