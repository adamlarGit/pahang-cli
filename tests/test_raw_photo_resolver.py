"""Unit tests for RawPhotoResolver (Ticket #25 / T2.2)."""

from __future__ import annotations

import logging
from pathlib import Path
import pytest

from src.project.models import CameraConfig
from src.full_report.photo_resolver import (
    PhotoPair,
    RawPhotoResolver,
)


@pytest.fixture
def ir_dir(tmp_path: Path) -> Path:
    """Create a temporary RAW DATA/IR directory structure."""
    raw_ir = tmp_path / "RAW DATA" / "IR"
    raw_ir.mkdir(parents=True)
    return raw_ir


def test_resolve_ir_photo_integer_to_path(ir_dir: Path) -> None:
    """Resolves integer photo number 290 to RAW DATA/IR/FLIR0290.jpg."""
    ir_file = ir_dir / "FLIR0290.jpg"
    ir_file.touch()

    resolver = RawPhotoResolver(ir_dir)
    resolved = resolver.resolve_ir_photo(290)

    assert Path(resolved) == ir_file
    assert resolved.endswith("FLIR0290.jpg")


def test_resolve_ir_photo_missing_directory_returns_empty() -> None:
    """Safely returns empty string '' when directory does not exist on disk."""
    resolver = RawPhotoResolver("NON_EXISTENT_DIR")
    assert resolver.resolve_ir_photo(290) == ""


def test_discover_paired_visual_photo_patterns(ir_dir: Path) -> None:
    """Discovers paired visual photo matching FLIR0290*-photo*.jpg across various naming patterns."""
    # Pattern 1: FLIR0290- photo.jpg (space after hyphen)
    (ir_dir / "FLIR0290.jpg").touch()
    vis1 = ir_dir / "FLIR0290- photo.jpg"
    vis1.touch()

    # Pattern 2: FLIR0291-photo.jpg (no space)
    (ir_dir / "FLIR0291.jpg").touch()
    vis2 = ir_dir / "FLIR0291-photo.jpg"
    vis2.touch()

    # Pattern 3: FLIR0292 - photo.jpg (spaces around hyphen)
    (ir_dir / "FLIR0292.jpg").touch()
    vis3 = ir_dir / "FLIR0292 - photo.jpg"
    vis3.touch()

    # Pattern 4: FLIR0293_photo.jpg (underscore)
    (ir_dir / "FLIR0293.jpg").touch()
    vis4 = ir_dir / "FLIR0293_photo.jpg"
    vis4.touch()

    # Pattern 5: FLIR0294 photo.jpg (space)
    (ir_dir / "FLIR0294.jpg").touch()
    vis5 = ir_dir / "FLIR0294 photo.jpg"
    vis5.touch()

    # Pattern 6: FLIR0295-photo-01.jpg (suffix)
    (ir_dir / "FLIR0295.jpg").touch()
    vis6 = ir_dir / "FLIR0295-photo-01.jpg"
    vis6.touch()

    # Pattern 7: FLIR0296-DC.jpg (DC suffix)
    (ir_dir / "FLIR0296.jpg").touch()
    vis7 = ir_dir / "FLIR0296-DC.jpg"
    vis7.touch()

    # Pattern 8: Uppercase FLIR0297-PHOTO.JPG
    (ir_dir / "FLIR0297.JPG").touch()
    vis8 = ir_dir / "FLIR0297-PHOTO.JPG"
    vis8.touch()

    resolver = RawPhotoResolver(ir_dir)

    assert Path(resolver.resolve_visual_photo(290)) == vis1
    assert Path(resolver.resolve_visual_photo(291)) == vis2
    assert Path(resolver.resolve_visual_photo(292)) == vis3
    assert Path(resolver.resolve_visual_photo(293)) == vis4
    assert Path(resolver.resolve_visual_photo(294)) == vis5
    assert Path(resolver.resolve_visual_photo(295)) == vis6
    assert Path(resolver.resolve_visual_photo(296)) == vis7
    assert Path(resolver.resolve_visual_photo(297)) == vis8


