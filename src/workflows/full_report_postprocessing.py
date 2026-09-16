"""Full Report post-processing workflow orchestrator converting .docx to PDF and appending testsheet.

Decisions and Architectural Policies Enforced:
- D42: Decoupled two-stage architecture: Stage 1 creates .docx, Stage 2 (this workflow)
  converts .docx to .pdf and merges testsheet PDF into the final client deliverable.
- D43: Testsheet PDF reuse & strict fail-fast: directly reuses pre-existing testsheet PDF
  from processed_testsheet/pdf/<stem>.pdf. Fails fast with clear diagnostic if missing.
- D45: Uniform virtual printer conversion: configured with configure_uniform_printer()
  (Adobe PDF / Microsoft Print to PDF) and Word COM ExportAsFixedFormat to preserve exact A4 metrics.
- SubstationIsolatedBatchResiliencePolicy: isolates individual substation failures during batch execution
  without aborting the remaining batch run.
- Seam: Swappable DocumentConverter (ComDocumentConverter vs FakeDocumentConverter).
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
import io
import logging
from pathlib import Path
import re
import time
from typing import TYPE_CHECKING, Any, Callable, Iterator, Sequence

from src.core.normalizers import format_month_folder
from src.postprocessing.converters import (
    BatchComSession,
    ComDocumentConverter,
    DocumentConverter,
    FakeDocumentConverter,
    batch_com_session,
    configure_uniform_printer,
)
from src.project.storage import extract_numerical_prefix
from src.quick_report.extractor import DAILY_DATE_FOLDER_PATTERN

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment

logger = logging.getLogger(__name__)

PostProcessingTarget = (
    Path
    | str
    | Sequence[Path | str]
    | None
)
ProgressSink = Callable[[str], None]


# ==============================================================================
# 1. Pre-Flight Testsheet PDF Validation (D43)
# ==============================================================================

class TestsheetPdfNotFoundError(FileNotFoundError):
    """Raised when pre-existing testsheet PDF is missing in processed_testsheet/pdf/."""

    __test__ = False


@dataclass(frozen=True)
class TestsheetPdfValidationResult:
    """Structured telemetry outcome of testsheet PDF presence validation."""

    path: Path | None
    is_valid: bool
    exists: bool = False
    size_bytes: int = 0
    error_message: str | None = None
    __test__ = False


def validate_processed_testsheet_pdf(
    path: Path | str | None,
    *,
    stem: str = "",
    raise_on_error: bool = False,
) -> TestsheetPdfValidationResult:
    """Validate existence and non-zero byte size of pre-existing testsheet PDF per D43.

    Args:
        path: Path to the testsheet PDF in processed_testsheet/pdf/, or None if unresolved.
        stem: Substation stem name for diagnostic error messaging.
        raise_on_error: If True, raises TestsheetPdfNotFoundError on validation failure.

    Returns:
        TestsheetPdfValidationResult with diagnostics.

    Raises:
        TestsheetPdfNotFoundError: If raise_on_error is True and validation fails.
    """
    stem_label = f" for '{stem}'" if stem else ""

    if path is None:
        err_msg = (
            f"Pre-existing testsheet PDF missing in processed_testsheet/pdf/{stem_label}. "
            f"Please run Quick Report post-processing first to generate the signed testsheet PDF."
        )
        if raise_on_error:
            raise TestsheetPdfNotFoundError(err_msg)
        return TestsheetPdfValidationResult(
            path=None,
            is_valid=False,
            exists=False,
            size_bytes=0,
            error_message=err_msg,
        )

    target = Path(path).expanduser().resolve()
    if not target.exists() or not target.is_file():
        err_msg = (
            f"Pre-existing testsheet PDF missing in processed_testsheet/pdf/ at '{target}'{stem_label}. "
            f"Please run Quick Report post-processing first to generate the signed testsheet PDF."
        )
        if raise_on_error:
            raise TestsheetPdfNotFoundError(err_msg)
        return TestsheetPdfValidationResult(
            path=target,
            is_valid=False,
            exists=False,
            size_bytes=0,
            error_message=err_msg,
        )

    size = target.stat().st_size
    if size == 0:
        err_msg = (
            f"Pre-existing testsheet PDF at '{target}'{stem_label} is 0 bytes. "
            f"Please run Quick Report post-processing first to generate a valid testsheet PDF."
        )
        if raise_on_error:
            raise TestsheetPdfNotFoundError(err_msg)
        return TestsheetPdfValidationResult(
            path=target,
            is_valid=False,
            exists=True,
            size_bytes=0,
            error_message=err_msg,
        )

    return TestsheetPdfValidationResult(
        path=target,
        is_valid=True,
        exists=True,
        size_bytes=size,
        error_message=None,
    )


def _find_pdf_in_dirs(pdf_dirs: Sequence[Path], stem: str) -> Path | None:
    """Search directories with phased priority: exact -> numerical prefix -> clean name."""
    # Phase 1: Exact match
    for pdf_dir in pdf_dirs:
        exact_pdf = pdf_dir / f"{stem}.pdf"
        if exact_pdf.exists() and exact_pdf.is_file():
            return exact_pdf.resolve()

    # Phase 2: Numerical prefix match (e.g. "005." or "5.")
    try:
        prefix_num = extract_numerical_prefix(stem)
        prefix_pattern1 = f"{prefix_num:03d}."
        prefix_pattern2 = f"{prefix_num}."

        for pdf_dir in pdf_dirs:
            for candidate in pdf_dir.glob("*.pdf"):
                if candidate.name.startswith("~$") or candidate.name.startswith("."):
                    continue
                if candidate.name.startswith(prefix_pattern1) or candidate.name.startswith(prefix_pattern2):
                    return candidate.resolve()
    except ValueError:
        pass

    # Phase 3: Substation name match without defect suffix
    clean_name_match = re.sub(r"^\d+\.\s*", "", stem).strip()
    clean_name_match = re.sub(r"\s*\(.*?\)$", "", clean_name_match).strip().lower()
    if clean_name_match:
        for pdf_dir in pdf_dirs:
            for candidate in pdf_dir.glob("*.pdf"):
                if candidate.name.startswith("~$") or candidate.name.startswith("."):
                    continue
                if clean_name_match in candidate.name.lower():
                    return candidate.resolve()

    return None


def resolve_processed_testsheet_pdf_path(
    docx_path: Path,
    environment: ProjectEnvironment | None = None,
) -> Path | None:
    """Resolve physical path to the matching testsheet PDF under processed_testsheet/pdf/."""
    doc_p = Path(docx_path).resolve()
    stem = doc_p.stem

    # Extract metadata from folder structure: .../<STATION>/<MONTH>/<DATE>/<STEM>.docx
    date_str = doc_p.parent.name
    month = doc_p.parent.parent.name
    station = doc_p.parent.parent.parent.name

    # Collect candidate processed_testsheet roots
    def _collect_pdf_dirs(ts_dir: Path) -> list[Path]:
        if not ts_dir.exists() or not ts_dir.is_dir():
            return []
        dirs = [ts_dir / "pdf", ts_dir]
        try:
            for sub in ts_dir.iterdir():
                if sub.is_dir() and sub.name.lower() != "pdf":
                    dirs.append(sub)
                    for sub2 in sub.iterdir():
                        if sub2.is_dir():
                            dirs.append(sub2)
        except Exception:
            pass
        return [d for d in dirs if d.exists() and d.is_dir()]

    candidate_roots: list[Path] = []
    if environment is not None:
        ts_base = environment.get_testsheet_dir()
        candidate_roots.extend([
            ts_base / station / month / date_str / "processed_testsheet",
            ts_base / station / date_str / "processed_testsheet",
            ts_base / date_str / "processed_testsheet",
        ])
        if (ts_base / station / month).exists() and (ts_base / station / month).is_dir():
            for sub in (ts_base / station / month).iterdir():
                if sub.is_dir() and (sub / "processed_testsheet").is_dir():
                    candidate_roots.append(sub / "processed_testsheet")

        base_path = getattr(environment, "base_path", None)
        if base_path:
            candidate_roots.extend([
                Path(base_path) / "TESTSHEET" / station / month / date_str / "processed_testsheet",
                Path(base_path) / "TESTSHEET" / date_str / "processed_testsheet",
            ])
            ts_m = Path(base_path) / "TESTSHEET" / station / month
            if ts_m.exists() and ts_m.is_dir():
                for sub in ts_m.iterdir():
                    if sub.is_dir() and (sub / "processed_testsheet").is_dir():
                        candidate_roots.append(sub / "processed_testsheet")

    # Also check relative to testsheet parent if docx is adjacent
    for part in doc_p.parts:
        if part.upper() == "FULL REPORT":
            try:
                idx = doc_p.parts.index(part)
                ts_rel = Path(*doc_p.parts[:idx]) / "TESTSHEET" / Path(*doc_p.parts[idx + 1 : -1]) / "processed_testsheet"
                candidate_roots.append(ts_rel)
            except Exception:
                pass
            break

    candidate_pdf_dirs: list[Path] = []
    for root_dir in candidate_roots:
        for d in _collect_pdf_dirs(root_dir):
            if d not in candidate_pdf_dirs:
                candidate_pdf_dirs.append(d)

    # 1. Search candidate directories
    matched = _find_pdf_in_dirs(candidate_pdf_dirs, stem)
    if matched is not None:
        return matched

    # 2. Workspace-wide fallback across all processed_testsheet dirs under ts_base
    if environment is not None:
        ts_base = environment.get_testsheet_dir()
        if ts_base.exists() and ts_base.is_dir():
            fallback_dirs: list[Path] = []
            try:
                for pts in ts_base.rglob("processed_testsheet"):
                    for d in _collect_pdf_dirs(pts):
                        if d not in candidate_pdf_dirs and d not in fallback_dirs:
                            fallback_dirs.append(d)
            except Exception:
                pass

            return _find_pdf_in_dirs(fallback_dirs, stem)

    return None


# ==============================================================================
# 2. Telemetry and Result Dataclasses
# ==============================================================================

@dataclass(frozen=True)
class FullReportPostProcessingTelemetry:
    """Dry-run inspection data and pre-flight validation status for a single Full Report."""

    docx_path: Path
    testsheet_pdf_path: Path | None
    target_pdf_path: Path
    stem: str
    substation_number: int | None = None
    substation_name: str = ""
    station: str = ""
    month: str = ""
    date_str: str = ""
    is_testsheet_pdf_valid: bool = False
    validation_result: TestsheetPdfValidationResult | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def pe_number(self) -> int | None:
        """Alias for substation_number."""
        return self.substation_number

    @property
    def is_ready(self) -> bool:
        """Return True if testsheet PDF is valid and zero errors exist."""
        return self.is_testsheet_pdf_valid and len(self.errors) == 0


@dataclass(frozen=True)
class FullReportPostProcessingInspection:
    """Inspection outcome returned by inspect() across all target reports."""

    targets: tuple[FullReportPostProcessingTelemetry, ...]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __iter__(self) -> Iterator[FullReportPostProcessingTelemetry]:
        return iter(self.targets)

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(self, index: int) -> FullReportPostProcessingTelemetry:
        return self.targets[index]

    @property
    def ready_targets(self) -> tuple[FullReportPostProcessingTelemetry, ...]:
        return tuple(t for t in self.targets if t.is_ready)

    @property
    def unready_targets(self) -> tuple[FullReportPostProcessingTelemetry, ...]:
        return tuple(t for t in self.targets if not t.is_ready)

    @property
    def ready_count(self) -> int:
        return len(self.ready_targets)

    @property
    def total_count(self) -> int:
        return len(self.targets)

    @property
    def ready_to_process(self) -> bool:
        return len(self.errors) == 0 and self.ready_count > 0


@dataclass(frozen=True)
class FullReportPostProcessingResult:
    """Consolidated post-processing execution outcome returned by process()."""

    total_reports: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    deliverables: tuple[Path, ...] = ()
    telemetries: tuple[FullReportPostProcessingTelemetry, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    duration_seconds: float = 0.0

    @property
    def is_success(self) -> bool:
        """Return True if at least one report succeeded and zero errors occurred."""
        return len(self.errors) == 0 and self.succeeded_count > 0

    @property
    def is_successful(self) -> bool:
        """Standardized alias across workflow models."""
        return self.is_success

    @property
    def final_deliverables(self) -> tuple[Path, ...]:
        """Standardized alias across post-processing summary models."""
        return self.deliverables

    @property
    def generated_paths(self) -> tuple[Path, ...]:
        """Standardized alias across workflow batch results."""
        return self.deliverables


# ==============================================================================
# 3. Deep Module: FullReportPostProcessingWorkflow
# ==============================================================================

class FullReportPostProcessingWorkflow:
    """Deep module orchestrating Full Report Word-to-PDF conversion and testsheet PDF merge.

    Enforces:
    - D42: Decoupled two-stage execution (post-processing runs after docx finalization).
    - D43: Fail-fast pre-flight validation on testsheet PDF in processed_testsheet/pdf/.
    - D45: Uniform A4 virtual printer configuration via configure_uniform_printer().
    - SubstationIsolatedBatchResiliencePolicy: isolated failures during batch runs.
    """

    def __init__(self, converter: DocumentConverter | None = None) -> None:
        self._converter: DocumentConverter = converter or ComDocumentConverter()

    # --------------------------------------------------------------------------
    # Public API: inspect()
    # --------------------------------------------------------------------------

    def inspect(
        self,
        target: PostProcessingTarget,
        environment: ProjectEnvironment,
        *,
        station: str | Sequence[str] | None = None,
        progress_sink: ProgressSink | None = None,
    ) -> FullReportPostProcessingInspection:
        """Dry-run discovery and pre-flight validation with strictly ZERO disk writes or COM calls."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        if progress_sink:
            progress_sink("Discovering Full Report documents for post-processing inspection...")

        docx_files, warnings, errors = self._discover_docx_files(target, environment, station=station)
        if not docx_files:
            return FullReportPostProcessingInspection(
                targets=(),
                warnings=tuple(warnings),
                errors=tuple(errors),
            )

        telemetries: list[FullReportPostProcessingTelemetry] = []
        for idx, docx_path in enumerate(docx_files, start=1):
            if progress_sink:
                progress_sink(
                    f"[{idx}/{len(docx_files)}] Inspecting testsheet PDF for {docx_path.name}..."
                )
            telem = self._inspect_single_report(docx_path, environment)
            telemetries.append(telem)

        return FullReportPostProcessingInspection(
            targets=tuple(telemetries),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    # --------------------------------------------------------------------------
    # Public API: process() / execute()
    # --------------------------------------------------------------------------

    def process(
        self,
        target: PostProcessingTarget,
        environment: ProjectEnvironment,
        *,
        station: str | Sequence[str] | None = None,
        progress_sink: ProgressSink | None = None,
        fail_fast: bool = False,
        output_dir: Path | str | None = None,
        com_session: Any = None,
    ) -> FullReportPostProcessingResult:
        """Execute Full Report post-processing: validate testsheet -> convert .docx -> merge PDFs.

        Resilience:
        SubstationIsolatedBatchResiliencePolicy isolates failures per report,
        allowing valid reports to convert and merge successfully even if others fail.
        """
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        start_time = time.time()

        if progress_sink:
            progress_sink("Discovering Full Report documents for post-processing...")

        docx_files, warnings, errors = self._discover_docx_files(target, environment, station=station)
        if not docx_files:
            if not errors:
                errors.append(f"No Full Report documents found for target: {target}")
            return FullReportPostProcessingResult(
                total_reports=0,
                succeeded_count=0,
                failed_count=0,
                deliverables=(),
                telemetries=(),
                warnings=tuple(warnings),
                errors=tuple(errors),
                duration_seconds=time.time() - start_time,
            )

        # Step 1: Pre-flight validation across all target documents
        telemetries: list[FullReportPostProcessingTelemetry] = []
        valid_targets: list[tuple[Path, Path, Path]] = []  # (docx_path, testsheet_pdf, deliverable_pdf)

        for docx_path in docx_files:
            telem = self._inspect_single_report(docx_path, environment, output_dir=output_dir)
            telemetries.append(telem)

            if not telem.is_ready:
                err_msg = telem.errors[0] if telem.errors else f"Validation failed for {docx_path.name}"
                if fail_fast:
                    raise TestsheetPdfNotFoundError(err_msg)
                errors.append(err_msg)
                continue

            assert telem.testsheet_pdf_path is not None
            valid_targets.append((docx_path, telem.testsheet_pdf_path, telem.target_pdf_path))

        # Step 2: Establish shared BatchComSession if ComDocumentConverter is used
        deliverables: list[Path] = []
        session_cm = self._establish_batch_session(com_session)

        with session_cm as session:
            word_app = getattr(session, "word_app", None)
            try:
                if word_app is not None:
                    configure_uniform_printer(word_app)

                for idx, (docx_path, ts_pdf, out_pdf) in enumerate(valid_targets, start=1):
                    if progress_sink:
                        progress_sink(
                            f"[{idx}/{len(valid_targets)}] Converting and merging Full Report for {docx_path.name}..."
                        )
                    try:
                        out_pdf.parent.mkdir(parents=True, exist_ok=True)
                        # Temporary PDF for Word conversion before in-place PyPDF2 merge
                        temp_conv_pdf = out_pdf.parent / f".tmp_conv_{out_pdf.name}"

                        try:
                            # 1. Word COM conversion
                            if word_app is not None:
                                self._converter.convert_docx_to_pdf(docx_path, temp_conv_pdf, word_app=word_app)
                            else:
                                self._converter.convert_docx_to_pdf(docx_path, temp_conv_pdf, session=session)

                            # 2. PyPDF2 merge: converted Full Report PDF + testsheet PDF -> out_pdf
                            self._converter.merge_pdfs(temp_conv_pdf, ts_pdf, out_pdf)
                        finally:
                            if temp_conv_pdf.exists():
                                try:
                                    temp_conv_pdf.unlink()
                                except Exception:
                                    pass

                        if out_pdf.exists() and out_pdf.stat().st_size > 0:
                            deliverables.append(out_pdf)
                            if progress_sink:
                                progress_sink(f"Deliverable generated -> {out_pdf.name}")
                        else:
                            err_msg = f"Merged deliverable for {docx_path.name} is missing or 0 bytes."
                            errors.append(err_msg)
                    except Exception as exc:
                        err_msg = f"Failed to post-process {docx_path.name}: {exc}"
                        errors.append(err_msg)
                        logger.exception(err_msg)
                        if fail_fast:
                            raise
            finally:
                word_app = None
                import gc
                gc.collect()

        duration = time.time() - start_time

        if progress_sink:
            progress_sink(
                f"Full Report post-processing completed: {len(deliverables)} succeeded, "
                f"{len(docx_files) - len(deliverables)} failed in {duration:.2f}s."
            )

        return FullReportPostProcessingResult(
            total_reports=len(docx_files),
            succeeded_count=len(deliverables),
            failed_count=len(docx_files) - len(deliverables),
            deliverables=tuple(deliverables),
            telemetries=tuple(telemetries),
            warnings=tuple(warnings),
            errors=tuple(errors),
            duration_seconds=duration,
        )

    execute = process

    # --------------------------------------------------------------------------
    # Single Item Convenience API
    # --------------------------------------------------------------------------

    def process_single(
        self,
        docx_path: Path | str,
        environment: ProjectEnvironment,
        *,
        output_path: Path | str | None = None,
        session: Any = None,
    ) -> Path:
        """Convert and merge a single Full Report document, failing fast on missing testsheet."""
        doc_p = Path(docx_path).expanduser().resolve()
        if not doc_p.exists():
            raise FileNotFoundError(f"Full Report docx not found: {doc_p}")

        ts_pdf = resolve_processed_testsheet_pdf_path(doc_p, environment)
        validate_processed_testsheet_pdf(ts_pdf, stem=doc_p.stem, raise_on_error=True)
        assert ts_pdf is not None

        out_p = Path(output_path).resolve() if output_path else doc_p.with_suffix(".pdf")
        out_p.parent.mkdir(parents=True, exist_ok=True)
        temp_conv_pdf = out_p.parent / f".tmp_conv_{out_p.name}"

        try:
            self._converter.convert_docx_to_pdf(doc_p, temp_conv_pdf, session=session)
            self._converter.merge_pdfs(temp_conv_pdf, ts_pdf, out_p)
        finally:
            if temp_conv_pdf.exists():
                try:
                    temp_conv_pdf.unlink()
                except Exception:
                    pass

        return out_p

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------

    def _establish_batch_session(self, explicit_session: Any) -> Any:
        """Establish single BatchComSession context across batch conversions."""
        if explicit_session is not None:
            return explicit_session

        if isinstance(self._converter, ComDocumentConverter):
            # Only Word COM is required for Full Report post-processing; bypass Excel COM startup
            return batch_com_session(excel_app=object(), configure_printer=True, suppress_errors=False)

        # For FakeDocumentConverter or headless testing
        return nullcontext(None)

    def _inspect_single_report(
        self,
        docx_path: Path,
        environment: ProjectEnvironment,
        output_dir: Path | str | None = None,
    ) -> FullReportPostProcessingTelemetry:
        """Evaluate pre-flight testsheet presence and compute dry-run telemetry without disk writes."""
        doc_p = Path(docx_path).resolve()
        stem = doc_p.stem
        date_str = doc_p.parent.name
        month = doc_p.parent.parent.name
        station = doc_p.parent.parent.parent.name

        pe_num = None
        try:
            pe_num = extract_numerical_prefix(stem)
        except ValueError:
            pass

        clean_sub_name = re.sub(r"^\d+\.\s*", "", stem)
        clean_sub_name = re.sub(r"\s*\(.*?\)$", "", clean_sub_name).strip()

        ts_pdf = resolve_processed_testsheet_pdf_path(doc_p, environment)
        val_res = validate_processed_testsheet_pdf(ts_pdf, stem=stem, raise_on_error=False)

        if output_dir:
            target_out = Path(output_dir) / f"{stem}.pdf"
        else:
            target_out = doc_p.with_suffix(".pdf")

        telem_errors: list[str] = []
        if not val_res.is_valid:
            telem_errors.append(val_res.error_message or "Testsheet PDF validation failed")

        return FullReportPostProcessingTelemetry(
            docx_path=doc_p,
            testsheet_pdf_path=ts_pdf,
            target_pdf_path=target_out,
            stem=stem,
            substation_number=pe_num,
            substation_name=clean_sub_name,
            station=station,
            month=month,
            date_str=date_str,
            is_testsheet_pdf_valid=val_res.is_valid,
            validation_result=val_res,
            errors=tuple(telem_errors),
        )

    def _discover_docx_files(
        self,
        target: PostProcessingTarget,
        environment: ProjectEnvironment,
        station: str | Sequence[str] | None = None,
    ) -> tuple[list[Path], list[str], list[str]]:
        """Discover Full Report .docx files matching target criteria."""
        warnings: list[str] = []
        errors: list[str] = []

        full_report_dir = environment.get_full_report_dir() if hasattr(environment, "get_full_report_dir") else environment.base_path / "FULL REPORT"

        # Case 1: Direct .docx path
        if isinstance(target, Path) and target.is_file() and target.suffix.lower() == ".docx":
            if not target.exists():
                errors.append(f"Target file does not exist: {target}")
                return [], warnings, errors
            return [target.resolve()], warnings, errors

        # Case 2: Direct path to directory
        if isinstance(target, Path) and target.is_dir():
            files = [
                p.resolve()
                for p in target.glob("*.docx")
                if not p.name.startswith("~$") and not p.name.startswith(".")
            ]
            files.sort(key=lambda p: p.name)
            return files, warnings, errors

        # Case 3: Sequence of paths
        if isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            collected: list[Path] = []
            for item in target:
                p = Path(item)
                if p.is_file() and p.suffix.lower() == ".docx" and p.exists():
                    collected.append(p.resolve())
                elif p.is_dir():
                    for f in sorted(p.glob("*.docx")):
                        if not f.name.startswith("~$") and not f.name.startswith("."):
                            collected.append(f.resolve())
                elif isinstance(item, str) and DAILY_DATE_FOLDER_PATTERN.match(item.strip()):
                    date_files = self._find_docx_by_date(full_report_dir, item.strip())
                    collected.extend(date_files)
            if station:
                collected = [p for p in collected if self._matches_station(p, station)]
            return collected, warnings, errors

        # Case 4: Target is date string or folder name
        if isinstance(target, str):
            clean_tgt = target.strip()
            # If path to existing directory
            p_tgt = Path(clean_tgt)
            if p_tgt.is_dir():
                files = [
                    p.resolve()
                    for p in p_tgt.glob("*.docx")
                    if not p.name.startswith("~$") and not p.name.startswith(".")
                ]
                if station:
                    files = [p for p in files if self._matches_station(p, station)]
                return files, warnings, errors

            # If calendar date DD-MM-YYYY
            if DAILY_DATE_FOLDER_PATTERN.match(clean_tgt):
                files = self._find_docx_by_date(full_report_dir, clean_tgt)
                if station:
                    files = [p for p in files if self._matches_station(p, station)]
                return files, warnings, errors

        # Case 5: Target is None (scan entire FULL REPORT directory)
        if target is None:
            if not full_report_dir.exists():
                warnings.append(f"Full Report directory does not exist: {full_report_dir}")
                return [], warnings, errors

            files = [
                p.resolve()
                for p in full_report_dir.rglob("*.docx")
                if not p.name.startswith("~$") and not p.name.startswith(".")
            ]
            if station:
                files = [p for p in files if self._matches_station(p, station)]
            files.sort(key=lambda p: p.name)
            return files, warnings, errors

        return [], warnings, errors

    def _find_docx_by_date(self, full_report_dir: Path, date_str: str) -> list[Path]:
        """Find all .docx files inside date subdirectories matching date_str."""
        if not full_report_dir.exists():
            return []

        matched: list[Path] = []
        for date_dir in full_report_dir.rglob(date_str):
            if date_dir.is_dir():
                for docx_p in date_dir.glob("*.docx"):
                    if not docx_p.name.startswith("~$") and not docx_p.name.startswith("."):
                        matched.append(docx_p.resolve())

        matched.sort(key=lambda p: p.name)
        return matched

    def _matches_station(self, docx_path: Path, station_filter: str | Sequence[str] | None) -> bool:
        """Check if docx_path belongs to the filtered station."""
        if station_filter is None:
            return True

        if isinstance(station_filter, str):
            target_stations = {station_filter.strip().upper()}
        else:
            target_stations = {str(s).strip().upper() for s in station_filter if str(s).strip()}

        if not target_stations:
            return True

        # Check path parts against station names
        path_parts_upper = {part.upper() for part in docx_path.parts}
        return bool(target_stations.intersection(path_parts_upper))
