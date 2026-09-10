"""Pre-Flight Integrity Validator for Finalized Quick Report (Ticket #21 / T1.2)."""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum file size floor (1.0 MB = 1024 * 1024 bytes) per D17
MIN_FILE_SIZE_BYTES: int = 1_048_576

# Minimum media count in word/media/ ensuring inspector photos are populated per D17
MIN_MEDIA_COUNT: int = 8


# Supported OpenXML image file extensions inside word/media/
VALID_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".tif",
    ".emf",
    ".wmf",
    ".gif",
})


class PreFlightValidationError(ValueError):
    """Raised when pre-flight integrity validation fails for a finalized Quick Report docx."""

    def __init__(
        self,
        message: str,
        *,
        result: PreFlightValidationResult | None = None,
    ) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class PreFlightValidationResult:
    """Structured telemetry result of pre-flight integrity check on a Quick Report."""

    path: Path
    is_valid: bool
    exists: bool = False
    size_bytes: int = 0
    media_count: int = 0
    error_message: str | None = None


def resolve_quick_report_path(
    base_path: Path | str,
    station: str,
    month: str,
    date: str,
    stem: str,
) -> Path:
    """Resolve physical path to QUICK REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.docx."""
    base = Path(base_path)
    clean_stem = stem.strip()
    filename = clean_stem if clean_stem.lower().endswith(".docx") else f"{clean_stem}.docx"
    return base / "QUICK REPORT" / station / month / date / filename


def validate_finalized_quick_report(
    path: Path | str,
    *,
    min_size_bytes: int = MIN_FILE_SIZE_BYTES,
    min_media_count: int = MIN_MEDIA_COUNT,
    raise_on_error: bool = False,
) -> PreFlightValidationResult:
    """Validate existence, size floor, and media count of finalized Quick Report docx.

    Checks:
    1. File presence on disk and .docx extension.
    2. File size floor >= 1.0 MB, rejecting empty or unpopulated templates.
    3. Image count >= 8 in `word/media/` via standard zipfile inspection.

    Args:
        path: Direct Path or string to the target Quick Report .docx file.
        min_size_bytes: Minimum file size floor in bytes (default: 1,048,576 = 1.0 MB).
        min_media_count: Minimum image count in word/media/ (default: 8).
        raise_on_error: If True, raises PreFlightValidationError on validation failure.

    Returns:
        Structured PreFlightValidationResult with diagnostics.

    Raises:
        PreFlightValidationError: If raise_on_error is True and validation fails.
    """
    target_path = Path(path).expanduser().resolve()

    def _fail(msg: str, exists: bool = True, size: int = 0, media: int = 0) -> PreFlightValidationResult:
        logger.warning(msg)
        res = PreFlightValidationResult(
            path=target_path,
            is_valid=False,
            exists=exists,
            size_bytes=size,
            media_count=media,
            error_message=msg,
        )
        if raise_on_error:
            raise PreFlightValidationError(msg, result=res)
        return res

    # 1. Validate file presence
    if not target_path.exists() or not target_path.is_file():
        return _fail(
            f"Finalized Quick Report does not exist at '{target_path}'.",
            exists=False,
            size=0,
            media=0,
        )

    # 2. Validate .docx extension
    if target_path.suffix.lower() != ".docx":
        return _fail(
            f"Finalized Quick Report at '{target_path}' is not a .docx document (suffix: '{target_path.suffix}').",
            exists=True,
            size=target_path.stat().st_size,
            media=0,
        )

    size_bytes = target_path.stat().st_size

    # Inspect media count if valid zip archive (best-effort for full diagnostics)
    media_count = 0
    zip_error: str | None = None
    try:
        with zipfile.ZipFile(target_path, "r") as zf:
            media_count = sum(
                1
                for name in zf.namelist()
                if name.startswith("word/media/")
                and not name.endswith("/")
                and Path(name).suffix.lower() in VALID_IMAGE_EXTENSIONS
            )
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError) as exc:
        zip_error = str(exc)

    # 3. Enforce file size floor >= 1.0 MB
    if size_bytes < min_size_bytes:
        size_mb = size_bytes / (1024 * 1024)
        floor_mb = min_size_bytes / (1024 * 1024)
        return _fail(
            f"Finalized Quick Report at '{target_path}' failed file size floor: "
            f"{size_bytes:,} bytes ({size_mb:.2f} MB) < {min_size_bytes:,} bytes ({floor_mb:.1f} MB). "
            f"Template is empty or unpopulated.",
            exists=True,
            size=size_bytes,
            media=media_count,
        )

    # 4. Enforce zip archive integrity
    if zip_error is not None:
        return _fail(
            f"Finalized Quick Report at '{target_path}' is not a valid docx/zip archive: {zip_error}",
            exists=True,
            size=size_bytes,
            media=0,
        )

    # 5. Enforce media count floor >= 8
    if media_count < min_media_count:
        return _fail(
            f"Finalized Quick Report at '{target_path}' contains insufficient media files: "
            f"media count {media_count} < minimum {min_media_count} in 'word/media/'. "
            f"Inspector photos have not been populated.",
            exists=True,
            size=size_bytes,
            media=media_count,
        )

    # All checks passed
    logger.debug(
        "Finalized Quick Report at '%s' passed pre-flight integrity check (%d bytes, %d media files).",
        target_path,
        size_bytes,
        media_count,
    )
    return PreFlightValidationResult(
        path=target_path,
        is_valid=True,
        exists=True,
        size_bytes=size_bytes,
        media_count=media_count,
        error_message=None,
    )
