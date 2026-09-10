"""Unit tests for finalized Quick Report pre-flight integrity validator (Ticket #21 / T1.2)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from src.full_report.preflight import (
    MIN_FILE_SIZE_BYTES,
    MIN_MEDIA_COUNT,
    PreFlightValidationError,
    PreFlightValidationResult,
    resolve_quick_report_path,
    validate_finalized_quick_report,
)


def _create_mock_docx(
    path: Path,
    *,
    media_count: int = 8,
    target_size_bytes: int = 1_100_000,
    corrupt_zip: bool = False,
) -> Path:
    """Create a mock .docx archive with controlled size and media count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if corrupt_zip:
        # Create non-zip binary file of desired size
        path.write_bytes(b"\x00" * target_size_bytes)
        return path

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        zf.writestr("word/_rels/document.xml.rels", b"<Relationships/>")

        for i in range(media_count):
            zf.writestr(f"word/media/image{i + 1}.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100)

        # Pad word/document.xml to reach target size if needed
        current_size = sum(info.file_size for info in zf.filelist)
        padding = max(0, target_size_bytes - current_size)
        zf.writestr("word/document.xml", b"<w:document>" + b"a" * padding + b"</w:document>")

    return path


def test_resolve_quick_report_path() -> None:
    base = Path("/workspace")
    resolved = resolve_quick_report_path(
        base,
        station="RAUB",
        month="08. AUGUST",
        date="04-08-2026",
        stem="005. TALAPIA (IR+VI)",
    )
    expected = (
        base
        / "QUICK REPORT"
        / "RAUB"
        / "08. AUGUST"
        / "04-08-2026"
        / "005. TALAPIA (IR+VI).docx"
    )
    assert resolved == expected


def test_resolve_quick_report_path_preserves_docx_suffix() -> None:
    base = Path("/workspace")
    resolved = resolve_quick_report_path(
        base,
        station="RAUB",
        month="08. AUGUST",
        date="04-08-2026",
        stem="005. TALAPIA (IR+VI).docx",
    )
    assert resolved.name == "005. TALAPIA (IR+VI).docx"


def test_validate_missing_quick_report(tmp_path: Path) -> None:
    missing_file = tmp_path / "QUICK REPORT" / "missing.docx"

    result = validate_finalized_quick_report(missing_file)
    assert not result.is_valid
    assert not result.exists
    assert result.size_bytes == 0
    assert result.media_count == 0
    assert result.error_message is not None
    assert "does not exist" in result.error_message

    with pytest.raises(PreFlightValidationError) as exc_info:
        validate_finalized_quick_report(missing_file, raise_on_error=True)
    assert exc_info.value.result == result
    assert "does not exist" in str(exc_info.value)


def test_validate_undersized_quick_report(tmp_path: Path) -> None:
    undersized_file = tmp_path / "QUICK REPORT" / "undersized.docx"
    # Create docx with 8 media files but total size < 1.0 MB (~50 KB)
    _create_mock_docx(undersized_file, media_count=8, target_size_bytes=50_000)

    result = validate_finalized_quick_report(undersized_file)
    assert not result.is_valid
    assert result.exists
    assert result.size_bytes < MIN_FILE_SIZE_BYTES
    assert result.media_count == 8
    assert result.error_message is not None
    assert "file size floor" in result.error_message.lower()

    with pytest.raises(PreFlightValidationError):
        validate_finalized_quick_report(undersized_file, raise_on_error=True)


def test_validate_corrupted_zip_archive(tmp_path: Path) -> None:
    corrupted_file = tmp_path / "QUICK REPORT" / "corrupt.docx"
    # Create non-zip file >= 1.0 MB
    _create_mock_docx(corrupted_file, target_size_bytes=1_200_000, corrupt_zip=True)

    result = validate_finalized_quick_report(corrupted_file)
    assert not result.is_valid
    assert result.exists
    assert result.size_bytes >= MIN_FILE_SIZE_BYTES
    assert result.media_count == 0
    assert result.error_message is not None
    assert "not a valid docx" in result.error_message.lower() or "zip" in result.error_message.lower()

    with pytest.raises(PreFlightValidationError):
        validate_finalized_quick_report(corrupted_file, raise_on_error=True)


def test_validate_insufficient_media_count(tmp_path: Path) -> None:
    unpopulated_file = tmp_path / "QUICK REPORT" / "unpopulated.docx"
    # Valid docx >= 1.0 MB, but only 3 images inside word/media/
    _create_mock_docx(unpopulated_file, media_count=3, target_size_bytes=1_200_000)

    result = validate_finalized_quick_report(unpopulated_file)
    assert isinstance(result, PreFlightValidationResult)
    assert not result.is_valid
    assert result.exists
    assert result.size_bytes >= MIN_FILE_SIZE_BYTES
    assert result.media_count == 3
    assert result.media_count < MIN_MEDIA_COUNT
    assert result.error_message is not None
    assert "media count" in result.error_message.lower()

    with pytest.raises(PreFlightValidationError):
        validate_finalized_quick_report(unpopulated_file, raise_on_error=True)


def test_validate_valid_finalized_quick_report(tmp_path: Path) -> None:
    valid_file = tmp_path / "QUICK REPORT" / "valid.docx"
    # Valid docx >= 1.0 MB with 10 media files
    _create_mock_docx(valid_file, media_count=10, target_size_bytes=1_200_000)

    result = validate_finalized_quick_report(valid_file)
    assert isinstance(result, PreFlightValidationResult)
    assert result.is_valid
    assert result.exists
    assert result.size_bytes >= MIN_FILE_SIZE_BYTES
    assert result.media_count == 10
    assert result.media_count >= MIN_MEDIA_COUNT
    assert result.error_message is None

    # Should not raise when raise_on_error=True
    result_raised = validate_finalized_quick_report(valid_file, raise_on_error=True)
    assert result_raised.is_valid


def test_validate_non_docx_extension(tmp_path: Path) -> None:
    non_docx_file = tmp_path / "QUICK REPORT" / "report.zip"
    _create_mock_docx(non_docx_file, media_count=10, target_size_bytes=1_200_000)

    result = validate_finalized_quick_report(non_docx_file)
    assert not result.is_valid
    assert result.exists
    assert result.error_message is not None
    assert "not a .docx document" in result.error_message

    with pytest.raises(PreFlightValidationError):
        validate_finalized_quick_report(non_docx_file, raise_on_error=True)


def test_validate_non_image_media_files_ignored(tmp_path: Path) -> None:
    target_file = tmp_path / "QUICK REPORT" / "non_images.docx"
    target_file.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target_file, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        # 4 real images
        for i in range(4):
            zf.writestr(f"word/media/image{i + 1}.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100)
        # 4 non-images in word/media/
        zf.writestr("word/media/data.txt", b"plain text")
        zf.writestr("word/media/script.js", b"console.log()")
        zf.writestr("word/media/binary.bin", b"\x00" * 50)
        zf.writestr("word/media/subfolder/", b"")
        # Pad to reach 1.2 MB
        zf.writestr("word/document.xml", b"<w:document>" + b"a" * 1_200_000 + b"</w:document>")

    result = validate_finalized_quick_report(target_file)
    assert not result.is_valid
    assert result.media_count == 4  # only the 4 PNGs counted
    assert result.error_message is not None
    assert "insufficient media files" in result.error_message.lower()

