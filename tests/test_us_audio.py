"""Unit tests for ultrasound audio embedding protection and pre-embedding snapshot management.

Ticket #142:
- os.replace retry loop with exponential backoff (5 attempts over 2.5s)
- Pre-embedding snapshot (.tmp_pre_sound_{target_pdf.name}) for fail-safe rollback
- Guaranteed cleanup of snapshot and temporary files in all paths
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import pymupdf as fitz
except ImportError:
    import fitz
import pytest

from src.workflows.us_audio import (
    _replace_with_retry,
    embed_survey_ultrasound_into_pdf,
)


def _create_mock_pdf_with_sound_clip(pdf_path: Path) -> Path:
    """Create a mock PDF containing 'Sound clip' text anchor."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Insert text anchor
    page.insert_text((100, 100), "Sound clip: Ultrasonic measurement")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_replace_with_retry_succeeds_immediately(tmp_path: Path) -> None:
    """Test _replace_with_retry succeeds on first attempt when no locks are present."""
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    src.write_text("source content")
    dst.write_text("old content")

    _replace_with_retry(src, dst, max_attempts=5, total_wait=0.1)

    assert not src.exists()
    assert dst.read_text() == "source content"


def test_replace_with_retry_succeeds_after_transient_locks(tmp_path: Path) -> None:
    """Test _replace_with_retry retries with backoff and succeeds once transient lock releases."""
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    src.write_text("source content")
    dst.write_text("destination content")

    attempts = 0
    real_replace = os.replace

    def fake_replace(s, d):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("Transient Windows lock: file in use")
        real_replace(s, d)

    with patch("os.replace", side_effect=fake_replace), patch("time.sleep"):
        _replace_with_retry(src, dst, max_attempts=5, total_wait=0.1)

    assert attempts == 3
    assert dst.read_text() == "source content"


def test_replace_with_retry_raises_after_max_attempts(tmp_path: Path) -> None:
    """Test _replace_with_retry raises PermissionError when lock persists beyond max attempts."""
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    src.write_text("source content")
    dst.write_text("destination content")

    with patch("os.replace", side_effect=PermissionError("Locked")), patch("time.sleep"):
        with pytest.raises(PermissionError):
            _replace_with_retry(src, dst, max_attempts=5, total_wait=0.1)


def test_embed_survey_ultrasound_snapshot_and_rollback_on_replace_failure(tmp_path: Path) -> None:
    """Test that when os.replace fails after all retries, target_pdf is restored from pre-embedding snapshot."""
    pdf_path = tmp_path / "deliverable.pdf"
    _create_mock_pdf_with_sound_clip(pdf_path)
    original_bytes = pdf_path.read_bytes()

    survey_root = tmp_path / "survey"
    survey_root.mkdir()

    # Mock discover_survey_measurements to return a valid US measurement
    mock_meas = MagicMock()
    mock_meas.tech = "US"
    mock_meas.label = "VCB_CB"

    snapshot_seen = []

    def fake_replace_fail(src, dst, *args, **kwargs):
        snapshot_file = pdf_path.parent / f".tmp_pre_sound_{pdf_path.name}"
        if snapshot_file.exists():
            snapshot_seen.append(snapshot_file.read_bytes())
        raise PermissionError("Persistent filesystem lock on destination PDF")

    with (
        patch("src.workflows.us_audio.discover_survey_measurements", return_value=[mock_meas]),
        patch("src.workflows.us_audio.resolve_measurement_audio_for_page", return_value=tmp_path / "dummy.wav"),
        patch("pathlib.Path.is_file", return_value=True),
        patch("src.workflows.us_audio.convert_24bit_wav_to_16bit_pcm", return_value=(b"\x00" * 100, 8000, 1)),
        patch("src.workflows.us_audio.embed_sound_annotation"),
        patch("src.workflows.us_audio._replace_with_retry", side_effect=fake_replace_fail),
    ):
        with pytest.raises(PermissionError):
            embed_survey_ultrasound_into_pdf(pdf_path, survey_root)

    # 1. Snapshot was captured before modification
    assert len(snapshot_seen) == 1
    assert snapshot_seen[0] == original_bytes

    # 2. Target PDF was rolled back to original bytes
    assert pdf_path.read_bytes() == original_bytes

    # 3. Snapshot and temp files were unlinked in finally block (zero lingering files)
    snapshot_file = pdf_path.parent / f".tmp_pre_sound_{pdf_path.name}"
    tmp_sound_file = pdf_path.parent / f".tmp_sound_{pdf_path.name}"
    assert not snapshot_file.exists()
    assert not tmp_sound_file.exists()


def test_embed_survey_ultrasound_cleans_up_snapshot_on_success(tmp_path: Path) -> None:
    """Test that pre-embedding snapshot is cleaned up on successful embedding."""
    pdf_path = tmp_path / "success.pdf"
    _create_mock_pdf_with_sound_clip(pdf_path)

    survey_root = tmp_path / "survey"
    survey_root.mkdir()

    mock_meas = MagicMock()
    mock_meas.tech = "US"
    mock_meas.label = "VCB_CB"

    snapshot_path = pdf_path.parent / f".tmp_pre_sound_{pdf_path.name}"
    tmp_path_sound = pdf_path.parent / f".tmp_sound_{pdf_path.name}"

    with (
        patch("src.workflows.us_audio.discover_survey_measurements", return_value=[mock_meas]),
        patch("src.workflows.us_audio.resolve_measurement_audio_for_page", return_value=tmp_path / "dummy.wav"),
        patch("pathlib.Path.is_file", return_value=True),
        patch("src.workflows.us_audio.convert_24bit_wav_to_16bit_pcm", return_value=(b"\x00" * 100, 8000, 1)),
        patch("src.workflows.us_audio.embed_sound_annotation"),
        patch("src.workflows.us_audio._replace_with_retry"),
    ):
        count = embed_survey_ultrasound_into_pdf(pdf_path, survey_root)
        assert count == 1

    # In all cases, zero temporary or snapshot files remain
    assert not snapshot_path.exists()
    assert not tmp_path_sound.exists()


def test_embed_survey_ultrasound_preflight_cleans_up_stale_snapshot(tmp_path: Path) -> None:
    """Test that pre-flight unlinks any pre-existing stale snapshot or temp files."""
    pdf_path = tmp_path / "stale_test.pdf"
    _create_mock_pdf_with_sound_clip(pdf_path)

    stale_snapshot = pdf_path.parent / f".tmp_pre_sound_{pdf_path.name}"
    stale_sound = pdf_path.parent / f".tmp_sound_{pdf_path.name}"
    stale_snapshot.write_text("stale snapshot")
    stale_sound.write_text("stale sound")

    # Call with non-existent survey (returns 0)
    embed_survey_ultrasound_into_pdf(pdf_path, survey_root=None)

    # Even when survey is missing, stale temp files should not linger
    # Now call with survey that has no US measurements
    survey_empty = tmp_path / "survey_empty"
    survey_empty.mkdir()
    embed_survey_ultrasound_into_pdf(pdf_path, survey_root=survey_empty)

    assert not stale_snapshot.exists()
    assert not stale_sound.exists()