def test_missing_paired_visual_photo_returns_empty_with_warning(ir_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Safely returns empty string '' with a warning if the paired visual photo is missing on disk."""
    (ir_dir / "FLIR0290.jpg").touch()
    # No paired visual photo created

    resolver = RawPhotoResolver(ir_dir)
    with caplog.at_level(logging.WARNING):
        vis = resolver.resolve_visual_photo(290)

    assert vis == ""
    assert any("FLIR0290" in w and "missing" in w for w in resolver.warnings)
    assert any("FLIR0290" in record.message for record in caplog.records)


def test_missing_ir_photo_returns_empty_with_warning(ir_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Safely returns empty string '' with warning when IR photo is absent from existing directory."""
    resolver = RawPhotoResolver(ir_dir)
    with caplog.at_level(logging.WARNING):
        ir = resolver.resolve_ir_photo(999)

    assert ir == ""
    assert any("FLIR0999" in w and "missing" in w for w in resolver.warnings)


def test_resolve_pair_complete_and_partial(ir_dir: Path) -> None:
    """Verifies resolve_pair returns PhotoPair with complete or partial paths."""
    (ir_dir / "FLIR0290.jpg").touch()
    (ir_dir / "FLIR0290- photo.jpg").touch()

    (ir_dir / "FLIR0291.jpg").touch()
    # 291 has no visual photo

    resolver = RawPhotoResolver(ir_dir)

    pair1 = resolver.resolve_pair(290)
    assert isinstance(pair1, PhotoPair)
    assert pair1.is_complete
    assert pair1.has_ir
    assert pair1.has_visual
    assert pair1.photo_number == 290
    assert pair1.ir_photo.endswith("FLIR0290.jpg")
    assert pair1.visual_photo.endswith("FLIR0290- photo.jpg")

    # Unpacking test
    ir_val, vis_val = pair1
    assert ir_val == pair1.ir_photo
    assert vis_val == pair1.visual_photo

    pair2 = resolver.resolve_pair(291)
    assert not pair2.is_complete
    assert pair2.has_ir
    assert not pair2.has_visual
    assert pair2.visual_photo == ""


def test_secondary_cable_split_photo_lookup_per_d27(ir_dir: Path) -> None:
    """Handles secondary cable split photo lookup with empty fallback per D27/D48."""
    # When split photo number is absent / None
    resolver = RawPhotoResolver(ir_dir)
    assert resolver.resolve_cable_split_photo(None) == ""
    assert resolver.resolve_cable_split_photo() == ""

    split_pair = resolver.resolve_cable_split_pair(None)
    assert split_pair.ir_photo == ""
    assert split_pair.visual_photo == ""

    # When photo numbers sequence has only 1 photo (primary photo exists on disk)
    (ir_dir / "FLIR0290.jpg").touch()
    split_pair_single = resolver.resolve_cable_split_pair([290])
    assert split_pair_single.ir_photo == ""
    assert split_pair_single.visual_photo == ""

    # When secondary photo number is provided and present on disk
    (ir_dir / "FLIR0291.jpg").touch()
    (ir_dir / "FLIR0291- photo.jpg").touch()
    res_pair = resolver.resolve_cable_split_pair([290, 291])
    assert res_pair.is_complete
    assert res_pair.ir_photo.endswith("FLIR0291.jpg")

    # When secondary photo number is provided but missing on disk -> safe empty fallback
    res_pair_missing = resolver.resolve_cable_split_pair(999)
    assert res_pair_missing.ir_photo == ""
    assert res_pair_missing.visual_photo == ""


def test_transformer_overview_top_resolution_per_d48(ir_dir: Path) -> None:
    """Verifies transformer overview top photo resolution with empty fallback per D48."""
    resolver = RawPhotoResolver(ir_dir)
    assert resolver.resolve_tx_overview_top_photo(None) == ""
    assert resolver.resolve_tx_overview_top_pair(None).ir_photo == ""

    (ir_dir / "FLIR0100.jpg").touch()
    assert resolver.resolve_tx_overview_top_photo(100).endswith("FLIR0100.jpg")
    assert resolver.resolve_tx_overview_top_photo(999) == ""


def test_dual_pair_camera_config(ir_dir: Path) -> None:
    """Verifies visual photo pairing when CameraConfig ir_mode is dual_pair."""
    cfg = CameraConfig(
        ir_mode="dual_pair",
        ir_prefix="FLIR",
        dc_prefix="DC_",
        dc_offset=1,
    )
    (ir_dir / "FLIR0290.jpg").touch()
    (ir_dir / "DC_0291.jpg").touch()

    resolver = RawPhotoResolver(ir_dir, camera_config=cfg)
    pair = resolver.resolve_pair(290)

    assert pair.is_complete
    assert pair.ir_photo.endswith("FLIR0290.jpg")
    assert pair.visual_photo.endswith("DC_0291.jpg")


def test_single_mode_does_not_match_dc_files(ir_dir: Path) -> None:
    """Verifies that DC_ visual photos are not paired when CameraConfig ir_mode is single."""
    (ir_dir / "FLIR0290.jpg").touch()
    (ir_dir / "DC_0291.jpg").touch()

    resolver = RawPhotoResolver(ir_dir, camera_config=CameraConfig(ir_mode="single"))
    # In single mode, DC_0291.jpg should NOT pair with FLIR0290
    assert resolver.resolve_visual_photo(290) == ""


def test_custom_prefix_camera_config(ir_dir: Path) -> None:
    """Verifies resolution with custom IR prefix (e.g. IR_)."""
    cfg = CameraConfig(ir_prefix="IR_")
    (ir_dir / "IR_0290.jpg").touch()
    (ir_dir / "IR_0290- photo.jpg").touch()

    resolver = RawPhotoResolver(ir_dir, camera_config=cfg)
    pair = resolver.resolve_pair(290)

    assert pair.is_complete
    assert pair.ir_photo.endswith("IR_0290.jpg")
    assert pair.visual_photo.endswith("IR_0290- photo.jpg")


def test_date_stamped_filenames(ir_dir: Path) -> None:
    """Verifies resolution of date-stamped filenames (e.g. FLIR_20260804_0290.jpg)."""
    (ir_dir / "FLIR_20260804_0290.jpg").touch()
    (ir_dir / "FLIR_20260804_0290- photo.jpg").touch()

    resolver = RawPhotoResolver(ir_dir)
    pair = resolver.resolve_pair(290)

    assert pair.is_complete
    assert pair.ir_photo.endswith("FLIR_20260804_0290.jpg")
    assert pair.visual_photo.endswith("FLIR_20260804_0290- photo.jpg")


def test_directory_nesting_resolution(tmp_path: Path) -> None:
    """Verifies resolver navigates from substation root to RAW DATA/IR automatically."""
    substation_root = tmp_path / "005. TALAPIA (IR+VI)"
    raw_ir = substation_root / "RAW DATA" / "IR"
    raw_ir.mkdir(parents=True)
    (raw_ir / "FLIR0290.jpg").touch()

    # Pass substation root folder directly
    resolver = RawPhotoResolver(substation_root)
    assert resolver.ir_dir == raw_ir
    assert resolver.resolve_ir_photo(290).endswith("FLIR0290.jpg")


def test_digit_collision_guard(ir_dir: Path) -> None:
    """Verifies that photo 29 does not collide with photo 290."""
    (ir_dir / "FLIR0290.jpg").touch()
    (ir_dir / "FLIR0290- photo.jpg").touch()

    resolver = RawPhotoResolver(ir_dir)
    # Photo 29 should not resolve to 290
    assert resolver.resolve_ir_photo(29) == ""
    assert resolver.resolve_visual_photo(29) == ""
