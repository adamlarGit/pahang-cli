"""Pre-Flight Integrity Validator and File Filtering for Post-Processing Pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from src.project.storage import extract_numerical_prefix

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment

logger = logging.getLogger(__name__)


class PreFlightValidationError(ValueError):
    """Raised when pre-flight file count integrity validation fails before post-processing."""

    def __init__(
        self,
        message: str,
        *,
        date_folder: str,
        quick_report_count: int,
        testsheet_count: int,
        raw_material_count: int | None = None,
        quick_reports: Sequence[Path] = (),
        testsheets: Sequence[Path] = (),
        raw_materials: Sequence[Path] = (),
    ) -> None:
        super().__init__(message)
        self.date_folder = date_folder
        self.quick_report_count = quick_report_count
        self.testsheet_count = testsheet_count
        self.raw_material_count = raw_material_count
        self.quick_reports = tuple(quick_reports)
        self.testsheets = tuple(testsheets)
        self.raw_materials = tuple(raw_materials)


@dataclass(frozen=True)
class PreFlightValidationResult:
    """Structured result summary of a pre-flight integrity check."""

    date_folder: str
    quick_report_count: int
    testsheet_count: int
    raw_material_count: int | None
    quick_reports: tuple[Path, ...]
    testsheets: tuple[Path, ...]
    raw_materials: tuple[Path, ...]

    @property
    def is_valid(self) -> bool:
        """Return True if counts match and are strictly greater than 0."""
        if self.quick_report_count <= 0 or self.testsheet_count <= 0:
            return False
        if self.quick_report_count != self.testsheet_count:
            return False
        if self.raw_material_count is not None and self.raw_material_count != self.quick_report_count:
            return False
        return True


def _sort_by_numerical_prefix(paths: Sequence[Path]) -> list[Path]:
    """Sort path items by leading numerical prefix or fallback to lowercase name."""

    def sort_key(p: Path) -> tuple[int, str]:
        try:
            return (extract_numerical_prefix(p.name), p.name.lower())
        except ValueError:
            try:
                return (extract_numerical_prefix(p.name, split_char="_"), p.name.lower())
            except ValueError:
                return (999999, p.name.lower())

    return sorted(paths, key=sort_key)


def filter_valid_quick_reports(directory: Path | str) -> list[Path]:
    """Discover and filter valid Word quick report (.docx) documents in a directory.

    Strictly ignores:
    - Office temporary lock files starting with `~$`
    - Hidden files starting with `.`
    - Subdirectories
    - Non-.docx files
    """
    target_dir = Path(directory).expanduser().resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        return []

    valid_files = [
        p
        for p in target_dir.iterdir()
        if p.is_file()
        and not p.name.startswith("~$")
        and not p.name.startswith(".")
        and p.suffix.lower() == ".docx"
    ]
    return _sort_by_numerical_prefix(valid_files)


def filter_valid_testsheets(directory: Path | str) -> list[Path]:
    """Discover and filter valid Excel testsheet (.xlsx) workbooks in a directory.

    Strictly ignores:
    - All subdirectories (such as `processed_testsheet/`, `UNSORTED RAW DATA/`, `pdf/`, etc.)
    - Office temporary lock files starting with `~$`
    - Hidden files starting with `.`
    - Non-.xlsx files (.docx, .pdf, .txt, etc.)
    """
    target_dir = Path(directory).expanduser().resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        return []

    valid_files = [
        p
        for p in target_dir.iterdir()
        if p.is_file()
        and not p.name.startswith("~$")
        and not p.name.startswith(".")
        and p.suffix.lower() == ".xlsx"
    ]
    return _sort_by_numerical_prefix(valid_files)


def filter_valid_raw_materials(directory: Path | str) -> list[Path]:
    """Discover and filter valid substation subdirectories in a RAW MATERIAL date directory.

    Strictly ignores:
    - System or hidden directories starting with `.`
    - Temporary directories starting with `~$`
    - Auxiliary directories starting with `processed_`
    - Files
    """
    target_dir = Path(directory).expanduser().resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        return []

    valid_dirs = [
        p
        for p in target_dir.iterdir()
        if p.is_dir()
        and not p.name.startswith("~$")
        and not p.name.startswith(".")
        and not p.name.startswith("processed_")
    ]
    return _sort_by_numerical_prefix(valid_dirs)


def resolve_date_folder_paths(
    env: ProjectEnvironment,
    date_folder: str | Path,
) -> tuple[Path, Path, Path]:
    """Resolve physical (TESTSHEET, QUICK REPORT, RAW MATERIAL) directory paths for a target date.

    Supports:
    - Absolute directory paths
    - Relative nested paths (e.g. 'TEMERLOH/08. AUGUST/28-08-2026')
    - Bare date strings (e.g. '28-08-2026') with recursive hierarchy discovery across workspace
    """
    ts_root = env.get_testsheet_dir()
    qr_root = env.get_quick_report_dir()
    raw_root = env.get_raw_material_dir()

    # 1. If date_folder is an absolute Path
    if isinstance(date_folder, Path) and date_folder.is_absolute():
        try:
            rel = date_folder.relative_to(ts_root)
            return (date_folder, qr_root / rel, raw_root / rel)
        except ValueError:
            pass
        try:
            rel = date_folder.relative_to(qr_root)
            return (ts_root / rel, date_folder, raw_root / rel)
        except ValueError:
            pass
        try:
            rel = date_folder.relative_to(raw_root)
            return (ts_root / rel, qr_root / rel, date_folder)
        except ValueError:
            pass

    date_str = str(date_folder).strip().strip('"').strip("'")
    target_p = Path(date_str)

    # 2. Check direct flat / relative subpath first
    candidate_ts = ts_root / target_p
    candidate_qr = qr_root / target_p
    candidate_raw = raw_root / target_p
    if candidate_ts.exists() or candidate_qr.exists():
        return (candidate_ts, candidate_qr, candidate_raw)

    # 3. Recursive lookup under TESTSHEET/ for matching date folder name
    target_name = target_p.name
    if ts_root.exists() and ts_root.is_dir():
        for sub in ts_root.rglob("*"):
            if sub.is_dir() and sub.name == target_name and not sub.name.startswith((".", "~$", "processed_")):
                rel = sub.relative_to(ts_root)
                return (sub, qr_root / rel, raw_root / rel)

    # 4. Recursive lookup under QUICK REPORT/ if not found under TESTSHEET/
    if qr_root.exists() and qr_root.is_dir():
        for sub in qr_root.rglob("*"):
            if sub.is_dir() and sub.name == target_name and not sub.name.startswith((".", "~$", "processed_")):
                rel = sub.relative_to(qr_root)
                return (ts_root / rel, sub, raw_root / rel)

    # Fallback to direct path
    return (candidate_ts, candidate_qr, candidate_raw)


def validate_postprocessing_preflight(
    env: ProjectEnvironment,
    date_folder: str | Path,
    *,
    ts_dir: Path | None = None,
    qr_dir: Path | None = None,
    raw_dir: Path | None = None,
) -> PreFlightValidationResult:
    """Validate file count integrity across QUICK REPORT, TESTSHEET, and RAW MATERIAL directories.

    Raises:
        PreFlightValidationError: When directories are missing, empty, or file counts mismatch.
    """
    if isinstance(date_folder, Path):
        date_str = date_folder.name if date_folder.is_absolute() else str(date_folder)
    else:
        date_str = str(date_folder).strip().strip('"').strip("'")

    if ts_dir is None or qr_dir is None or raw_dir is None:
        resolved_ts, resolved_qr, resolved_raw = resolve_date_folder_paths(env, date_folder)
        ts_dir = ts_dir or resolved_ts
        qr_dir = qr_dir or resolved_qr
        raw_dir = raw_dir or resolved_raw

    if not qr_dir.exists() or not qr_dir.is_dir():
        raise PreFlightValidationError(
            f"Pre-flight integrity check failed for date folder '{date_str}': "
            f"QUICK REPORT directory does not exist at '{qr_dir}'.",
            date_folder=date_str,
            quick_report_count=0,
            testsheet_count=0,
            raw_material_count=None,
        )

    if not ts_dir.exists() or not ts_dir.is_dir():
        quick_reports_pre = filter_valid_quick_reports(qr_dir)
        raise PreFlightValidationError(
            f"Pre-flight integrity check failed for date folder '{date_str}': "
            f"TESTSHEET directory does not exist at '{ts_dir}'.",
            date_folder=date_str,
            quick_report_count=len(quick_reports_pre),
            testsheet_count=0,
            raw_material_count=None,
            quick_reports=quick_reports_pre,
        )

    quick_reports = filter_valid_quick_reports(qr_dir)
    testsheets = filter_valid_testsheets(ts_dir)

    raw_materials: list[Path] = []
    raw_material_count: int | None = None
    if raw_dir.exists() and raw_dir.is_dir():
        raw_materials = filter_valid_raw_materials(raw_dir)
        raw_material_count = len(raw_materials)

    qr_count = len(quick_reports)
    ts_count = len(testsheets)

    if qr_count == 0:
        raise PreFlightValidationError(
            f"Pre-flight integrity check failed for date folder '{date_str}': "
            f"QUICK REPORT directory contains 0 valid .docx files at '{qr_dir}'.",
            date_folder=date_str,
            quick_report_count=0,
            testsheet_count=ts_count,
            raw_material_count=raw_material_count,
            quick_reports=quick_reports,
            testsheets=testsheets,
            raw_materials=raw_materials,
        )

    if ts_count == 0:
        raise PreFlightValidationError(
            f"Pre-flight integrity check failed for date folder '{date_str}': "
            f"TESTSHEET directory contains 0 valid .xlsx files at '{ts_dir}'.",
            date_folder=date_str,
            quick_report_count=qr_count,
            testsheet_count=0,
            raw_material_count=raw_material_count,
            quick_reports=quick_reports,
            testsheets=testsheets,
            raw_materials=raw_materials,
        )

    if qr_count != ts_count:
        qr_names = [p.name for p in quick_reports]
        ts_names = [p.name for p in testsheets]
        raise PreFlightValidationError(
            f"Pre-flight integrity check failed for date folder '{date_str}': "
            f"Count mismatch detected between QUICK REPORT ({qr_count}) and TESTSHEET ({ts_count}).\n"
            f"  Quick Reports ({qr_count}): {qr_names}\n"
            f"  Testsheets ({ts_count}): {ts_names}",
            date_folder=date_str,
            quick_report_count=qr_count,
            testsheet_count=ts_count,
            raw_material_count=raw_material_count,
            quick_reports=quick_reports,
            testsheets=testsheets,
            raw_materials=raw_materials,
        )

    if raw_material_count is not None and raw_material_count != qr_count:
        raw_names = [p.name for p in raw_materials]
        raise PreFlightValidationError(
            f"Pre-flight integrity check failed for date folder '{date_str}': "
            f"Count mismatch detected between RAW MATERIAL ({raw_material_count}) and "
            f"QUICK REPORT / TESTSHEET ({qr_count}).\n"
            f"  Raw Materials ({raw_material_count}): {raw_names}",
            date_folder=date_str,
            quick_report_count=qr_count,
            testsheet_count=ts_count,
            raw_material_count=raw_material_count,
            quick_reports=quick_reports,
            testsheets=testsheets,
            raw_materials=raw_materials,
        )

    return PreFlightValidationResult(
        date_folder=date_str,
        quick_report_count=qr_count,
        testsheet_count=ts_count,
        raw_material_count=raw_material_count,
        quick_reports=tuple(quick_reports),
        testsheets=tuple(testsheets),
        raw_materials=tuple(raw_materials),
    )
