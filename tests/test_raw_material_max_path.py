"""Tests for Windows MAX_PATH (> 260 chars) hardening across RawMaterialLoader and safe_path utility."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
import shutil
import zipfile

import pytest

from src.core.path_utils import safe_path
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.raw_material import (
    CopyInstruction,
    ExtractInstruction,
    RawMaterialLoader,
    TransformationPlan,
)


def _build_deep_path(base_dir: Path, target_min_len: int = 280) -> Path:
    """Helper to build a deeply nested path exceeding target_min_len characters."""
    segment = "substation_folder_with_extended_path_segment_exceeding_standard_limits"
    current = base_dir
    while len(str(current)) < target_min_len:
        current = current / segment
    return current


def test_safe_path_normalization() -> None:
    """Verify safe_path normalizes slashes, handles UNC paths, and applies Windows \\\\?\\ prefix."""
    # Slashes normalized
    res = safe_path("C:/folder/subfolder/file.txt")
    if os.name == "nt":
        assert res.startswith("\\\\?\\")
        assert "/" not in res
        assert res == "\\\\?\\C:\\folder\\subfolder\\file.txt"

    # Already prefixed path
    prefixed = "\\\\?\\C:\\folder\\subfolder\\file.txt"
    assert safe_path(prefixed) == prefixed

    # UNC path
    unc = "\\\\server\\share\\data\\file.txt"
    res_unc = safe_path(unc)
    if os.name == "nt":
        assert res_unc == "\\\\?\\UNC\\server\\share\\data\\file.txt"

    # Already prefixed UNC path
    prefixed_unc = "\\\\?\\UNC\\server\\share\\data\\file.txt"
    assert safe_path(prefixed_unc) == prefixed_unc

    # Device path handling
    device_path = "\\\\.\\pipe\\named_pipe_test"
    assert safe_path(device_path) == device_path

    # Empty path handling
    assert safe_path("") == ""
    assert safe_path(Path("")) == ""
    assert safe_path(None) == ""


def test_safe_path_copy_and_rmtree_long_path(tmp_path: Path) -> None:
    """Verify file copying and rmtree succeed on real disk paths exceeding 260 characters."""
    deep_dir = _build_deep_path(tmp_path, target_min_len=280)
    assert len(str(deep_dir)) > 260

    # 1. Directory creation
    safe_deep = safe_path(deep_dir)
    os.makedirs(safe_deep, exist_ok=True)
    assert os.path.exists(safe_deep)

    # 2. File creation and copy
    source_file = tmp_path / "test_photo_sample.jpg"
    source_file.write_bytes(b"JPEG_MOCK_DATA_12345")
    dest_file = deep_dir / "copied_deep_photo.jpg"

    shutil.copy2(safe_path(source_file), safe_path(dest_file))
    assert os.path.exists(safe_path(dest_file))
    assert Path(safe_path(dest_file)).read_bytes() == b"JPEG_MOCK_DATA_12345"

    # 3. Cleanup via rmtree on deep directory
    shutil.rmtree(safe_deep)
    assert not os.path.exists(safe_deep)


def test_safe_path_zip_extraction_long_path(tmp_path: Path) -> None:
    """Verify zip archive extraction succeeds into directory paths exceeding 260 characters."""
    deep_extract_dir = _build_deep_path(tmp_path, target_min_len=280) / "extracted_survey"
    assert len(str(deep_extract_dir)) > 260

    # Create dummy zip archive
    zip_path = tmp_path / "sample_survey_archive.zip"
    with zipfile.ZipFile(safe_path(zip_path), "w") as z:
        z.writestr("index.html", "<html>Mock PRPD Survey</html>")
        z.writestr("SWG/TEV.html", "<html>Mock TEV</html>")
        z.writestr("SWG/data/readings.csv", "timestamp,db,count\n12:00,15,30\n")

    dest_safe = safe_path(deep_extract_dir)
    if os.path.exists(dest_safe):
        shutil.rmtree(dest_safe)
    os.makedirs(dest_safe, exist_ok=True)

    with zipfile.ZipFile(safe_path(zip_path), "r") as z:
        z.extractall(dest_safe)

    assert os.path.exists(safe_path(deep_extract_dir / "index.html"))
    assert os.path.exists(safe_path(deep_extract_dir / "SWG" / "TEV.html"))
    assert os.path.exists(safe_path(deep_extract_dir / "SWG" / "data" / "readings.csv"))

    # Verify content integrity
    extracted_html = Path(safe_path(deep_extract_dir / "index.html")).read_text(encoding="utf-8")
    assert "Mock PRPD Survey" in extracted_html

    # Cleanup
    shutil.rmtree(dest_safe)
    assert not os.path.exists(dest_safe)


def test_raw_material_loader_execute_plan_long_path(tmp_path: Path) -> None:
    """Verify RawMaterialLoader.execute_plan executes on paths exceeding 260 characters without WinError 206."""
    deep_base = _build_deep_path(tmp_path, target_min_len=270)
    substation_dir = deep_base / "12. PPU DEEP LONG SUBSTATION 33-11kV"
    raw_data_dir = substation_dir / "RAW DATA"
    ir_dir = raw_data_dir / "IR"
    dg_dir = raw_data_dir / "DG"
    us_tev_dir = raw_data_dir / "US+TEV" / "survey_run_2026"

    assert len(str(ir_dir)) > 260
    assert len(str(dg_dir)) > 260
    assert len(str(us_tev_dir)) > 260

    meta = ProjectMetadata(
        key="pahang_maxpath_test",
        name="Pahang MAX_PATH Test",
        po_number="PO12345",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="1",
        technologies=("IR", "DG", "US", "TEV"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    env = ProjectEnvironment(metadata=meta, storage=storage)

    # Prepare dummy source photos and archive
    src_dir = tmp_path / "source_photos"
    src_dir.mkdir(parents=True, exist_ok=True)
    ir_photo = src_dir / "IMG_0001.JPG"
    ir_photo.write_bytes(b"IR_IMAGE_BYTES_123")
    dg_photo = src_dir / "IMG_0002.JPG"
    dg_photo.write_bytes(b"DG_IMAGE_BYTES_456")

    archive = src_dir / "survey.zip"
    with zipfile.ZipFile(safe_path(archive), "w") as z:
        z.writestr("index.html", "<html>PRPD Survey</html>")
        z.writestr("details.json", '{"status": "ok"}')

    plan = TransformationPlan(
        directories_to_create=(ir_dir, dg_dir, us_tev_dir),
        copy_instructions=(
            CopyInstruction(
                source_path=ir_photo,
                dest_path=ir_dir / "IMG_0001.JPG",
                tech_name="IR",
                substation_folder_name="12. PPU DEEP LONG SUBSTATION 33-11kV",
                photo_number=1,
            ),
            CopyInstruction(
                source_path=dg_photo,
                dest_path=dg_dir / "IMG_0002.JPG",
                tech_name="DG",
                substation_folder_name="12. PPU DEEP LONG SUBSTATION 33-11kV",
                photo_number=2,
            ),
        ),
        extract_instructions=(
            ExtractInstruction(
                source_archive=archive,
                dest_dir=us_tev_dir,
                substation_folder_name="12. PPU DEEP LONG SUBSTATION 33-11kV",
            ),
        ),
        substation_folder_name="12. PPU DEEP LONG SUBSTATION 33-11kV",
        ir_count=1,
        dg_count=1,
        us_tev_count=1,
        substation_dir=substation_dir,
    )

    loader = RawMaterialLoader()
    counts = loader.execute_plan(env, plan)
    assert counts == (1, 1, 1)

    # Verify destination files on disk
    dest_ir = ir_dir / "IMG_0001.JPG"
    dest_dg = dg_dir / "IMG_0002.JPG"
    dest_html = us_tev_dir / "index.html"
    dest_json = us_tev_dir / "details.json"

    assert os.path.exists(safe_path(dest_ir))
    assert Path(safe_path(dest_ir)).read_bytes() == b"IR_IMAGE_BYTES_123"

    assert os.path.exists(safe_path(dest_dg))
    assert Path(safe_path(dest_dg)).read_bytes() == b"DG_IMAGE_BYTES_456"

    assert os.path.exists(safe_path(dest_html))
    assert "PRPD Survey" in Path(safe_path(dest_html)).read_text(encoding="utf-8")

    assert os.path.exists(safe_path(dest_json))


def test_raw_material_loader_legacy_migration_long_path(tmp_path: Path) -> None:
    """Verify RawMaterialLoader._migrate_legacy_substation_folders migrates folders on paths exceeding 260 characters."""
    deep_base = _build_deep_path(tmp_path, target_min_len=270)
    substation_dir = deep_base / "05. PPU LEGACY DEEP MIGRATION SUBSTATION"
    loose_ir = substation_dir / "IR"
    loose_dg = substation_dir / "DG"

    assert len(str(loose_ir)) > 260
    assert len(str(loose_dg)) > 260

    os.makedirs(safe_path(loose_ir), exist_ok=True)
    os.makedirs(safe_path(loose_dg), exist_ok=True)

    (Path(safe_path(loose_ir)) / "old_ir.jpg").write_text("old IR content")
    (Path(safe_path(loose_dg)) / "old_dg.jpg").write_text("old DG content")

    loader = RawMaterialLoader()
    loader._migrate_legacy_substation_folders(substation_dir)

    # Legacy loose folders should be migrated and removed
    assert not os.path.exists(safe_path(loose_ir))
    assert not os.path.exists(safe_path(loose_dg))

    # Target files in RAW DATA should exist
    migrated_ir = substation_dir / "RAW DATA" / "IR" / "old_ir.jpg"
    migrated_dg = substation_dir / "RAW DATA" / "DG" / "old_dg.jpg"

    assert os.path.exists(safe_path(migrated_ir))
    assert Path(safe_path(migrated_ir)).read_text() == "old IR content"

    assert os.path.exists(safe_path(migrated_dg))
    assert Path(safe_path(migrated_dg)).read_text() == "old DG content"


def test_merge_directory_contents_with_existing_target_long_path(tmp_path: Path) -> None:
    """Verify RawMaterialLoader._merge_directory_contents merges into existing targets on paths > 260 chars."""
    deep_base = _build_deep_path(tmp_path, target_min_len=270)
    src_dir = deep_base / "source_merge_folder"
    dst_dir = deep_base / "target_merge_folder"

    assert len(str(src_dir)) > 260
    assert len(str(dst_dir)) > 260

    # 1. Setup pre-existing content in target directory
    dst_shared = dst_dir / "nested_shared_dir"
    os.makedirs(safe_path(dst_shared), exist_ok=True)
    (Path(safe_path(dst_dir)) / "existing_keep.txt").write_text("keep existing")
    (Path(safe_path(dst_shared)) / "existing_child.txt").write_text("keep existing child")

    # 2. Setup source directory with files to merge
    src_shared = src_dir / "nested_shared_dir"
    src_unique = src_dir / "nested_unique_dir"
    os.makedirs(safe_path(src_shared), exist_ok=True)
    os.makedirs(safe_path(src_unique), exist_ok=True)
    (Path(safe_path(src_dir)) / "new_file.txt").write_text("merged new file")
    (Path(safe_path(src_shared)) / "new_child.txt").write_text("merged new child")
    (Path(safe_path(src_unique)) / "unique_file.txt").write_text("merged unique file")

    loader = RawMaterialLoader()
    loader._merge_directory_contents(src_dir, dst_dir)

    # 3. Verify destination has all pre-existing and newly merged files
    assert (Path(safe_path(dst_dir)) / "existing_keep.txt").read_text() == "keep existing"
    assert (Path(safe_path(dst_shared)) / "existing_child.txt").read_text() == "keep existing child"
    assert (Path(safe_path(dst_dir)) / "new_file.txt").read_text() == "merged new file"
    assert (Path(safe_path(dst_shared)) / "new_child.txt").read_text() == "merged new child"
    assert (Path(safe_path(dst_dir / "nested_unique_dir")) / "unique_file.txt").read_text() == "merged unique file"


def test_converters_module_remains_untouched_by_safe_path() -> None:
    """Verify COM workflows in src/postprocessing/converters.py remain untouched and excluded from safe_path."""
    from src.postprocessing import converters

    source_code = inspect.getsource(converters)
    assert "safe_path" not in source_code
