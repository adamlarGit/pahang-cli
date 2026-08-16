"""Ingest MSMS CSV Workflow implementation for Pahang CLI.

Ingests raw client CSV files from MSMS/RAW DATA/ into MSMS/TO BE FILLED/ with
canonical naming (DD-MM-YYYY_NNN.csv), SHA-256 deduplication, and schema validation.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path
import re
import shutil
from typing import Sequence

from src.project.environment import ProjectEnvironment
from src.workflows.models import IngestMsmsCsvRequest, IngestMsmsCsvResult


def extract_date_from_filename(filename: str) -> str:
    """Extract and normalize date from raw CSV filename to DD-MM-YYYY format.

    Supported patterns:
    - DD-MM-YYYY, DD_MM_YYYY, DD.MM.YYYY, DD/MM/YYYY
    - YYYY-MM-DD, YYYY_MM_DD, YYYY.MM.DD, YYYY/MM/DD
    - DDMMYYYY (8 consecutive digits)
    - YYYYMMDD (8 consecutive digits)

    Raises:
        ValueError: If no valid date can be extracted from filename.
    """
    stem = Path(filename).stem

    # Pattern 1: DD-MM-YYYY with various separators (-, _, ., /)
    match_ddmmyyyy = re.search(r"(?<!\d)(\d{2})[-_./](\d{2})[-_./](\d{4})(?!\d)", stem)
    if match_ddmmyyyy:
        day, month, year = int(match_ddmmyyyy.group(1)), int(match_ddmmyyyy.group(2)), int(match_ddmmyyyy.group(3))
        try:
            d = date(year, month, day)
            return f"{d.day:02d}-{d.month:02d}-{d.year:04d}"
        except ValueError:
            pass

    # Pattern 2: YYYY-MM-DD with various separators
    match_yyyymmdd = re.search(r"(?<!\d)(\d{4})[-_./](\d{2})[-_./](\d{2})(?!\d)", stem)
    if match_yyyymmdd:
        year, month, day = int(match_yyyymmdd.group(1)), int(match_yyyymmdd.group(2)), int(match_yyyymmdd.group(3))
        try:
            d = date(year, month, day)
            return f"{d.day:02d}-{d.month:02d}-{d.year:04d}"
        except ValueError:
            pass

    # Pattern 3: 8 consecutive digits DDMMYYYY
    matches_8digits = re.findall(r"(?<!\d)(\d{8})(?!\d)", stem)
    for m in matches_8digits:
        # Try DDMMYYYY
        day, month, year = int(m[:2]), int(m[2:4]), int(m[4:])
        if 2000 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31:
            try:
                d = date(year, month, day)
                return f"{d.day:02d}-{d.month:02d}-{d.year:04d}"
            except ValueError:
                pass
        # Try YYYYMMDD
        year, month, day = int(m[:4]), int(m[4:6]), int(m[6:])
        if 2000 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31:
            try:
                d = date(year, month, day)
                return f"{d.day:02d}-{d.month:02d}-{d.year:04d}"
            except ValueError:
                pass

    raise ValueError(f"Could not extract valid date from filename: '{filename}'")


class IngestMsmsCsvPreflightGuard:
    """Pre-flight resource guard stage for Ingest MSMS CSV workflow."""

    def validate(self, environment: ProjectEnvironment) -> None:
        """Validate environmental preconditions before reading CSVs."""
        raw_files = environment.storage.list_msms_raw_csv_files()
        raw_dir = environment.storage.get_msms_raw_data_dir()

        if not raw_files:
            if not raw_dir.exists() or not raw_dir.is_dir():
                raise FileNotFoundError(f"MSMS RAW DATA directory not found: {raw_dir}")
            raise FileNotFoundError(f"No CSV files found in RAW DATA directory: {raw_dir}")

        to_be_filled_dir = environment.storage.get_msms_to_be_filled_dir()
        environment.storage.ensure_directory(to_be_filled_dir)


class IngestMsmsCsvExtractor:
    """Reading and schema validation stage for Ingest MSMS CSV workflow."""

    REQUIRED_HEADERS = ("WONUM", "TNBLOCATION", "METERNAME")

    def extract_files(self, source: Path | Sequence[Path]) -> list[Path]:
        """Discover and validate CSV schema for all files in source directory or sequence."""
        if isinstance(source, Path):
            if not source.exists() or not source.is_dir():
                return []
            files = sorted([p for p in source.glob("*.csv") if p.is_file()])
        else:
            files = sorted([p for p in source if p.is_file()])

        if not files:
            return []

        for filepath in files:
            self._validate_csv_schema(filepath)

        return files

    def _validate_csv_schema(self, filepath: Path) -> None:
        """Verify that required headers exist in the CSV file."""
        headers = self._read_headers(filepath)
        normalized_headers = {h.strip().upper() for h in headers if h}

        missing = [req for req in self.REQUIRED_HEADERS if req not in normalized_headers]
        if missing:
            raise ValueError(
                f"Missing required CSV headers {missing} in file: {filepath.name}. "
                f"Expected headers containing {list(self.REQUIRED_HEADERS)}, but found {headers}."
            )

    def _read_headers(self, filepath: Path) -> list[str]:
        """Read CSV headers with encoding fallback."""
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                with open(filepath, mode="r", encoding=encoding, newline="") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row and any(cell.strip() for cell in row):
                            return row
                return []
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Could not decode CSV file: {filepath.name}")


class IngestMsmsCsvFilter:
    """Content-hash deduplication filter stage for Ingest MSMS CSV workflow."""

    def filter_files(
        self, raw_files: Sequence[Path], to_be_filled_dir: Path
    ) -> tuple[list[Path], list[Path]]:
        """Filter out duplicate CSV files using SHA-256 content hashing.

        Returns:
            (files_to_process, duplicate_files)
        """
        existing_hashes = self._get_existing_hashes(to_be_filled_dir, exclude_files=raw_files)
        to_process: list[Path] = []
        duplicates: list[Path] = []

        for raw_file in raw_files:
            file_hash = self._compute_sha256(raw_file)
            if file_hash in existing_hashes:
                duplicates.append(raw_file)
            else:
                existing_hashes.add(file_hash)
                to_process.append(raw_file)

        return to_process, duplicates

    def _get_existing_hashes(
        self, directory: Path, exclude_files: Sequence[Path] = ()
    ) -> set[str]:
        """Compute SHA-256 hashes of all existing CSVs in directory, excluding candidate files."""
        exclude_set = {p.resolve() for p in exclude_files}
        hashes: set[str] = set()
        if not directory.exists():
            return hashes
        for p in directory.glob("*.csv"):
            if p.is_file() and p.resolve() not in exclude_set:
                hashes.add(self._compute_sha256(p))
        return hashes

    @staticmethod
    def _compute_sha256(filepath: Path) -> str:
        """Compute SHA-256 hash of file content."""
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()


@dataclass(frozen=True)
class IngestMsmsCsvPlan:
    """Execution plan for moving and canonicalizing CSV files."""

    mappings: tuple[tuple[Path, Path], ...]
    duplicate_files: tuple[Path, ...]


class IngestMsmsCsvTransformer:
    """Transformation stage mapping source files to canonical target paths."""

    def build_plan(
        self,
        files: Sequence[Path],
        to_be_filled_dir: Path,
        duplicates: Sequence[Path] = (),
    ) -> IngestMsmsCsvPlan:
        """Build mapping of source paths to canonical target paths DD-MM-YYYY_NNN.csv."""
        date_indices = self._scan_existing_indices(to_be_filled_dir, exclude_files=files)
        mappings: list[tuple[Path, Path]] = []

        for file_path in files:
            date_str = extract_date_from_filename(file_path.name)
            current_idx = date_indices.get(date_str, 0) + 1
            date_indices[date_str] = current_idx

            target_filename = f"{date_str}_{current_idx:03d}.csv"
            target_path = to_be_filled_dir / target_filename
            mappings.append((file_path, target_path))

        return IngestMsmsCsvPlan(
            mappings=tuple(mappings),
            duplicate_files=tuple(duplicates),
        )

    def _scan_existing_indices(
        self, directory: Path, exclude_files: Sequence[Path] = ()
    ) -> dict[str, int]:
        """Scan directory to find max sequence index for each date prefix, excluding candidate files."""
        exclude_set = {p.resolve() for p in exclude_files}
        indices: dict[str, int] = {}
        if not directory.exists():
            return indices

        pattern = re.compile(r"^(\d{2}-\d{2}-\d{4})_(\d{3})\.csv$", re.IGNORECASE)
        for p in directory.glob("*.csv"):
            if not p.is_file() or p.resolve() in exclude_set:
                continue
            m = pattern.match(p.name)
            if m:
                dt_str, idx_str = m.group(1), m.group(2)
                idx = int(idx_str)
                if idx > indices.get(dt_str, 0):
                    indices[dt_str] = idx
            else:
                # Handle unindexed canonical date file like 01-08-2026.csv
                m_single = re.match(r"^(\d{2}-\d{2}-\d{4})\.csv$", p.name, re.IGNORECASE)
                if m_single:
                    dt_str = m_single.group(1)
                    if indices.get(dt_str, 0) < 1:
                        indices[dt_str] = 1

        return indices


class IngestMsmsCsvLoader:
    """Loader stage executing file movements."""

    def load(self, plan: IngestMsmsCsvPlan) -> list[Path]:
        """Move normalized CSV files from RAW DATA into TO BE FILLED."""
        ingested: list[Path] = []
        for src, dst in plan.mappings:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != dst.resolve():
                shutil.move(str(src), str(dst))
            ingested.append(dst)
        return ingested


class IngestMsmsCsvAuditor:
    """Auditing stage verifying file integrity and reporting telemetry."""

    def audit(
        self, plan: IngestMsmsCsvPlan, ingested_paths: Sequence[Path]
    ) -> IngestMsmsCsvResult:
        """Verify output integrity and return workflow result."""
        for p in ingested_paths:
            if not p.exists():
                raise RuntimeError(f"Target CSV file does not exist after ingestion: {p}")
            if p.stat().st_size == 0:
                raise RuntimeError(f"Target CSV file is empty (0 bytes) after ingestion: {p}")

        return IngestMsmsCsvResult(
            files_ingested=len(ingested_paths),
            files_skipped_duplicate=len(plan.duplicate_files),
            ingested_files=tuple(ingested_paths),
            skipped_files=tuple(plan.duplicate_files),
        )


class IngestMsmsCsvWorkflow:
    """6-stage ETL workflow for ingesting raw client CSVs into TO BE FILLED."""

    def __init__(
        self,
        preflight_guard: IngestMsmsCsvPreflightGuard | None = None,
        extractor: IngestMsmsCsvExtractor | None = None,
        filter_stage: IngestMsmsCsvFilter | None = None,
        transformer: IngestMsmsCsvTransformer | None = None,
        loader: IngestMsmsCsvLoader | None = None,
        auditor: IngestMsmsCsvAuditor | None = None,
    ) -> None:
        self.preflight_guard = preflight_guard or IngestMsmsCsvPreflightGuard()
        self.extractor = extractor or IngestMsmsCsvExtractor()
        self.filter_stage = filter_stage or IngestMsmsCsvFilter()
        self.transformer = transformer or IngestMsmsCsvTransformer()
        self.loader = loader or IngestMsmsCsvLoader()
        self.auditor = auditor or IngestMsmsCsvAuditor()

    def execute(
        self, environment: ProjectEnvironment, request: IngestMsmsCsvRequest | None = None
    ) -> IngestMsmsCsvResult:
        """Execute the Ingest MSMS CSV workflow."""
        req = request or IngestMsmsCsvRequest()
        if req.progress_sink:
            req.progress_sink("Validating MSMS RAW DATA directory...")

        self.preflight_guard.validate(environment)

        raw_csv_files = environment.storage.list_msms_raw_csv_files()
        raw_dir = environment.storage.get_msms_raw_data_dir()
        to_be_filled_dir = environment.storage.get_msms_to_be_filled_dir()

        if req.progress_sink:
            request_sink = req.progress_sink
            request_sink(f"Extracting and validating CSV files from {raw_dir}...")

        raw_files = self.extractor.extract_files(raw_csv_files if raw_csv_files else raw_dir)

        if req.progress_sink:
            req.progress_sink(f"Filtering duplicate files ({len(raw_files)} candidate(s))...")

        to_process, duplicates = self.filter_stage.filter_files(raw_files, to_be_filled_dir)

        if req.progress_sink:
            req.progress_sink(
                f"Building canonical paths for {len(to_process)} file(s) ({len(duplicates)} duplicate(s) skipped)..."
            )

        plan = self.transformer.build_plan(to_process, to_be_filled_dir, duplicates=duplicates)

        if req.progress_sink:
            req.progress_sink(f"Moving {len(plan.mappings)} normalized CSV file(s) to {to_be_filled_dir}...")

        ingested_paths = self.loader.load(plan)

        result = self.auditor.audit(plan, ingested_paths)

        if req.progress_sink:
            req.progress_sink(
                f"Ingestion completed: {result.files_ingested} file(s) ingested, {result.files_skipped_duplicate} duplicate(s) skipped."
            )

        return result

