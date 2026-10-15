"""Unit tests for 33kV raw material discovery and US+TEV multi-board archive extraction."""

from __future__ import annotations

from pathlib import Path
import zipfile
import openpyxl
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import CameraConfig, ProjectMetadata
from src.project.storage import (
    LocalWorkspaceStorage,
    SubstationStemInfo,
    parse_substation_stem,
)
from src.testsheet.models import PhotoRange, SubstationTestsheetPackage
from src.workflows.models import RawMaterialRequest
from src.workflows.raw_material import (
    RawMaterialExtractor,
    RawMaterialFilter,
    RawMaterialTransformer,
    RawMaterialWorkflow,
)


def test_parse_substation_stem_ppu_standard() -> None:
    stem = "01. PPU APMM 33-11kV (VI)"
    info = parse_substation_stem(stem)
    assert info.substation_number == 1
    assert info.station_type == "PPU"
    assert info.name == "APMM"
    assert info.voltage_token == "33-11kV"
    assert info.defect_suffix == "(VI)"


def test_parse_substation_stem_pmu_multi_voltage() -> None:
    stem = "08. PMU GBID 275-132-33-11kV (VI)"
    info = parse_substation_stem(stem)
    assert info.substation_number == 8
    assert info.station_type == "PMU"
    assert info.name == "GBID"
    assert info.voltage_token == "275-132-33-11kV"
    assert info.defect_suffix == "(VI)"


def test_parse_substation_stem_ssu_single_voltage() -> None:
    stem = "05. SSU KPC GEBENG 33kV (VI)"
    info = parse_substation_stem(stem)
    assert info.substation_number == 5
    assert info.station_type == "SSU"
    assert info.name == "KPC GEBENG"
    assert info.voltage_token == "33kV"
    assert info.defect_suffix == "(VI)"


def test_parse_substation_stem_nested_parentheses() -> None:
    stem = "03. PPU KIIP (SSU CAMEL POWER) 33-11kV (VI)"
    info = parse_substation_stem(stem)
    assert info.substation_number == 3
    assert info.station_type == "PPU"
    assert info.name == "KIIP (SSU CAMEL POWER)"
    assert info.voltage_token == "33-11kV"
    assert info.defect_suffix == "(VI)"


def test_parse_substation_stem_complex_defect_suffix() -> None:
    stem = "01. PPU APMM 33-11kV (IR+US+TEV+VI)"
    info = parse_substation_stem(stem)
    assert info.substation_number == 1
    assert info.station_type == "PPU"
    assert info.name == "APMM"
    assert info.voltage_token == "33-11kV"
    assert info.defect_suffix == "(IR+US+TEV+VI)"


def test_parse_substation_stem_without_defect_suffix() -> None:
    stem = "01. PPU APMM 33-11kV"
    info = parse_substation_stem(stem)
    assert info.substation_number == 1
    assert info.station_type == "PPU"
    assert info.name == "APMM"
    assert info.voltage_token == "33-11kV"
    assert info.defect_suffix is None


def test_parse_substation_stem_11kv_legacy_format() -> None:
    stem = "001. PE TELUK CEMPEDAK"
    info = parse_substation_stem(stem)
    assert info.substation_number == 1
    assert info.station_type == "PE"
    assert info.name == "TELUK CEMPEDAK"
    assert info.voltage_token is None
    assert info.defect_suffix is None


def test_parse_substation_stem_bare_number() -> None:
    assert parse_substation_stem("01").substation_number == 1
    assert parse_substation_stem("001").substation_number == 1
    assert parse_substation_stem("5").substation_number == 5


def test_workspace_storage_get_substation_raw_data_dir_2digit_and_us(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    date_dir = tmp_path / "RAW MATERIAL" / "KUANTAN" / "01. JANUARY" / "15-01-2026"
    sub_dir = date_dir / "01. PPU APMM 33-11kV (VI)"
    us_dir = sub_dir / "US"
    us_dir.mkdir(parents=True)

    found = storage.get_substation_raw_data_dir("KUANTAN", "01. JANUARY", "15-01-2026", 1)
    assert found == sub_dir


def test_workspace_storage_get_substation_raw_data_dir_with_raw_data_child(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    date_dir = tmp_path / "RAW MATERIAL" / "KUANTAN" / "01. JANUARY" / "15-01-2026"
    sub_dir = date_dir / "05. SSU KPC GEBENG 33kV (VI)"
    raw_data_child = sub_dir / "RAW DATA"
    raw_data_child.mkdir(parents=True)

    found = storage.get_substation_raw_data_dir("KUANTAN", "01. JANUARY", "15-01-2026", 5)
    assert found == raw_data_child


def test_extractor_scans_us_and_us_tev_and_root_folders(tmp_path: Path) -> None:
    extractor = RawMaterialExtractor()
    unsorted_dir = tmp_path / "UNSORTED RAW DATA"
    us_dir = unsorted_dir / "US"
    us_tev_dir = unsorted_dir / "US+TEV"
    us_dir.mkdir(parents=True)
    us_tev_dir.mkdir(parents=True)

    zip_root = unsorted_dir / "01_ROOT.zip"
    zip_us = us_dir / "01_US.zip"
    zip_us_tev = us_tev_dir / "01_USTEV.zip"
    zip_root.touch()
    zip_us.touch()
    zip_us_tev.touch()

    pkg = SubstationTestsheetPackage(
        substation_number=1,
        station="KUANTAN",
        month="01. JANUARY",
        date_str="15-01-2026",
        testsheet_path=tmp_path / "01. PPU APMM 33-11kV (VI).xlsx",
        unsorted_raw_data_dir=unsorted_dir,
    )

    warnings: list[str] = []
    extracted = extractor.extract_package_data(pkg, warnings)

    assert len(extracted.us_tev_archives) == 3
    assert zip_root in extracted.us_tev_archives
    assert zip_us in extracted.us_tev_archives
    assert zip_us_tev in extracted.us_tev_archives


def test_filter_us_tev_archives_33kv_multi_board() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    archives = [
        Path("/tmp/01_PPU_APMM_33KV.zip"),
        Path("/tmp/01_PPU_APMM_11KV.zip"),
        Path("/tmp/02_PPU_OTHER_33KV.zip"),
    ]

    matched = filter_stage.filter_us_tev_archives(
        archives,
        substation_number=1,
        warnings=warnings,
        voltage_type="33kV",
        station_name="APMM",
    )
    assert len(matched) == 2
    assert Path("/tmp/01_PPU_APMM_33KV.zip") in matched
    assert Path("/tmp/01_PPU_APMM_11KV.zip") in matched
    assert len(warnings) == 0


def test_filter_us_tev_archives_11kv_multi_board_raises_error() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    archives = [
        Path("/tmp/001_PE_A.zip"),
        Path("/tmp/001_PE_B.zip"),
    ]

    with pytest.raises(RuntimeError, match="Multiple US\\+TEV archives matched PE 001"):
        filter_stage.filter_us_tev_archives(
            archives,
            substation_number=1,
            warnings=warnings,
            voltage_type="11kV",
        )


def test_filter_us_tev_archives_2digit_matching() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    archives = [
        Path("/tmp/05_SSU_KPC_GEBENG_33KV.zip"),
        Path("/tmp/08_PMU_GBID_33KV.zip"),
    ]

    matched = filter_stage.filter_us_tev_archives(
        archives,
        substation_number=5,
        warnings=warnings,
        voltage_type="33kV",
    )
    assert matched == [Path("/tmp/05_SSU_KPC_GEBENG_33KV.zip")]


def test_filter_us_tev_archives_station_name_disambiguation() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []

    archives = [
        Path("/tmp/01_PPU_APMM_33KV.zip"),
        Path("/tmp/01_PPU_PEKAN_33KV.zip"),
    ]

    matched = filter_stage.filter_us_tev_archives(
        archives,
        substation_number=1,
        warnings=warnings,
        voltage_type="33kV",
        station_name="APMM",
    )
    assert matched == [Path("/tmp/01_PPU_APMM_33KV.zip")]


def test_resolve_substation_dest_dir_33kv_default_to_testsheet_stem(tmp_path: Path) -> None:
    transformer = RawMaterialTransformer()
    meta = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV",
        po_number="PO123",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="1",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    env = ProjectEnvironment(metadata=meta, storage=storage)

    pkg = SubstationTestsheetPackage(
        substation_number=1,
        station="KUANTAN",
        month="01. JANUARY",
        date_str="15-01-2026",
        testsheet_path=tmp_path / "01. PPU APMM 33-11kV (VI).xlsx",
        unsorted_raw_data_dir=tmp_path / "UNSORTED",
    )

    dest_dir = transformer._resolve_substation_dest_dir(env, pkg, "001")
    expected = tmp_path / "RAW MATERIAL" / "KUANTAN" / "01. JANUARY" / "15-01-2026" / "01. PPU APMM 33-11kV (VI)"
    assert dest_dir == expected


def test_resolve_substation_dest_dir_33kv_existing_dir_resolved(tmp_path: Path) -> None:
    transformer = RawMaterialTransformer()
    meta = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV",
        po_number="PO123",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="1",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    env = ProjectEnvironment(metadata=meta, storage=storage)

    date_dir = tmp_path / "RAW MATERIAL" / "KUANTAN" / "01. JANUARY" / "15-01-2026"
    existing = date_dir / "01. PPU APMM 33-11kV (CUSTOM)"
    existing.mkdir(parents=True)

    pkg = SubstationTestsheetPackage(
        substation_number=1,
        station="KUANTAN",
        month="01. JANUARY",
        date_str="15-01-2026",
        testsheet_path=tmp_path / "01. PPU APMM 33-11kV (VI).xlsx",
        unsorted_raw_data_dir=tmp_path / "UNSORTED",
    )

    dest_dir = transformer._resolve_substation_dest_dir(env, pkg, "001")
    assert dest_dir == existing


def test_build_plan_33kv_existing_us_folder_preference(tmp_path: Path) -> None:
    transformer = RawMaterialTransformer()
    meta = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV",
        po_number="PO123",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="1",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    env = ProjectEnvironment(metadata=meta, storage=storage)

    date_dir = tmp_path / "RAW MATERIAL" / "KUANTAN" / "01. JANUARY" / "15-01-2026"
    sub_dir = date_dir / "01. PPU APMM 33-11kV (VI)"
    us_dir = sub_dir / "US"
    us_dir.mkdir(parents=True)

    pkg = SubstationTestsheetPackage(
        substation_number=1,
        station="KUANTAN",
        month="01. JANUARY",
        date_str="15-01-2026",
        testsheet_path=tmp_path / "01. PPU APMM 33-11kV (VI).xlsx",
        unsorted_raw_data_dir=tmp_path / "UNSORTED",
    )

    plan = transformer.build_plan(
        environment=env,
        package=pkg,
        filtered_ir=(),
        filtered_dg=(),
        matched_us_tevs=[tmp_path / "01_PPU_APMM_33KV.zip"],
    )

    assert len(plan.extract_instructions) == 1
    assert plan.extract_instructions[0].dest_dir == us_dir / "01_PPU_APMM_33KV"
    assert us_dir in plan.directories_to_create


def test_build_plan_33kv_multi_board_extract_instructions(tmp_path: Path) -> None:
    transformer = RawMaterialTransformer()
    meta = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV",
        po_number="PO123",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="1",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    env = ProjectEnvironment(metadata=meta, storage=storage)

    pkg = SubstationTestsheetPackage(
        substation_number=1,
        station="KUANTAN",
        month="01. JANUARY",
        date_str="15-01-2026",
        testsheet_path=tmp_path / "01. PPU APMM 33-11kV (VI).xlsx",
        unsorted_raw_data_dir=tmp_path / "UNSORTED",
    )

    archives = [
        tmp_path / "01_PPU_APMM_33KV.zip",
        tmp_path / "01_PPU_APMM_11KV.zip",
    ]

    plan = transformer.build_plan(
        environment=env,
        package=pkg,
        filtered_ir=(),
        filtered_dg=(),
        matched_us_tevs=archives,
    )

    assert plan.us_tev_count == 2
    assert len(plan.extract_instructions) == 2
    dest_stems = [inst.dest_dir.name for inst in plan.extract_instructions]
    assert dest_stems == ["01_PPU_APMM_33KV", "01_PPU_APMM_11KV"]


def test_filter_ir_dg_blank_bounds_resilience() -> None:
    filter_stage = RawMaterialFilter()
    warnings: list[str] = []
    blank_range = PhotoRange(start_num=None, end_num=None)

    ir_matched = filter_stage.filter_ir_photos(
        photos=[Path("/tmp/FLIR0001.jpg")],
        camera_config=CameraConfig(),
        photo_range=blank_range,
        substation_folder_name="01. PPU APMM 33-11kV (VI)",
        warnings=warnings,
    )
    assert ir_matched == []
    assert any("photo range not specified or incomplete" in w for w in warnings)

    dg_matched = filter_stage.filter_dg_photos(
        photos=[Path("/tmp/IMG_0001.jpg")],
        camera_config=CameraConfig(),
        photo_range=blank_range,
        substation_folder_name="01. PPU APMM 33-11kV (VI)",
        warnings=warnings,
    )
    assert dg_matched == []


def test_raw_material_workflow_33kv_e2e_multi_board(tmp_path: Path) -> None:
    from tests.fixtures.ppu_workbook_factory import create_ppu_testsheet_workbook

    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    meta = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV",
        po_number="PO123",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="1",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    env = ProjectEnvironment(metadata=meta, storage=storage)
    storage.ensure_directory(storage.get_raw_material_dir())
    storage.ensure_directory(storage.get_python_dir())

    # 1. Populate TOTAL PE.xlsx
    total_pe_path = storage.get_total_pe_path()
    wb_pe = openpyxl.Workbook()
    ws_pe = wb_pe.active
    ws_pe.title = "DataCycle1"
    ws_pe.append(["PE NO", "FL NUMBER", "SUBSTATION NAME", "DATE", "TYPE", "WO", "SCOPE"])
    ws_pe.append(["1", "CGBG-PPU-APMM", "PPU APMM", "15-01-2026", "PPU", "WO123", ""])
    wb_pe.save(total_pe_path)
    wb_pe.close()

    # 2. Testsheet setup
    date_dir = tmp_path / "TESTSHEET" / "KUANTAN" / "01. JANUARY" / "15-01-2026"
    date_dir.mkdir(parents=True)
    testsheet_path = date_dir / "01. PPU APMM 33-11kV (VI).xlsx"
    create_ppu_testsheet_workbook(
        path=testsheet_path,
        substation_number=1,
        substation_name="PPU APMM 33-11kV",
        date_val="15-01-2026",
        raw_photo_bounds={"ir_start": 1, "ir_end": 2, "dg_start": 1, "dg_end": 1},
    )

    # 3. Unsorted raw data
    unsorted_dir = date_dir / "UNSORTED RAW DATA"
    (unsorted_dir / "IR").mkdir(parents=True)
    (unsorted_dir / "DG").mkdir(parents=True)
    (unsorted_dir / "US").mkdir(parents=True)

    (unsorted_dir / "IR" / "FLIR0001.jpg").touch()
    (unsorted_dir / "IR" / "FLIR0002.jpg").touch()
    (unsorted_dir / "DG" / "IMG_0001.jpg").touch()

    # Create 2 multi-board zip archives
    with zipfile.ZipFile(unsorted_dir / "US" / "01_PPU_APMM_33KV.zip", "w") as z:
        z.writestr("33kv.txt", "33kv data")
    with zipfile.ZipFile(unsorted_dir / "US" / "01_PPU_APMM_11KV.zip", "w") as z:
        z.writestr("11kv.txt", "11kv data")

    workflow = RawMaterialWorkflow()
    request = RawMaterialRequest(output_path=date_dir)
    result = workflow.execute(env, request)

    assert result.substations_count == 1
    assert result.ir_copied_count == 2
    assert result.dg_copied_count == 1
    assert result.us_tev_extracted_count == 2

    dest_sub = tmp_path / "RAW MATERIAL" / "KUANTAN" / "01. JANUARY" / "15-01-2026" / "01. PPU APMM 33-11kV (VI)"
    assert (dest_sub / "IR" / "FLIR0001.jpg").exists()
    assert (dest_sub / "IR" / "FLIR0002.jpg").exists()
    assert (dest_sub / "DG" / "IMG_0001.jpg").exists()
    assert (dest_sub / "US+TEV" / "01_PPU_APMM_33KV" / "33kv.txt").exists()
    assert (dest_sub / "US+TEV" / "01_PPU_APMM_11KV" / "11kv.txt").exists()



