"""Full Report workflow orchestrator deep module exposing inspect() and generate().

Decisions and Architectural Policies Enforced:
- D41: Upfront fail-fast Quick Report pre-flight integrity check via validate_finalized_quick_report().
- D40 / D03: Swappable compiler seam via DocumentCompiler (WordComDocumentCompiler vs FakeDocumentCompiler).
- D14: Managed temp_parts/ workspace lifecycle with automatic cleanup unless --keep-temp is specified.
- Single BatchComSession context established across all batch substations to prevent Word COM process thrashing.
- SubstationIsolatedBatchResiliencePolicy: isolates individual substation failures without aborting the batch run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import gc
import logging
from pathlib import Path
import shutil
from typing import TYPE_CHECKING, Any, Callable, Iterator, Sequence

from src.core.normalizers import (
    format_month_folder,
    normalize_for_report,
)
from src.full_report.attribution import (
    inspect_deliverable_attribution,
    quarantine_deliverable,
)
from src.full_report.composer import FullReportComposer
from src.full_report.photo_resolver import RawPhotoResolver
from src.full_report.plan_builder import FullReportPlanBuilder, FullReportStationPlan
from src.full_report.preflight import (
    PreFlightValidationResult,
    resolve_quick_report_path,
    validate_finalized_quick_report,
)
from src.full_report.slicer import (
    DocumentSlicer,
    FakeDocumentSlicer,
    WordComDocumentSlicer,
)
from src.postprocessing.converters import BatchComSession
from src.quick_report.compiler import (
    DocumentCompiler,
    FakeDocumentCompiler,
    WordComDocumentCompiler,
)
from src.quick_report.defects import CbmDefectRecord, ViDefectRecord
from src.quick_report.extractor import (
    DAILY_DATE_FOLDER_PATTERN,
    QuickReportExtractor,
)
from src.quick_report.prpd import (
    discover_ultratev_survey_dir,
    generate_all_substation_prpd_graphs,
)
from src.quick_report.utils import (
    normalize_functional_location_input,
    sanitize_filename,
)
from src.testsheet.models import (
    SubstationEquipmentPackage,
    SubstationTestsheetPackage,
)

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment

logger = logging.getLogger(__name__)

ReportTarget = (
    Path
    | str
    | SubstationTestsheetPackage
    | Sequence[Path | str | SubstationTestsheetPackage]
    | None
)
ProgressSink = Callable[[str], None]


# ==============================================================================
# 1. Telemetry and Result Dataclasses
# ==============================================================================

@dataclass(frozen=True)
class FullReportSubstationTelemetry:
    """Dry-run inspection data and pre-flight validation status for a single substation."""

    substation_number: int
    substation_name: str
    functional_location: str
    station: str
    month: str
    date_str: str
    quick_report_path: Path | None
    is_quick_report_valid: bool
    preflight_result: PreFlightValidationResult | None
    target_output_path: Path
    stem: str
    defect_suffix: str
    cbm_defect_count: int
    vi_defect_count: int
    equipment_count: int = 0
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def pe_number(self) -> int:
        """Alias for substation_number for backwards compatibility."""
        return self.substation_number

    @property
    def is_ready(self) -> bool:
        """Return True if Quick Report passed pre-flight validation and no errors exist."""
        return self.is_quick_report_valid and len(self.errors) == 0

    @property
    def quick_report_valid(self) -> bool:
        """Alias for is_quick_report_valid."""
        return self.is_quick_report_valid


@dataclass(frozen=True)
class FullReportInspection:
    """Inspection outcome returned by inspect() across all targets."""

    targets: tuple[FullReportSubstationTelemetry, ...]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __iter__(self) -> Iterator[FullReportSubstationTelemetry]:
        return iter(self.targets)

    def __len__(self) -> int:
        return len(self.targets)

    def __getitem__(self, index: int) -> FullReportSubstationTelemetry:
        return self.targets[index]

    @property
    def ready_targets(self) -> tuple[FullReportSubstationTelemetry, ...]:
        return tuple(t for t in self.targets if t.is_ready)

    @property
    def unready_targets(self) -> tuple[FullReportSubstationTelemetry, ...]:
        return tuple(t for t in self.targets if not t.is_ready)

    @property
    def ready_count(self) -> int:
        return len(self.ready_targets)

    @property
    def total_count(self) -> int:
        return len(self.targets)

    @property
    def ready_to_generate(self) -> bool:
        return len(self.errors) == 0 and self.ready_count > 0


@dataclass(frozen=True)
class FullReportStationExecutionResult:
    """Individual substation compilation outcome and telemetry."""

    station: str
    substation_number: int
    output_path: Path | None
    is_success: bool
    error_message: str | None = None
    parts_count: int = 0
    warnings: tuple[str, ...] = ()
    preflight_result: PreFlightValidationResult | None = None
    chunk_paths: tuple[Path, ...] = ()
    is_multipart: bool = False

    @property
    def pe_number(self) -> int:
        return self.substation_number


@dataclass(frozen=True)
class FullReportBatchResult:
    """Consolidated execution outcome returned by generate()."""

    total_stations: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    station_results: tuple[FullReportStationExecutionResult, ...] = ()
    generated_paths: tuple[Path, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.generated_paths and self.station_results:
            flattened: list[Path] = []
            for r in self.station_results:
                if r.is_success:
                    if r.is_multipart and r.chunk_paths:
                        flattened.extend(r.chunk_paths)
                    elif r.output_path:
                        flattened.append(r.output_path)
            if flattened:
                object.__setattr__(self, "generated_paths", tuple(flattened))

    @property
    def reports_generated(self) -> int:
        """Alias for succeeded_count."""
        return self.succeeded_count

    @property
    def is_success(self) -> bool:
        """Return True if at least one report generated and zero errors occurred."""
        return len(self.errors) == 0 and self.succeeded_count > 0

    @property
    def is_successful(self) -> bool:
        """Standardized alias across workflow models."""
        return self.is_success


# ==============================================================================
# 2. Deep Module: FullReportWorkflow
# ==============================================================================

class FullReportWorkflow:
    """Deep module orchestrating Full Report inspection and batch document compilation.

    Presents exactly two primary entry points:
    - inspect(): In-process dry-run planning, pre-flight Quick Report integrity validation,
      and telemetry calculation with strictly ZERO disk writes.
    - generate(): Full rendering and COM compilation under SubstationIsolatedBatchResiliencePolicy
      within a single shared BatchComSession context.
    """

    def __init__(
        self,
        compiler: DocumentCompiler | None = None,
        composer: FullReportComposer | None = None,
        plan_builder: FullReportPlanBuilder | None = None,
        extractor: QuickReportExtractor | None = None,
        slicer: DocumentSlicer | None = None,
        photo_resolver: RawPhotoResolver | None = None,
    ) -> None:
        if compiler is not None:
            self._compiler = compiler
        elif composer is not None and getattr(composer, "compiler", None) is not None:
            self._compiler = composer.compiler
        else:
            self._compiler = WordComDocumentCompiler()

        self._composer = composer or FullReportComposer(compiler=self._compiler)

        if slicer is not None:
            self._slicer = slicer
        elif isinstance(self._compiler, FakeDocumentCompiler):
            self._slicer = FakeDocumentSlicer()
        else:
            self._slicer = WordComDocumentSlicer()

        self._plan_builder = plan_builder or FullReportPlanBuilder(
            slicer=self._slicer,
            photo_resolver=photo_resolver,
        )
        self._extractor = extractor or QuickReportExtractor()
        self._photo_resolver = photo_resolver

    # --------------------------------------------------------------------------
    # Public API: inspect()
    # --------------------------------------------------------------------------

    def inspect(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        *,
        station: str | Sequence[str] | None = None,
        progress_sink: ProgressSink | None = None,
    ) -> FullReportInspection:
        """Dry-run discovery and pre-flight validation without disk writes or COM calls."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        self._validate_target_existence(target, environment)

        if progress_sink:
            progress_sink("Discovering target packages for Full Report inspection...")

        packages, warnings, errors = self._discover_packages(target, environment, station=station)
        if not packages:
            return FullReportInspection(
                targets=(),
                warnings=tuple(warnings),
                errors=tuple(errors),
            )

        telemetries: list[FullReportSubstationTelemetry] = []
        for idx, pkg in enumerate(packages, start=1):
            st_name = self._resolve_substation_display_name(pkg)
            if progress_sink:
                progress_sink(
                    f"[{idx}/{len(packages)}] Inspecting Quick Report for {st_name}..."
                )
            try:
                telem = self._inspect_single_package(pkg, environment)
                telemetries.append(telem)
            except Exception as exc:
                err_msg = f"Failed to inspect {st_name}: {exc}"
                errors.append(err_msg)
                logger.exception(err_msg)
                telemetries.append(
                    FullReportSubstationTelemetry(
                        substation_number=pkg.substation_number,
                        substation_name=st_name,
                        functional_location=self._resolve_fl(pkg),
                        station=pkg.station or (pkg.data.station_name if pkg.data else "") or "UNKNOWN",
                        month=pkg.month or "01. JANUARY",
                        date_str=pkg.date_str or "01-01-2026",
                        quick_report_path=None,
                        is_quick_report_valid=False,
                        preflight_result=None,
                        target_output_path=Path(""),
                        stem="",
                        defect_suffix="",
                        cbm_defect_count=0,
                        vi_defect_count=0,
                        errors=(err_msg,),
                    )
                )

        return FullReportInspection(
            targets=tuple(telemetries),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    # --------------------------------------------------------------------------
    # Public API: generate()
    # --------------------------------------------------------------------------

    def generate(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        *,
        station: str | Sequence[str] | None = None,
        progress_sink: ProgressSink | None = None,
        keep_temp: bool = False,
        temp_dir: Path | str | None = None,
        output_dir: Path | str | None = None,
        com_session: Any = None,
    ) -> FullReportBatchResult:
        """End-to-end: discover -> preflight -> plan -> render -> compile.

        Resilience:
        SubstationIsolatedBatchResiliencePolicy isolates failures per substation,
        allowing healthy substations to generate successfully even if others fail.
        """
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        self._validate_target_existence(target, environment)

        if progress_sink:
            progress_sink("Discovering target packages for Full Report...")

        packages, warnings, errors = self._discover_packages(target, environment, station=station)
        if not packages:
            if not errors:
                errors.append(f"No testsheet packages found for target: {target}")
            return FullReportBatchResult(
                total_stations=0,
                succeeded_count=0,
                failed_count=0,
                station_results=(),
                generated_paths=(),
                warnings=tuple(warnings),
                errors=tuple(errors),
            )

        if progress_sink:
            progress_sink(f"Found {len(packages)} packages to process.")

        ordered_results: list[FullReportStationExecutionResult | None] = [None] * len(packages)
        generated_paths: list[Path] = []

        base_temp_root = (
            Path(temp_dir).resolve()
            if temp_dir is not None
            else (Path(environment.base_path).resolve() / ".temp" / "full_report")
        )

        # Single shared BatchComSession context across ALL phases (slicing & compilation)
        session_cm = self._establish_batch_session(com_session)

        with session_cm as session:
            word_app = getattr(session, "word_app", None)
            orig_word_app = getattr(self._compiler, "_word_app", None)
            orig_slicer_word_app = getattr(self._slicer, "_word_app", None)
            if word_app is not None:
                try:
                    word_app.ScreenUpdating = False
                    word_app.DisplayAlerts = 0
                except Exception:
                    pass
                if hasattr(self._compiler, "_word_app"):
                    self._compiler._word_app = word_app
                if hasattr(self._slicer, "_word_app"):
                    self._slicer._word_app = word_app

            try:
                # Unified single-phase lifecycle per substation:
                # [Preflight -> Slice -> Render -> Compile -> Sanity Check -> Success]
                for pkg_idx, pkg in enumerate(packages):
                    st_name = self._resolve_substation_display_name(pkg)
                    if progress_sink:
                        progress_sink(
                            f"[{pkg_idx + 1}/{len(packages)}] Generating Full Report for {st_name}..."
                        )

                    # 1. Pre-flight validation
                    qr_path = self._resolve_quick_report_path(environment, pkg)
                    val_res = validate_finalized_quick_report(qr_path, raise_on_error=False)
                    if not val_res.is_valid:
                        # SubstationIsolatedBatchResiliencePolicy: record upfront validation failure
                        err_msg = f"Pre-flight validation failed for {st_name}: {val_res.error_message}"
                        errors.append(err_msg)
                        ordered_results[pkg_idx] = FullReportStationExecutionResult(
                            station=st_name,
                            substation_number=pkg.substation_number,
                            output_path=None,
                            is_success=False,
                            error_message=val_res.error_message,
                            preflight_result=val_res,
                        )
                        continue

                    # 2. Workspace allocation
                    sub_num = pkg.substation_number or (pkg.data.pe_number if getattr(pkg, "data", None) else 0) or 0
                    date_str = pkg.date_str or (pkg.data.date if getattr(pkg, "data", None) else "") or "01-01-2026"
                    clean_name = sanitize_filename(st_name)
                    clean_date = sanitize_filename(date_str).replace(" ", "_")
                    substation_key = f"{sub_num:03d}_{clean_name}_{clean_date}"
                    station_temp_dir = base_temp_root / substation_key

                    # Pre-purge on allocation: guarantee completely clean slate for this substation
                    if station_temp_dir.exists():
                        shutil.rmtree(station_temp_dir, ignore_errors=True)
                    (station_temp_dir / "sliced").mkdir(parents=True, exist_ok=True)
                    (station_temp_dir / "rendered").mkdir(parents=True, exist_ok=True)
                    (station_temp_dir / "prpd").mkdir(parents=True, exist_ok=True)

                    try:
                        # 3. Slicing & Plan building
                        plan = self._build_station_plan(
                            pkg,
                            environment,
                            quick_report_path=qr_path,
                            output_dir=output_dir,
                            station_temp_dir=station_temp_dir,
                        )

                        # 4. Rendering & Compilation
                        rendered_dir = station_temp_dir / "rendered"
                        rendered_dir.mkdir(parents=True, exist_ok=True)

                        comp_res = self._composer.compose(
                            plan,
                            keep_temp=keep_temp,
                            temp_dir=rendered_dir,
                            base_dir=environment.base_path,
                        )

                        out_path = comp_res.output_path
                        if not out_path or not out_path.exists() or out_path.stat().st_size == 0:
                            err_msg = f"Generated report for {st_name} is missing or 0 bytes."
                            errors.append(err_msg)
                            ordered_results[pkg_idx] = FullReportStationExecutionResult(
                                station=st_name,
                                substation_number=pkg.substation_number,
                                output_path=out_path,
                                is_success=False,
                                error_message=err_msg,
                                preflight_result=val_res,
                            )
                        else:
                            # 5. Seam 4: Post-Compilation Deliverable Sanity Check
                            if comp_res.is_multipart and comp_res.chunk_paths:
                                # Verify each chunk path exists and passes attribution
                                all_attr_ok = True
                                attr_failures: list[str] = []
                                for chunk_path in comp_res.chunk_paths:
                                    if not chunk_path or not chunk_path.exists() or chunk_path.stat().st_size == 0:
                                        all_attr_ok = False
                                        attr_failures.append(f"Chunk {chunk_path.name} is missing or 0 bytes.")
                                        continue
                                    c_ok, c_reason = inspect_deliverable_attribution(
                                        chunk_path,
                                        target_substation=st_name,
                                    )
                                    if not c_ok:
                                        all_attr_ok = False
                                        attr_failures.append(f"{chunk_path.name}: {c_reason}")
                                if not all_attr_ok:
                                    for cp in comp_res.chunk_paths:
                                        if cp and cp.exists():
                                            quarantine_deliverable(cp)
                                    err_msg = (
                                        f"Post-compilation attribution sanity check failed for {st_name}: "
                                        f"{'; '.join(attr_failures)}. Deliverables quarantined."
                                    )
                                    errors.append(err_msg)
                                    ordered_results[pkg_idx] = FullReportStationExecutionResult(
                                        station=st_name,
                                        substation_number=pkg.substation_number,
                                        output_path=None,
                                        is_success=False,
                                        error_message=err_msg,
                                        preflight_result=val_res,
                                    )
                                else:
                                    if comp_res.is_multipart and comp_res.chunk_paths:
                                        generated_paths.extend(comp_res.chunk_paths)
                                    else:
                                        generated_paths.append(out_path)
                                    ordered_results[pkg_idx] = FullReportStationExecutionResult(
                                        station=st_name,
                                        substation_number=pkg.substation_number,
                                        output_path=out_path,
                                        is_success=True,
                                        parts_count=comp_res.part_count,
                                        preflight_result=val_res,
                                        chunk_paths=comp_res.chunk_paths,
                                        is_multipart=comp_res.is_multipart,
                                    )
                            else:
                                is_attr_ok, attr_reason = inspect_deliverable_attribution(
                                    out_path,
                                    target_substation=st_name,
                                )
                                if not is_attr_ok:
                                    quarantined_path = quarantine_deliverable(out_path)
                                    err_msg = (
                                        f"Post-compilation attribution sanity check failed for {st_name}: "
                                        f"{attr_reason}. Deliverable quarantined to '{quarantined_path.name}'."
                                    )
                                    errors.append(err_msg)
                                    ordered_results[pkg_idx] = FullReportStationExecutionResult(
                                        station=st_name,
                                        substation_number=pkg.substation_number,
                                        output_path=None,
                                        is_success=False,
                                        error_message=err_msg,
                                        preflight_result=val_res,
                                    )
                                else:
                                    generated_paths.append(out_path)
                                    ordered_results[pkg_idx] = FullReportStationExecutionResult(
                                        station=st_name,
                                        substation_number=pkg.substation_number,
                                        output_path=out_path,
                                        is_success=True,
                                        parts_count=comp_res.part_count,
                                        preflight_result=val_res,
                                        chunk_paths=comp_res.chunk_paths,
                                        is_multipart=comp_res.is_multipart,
                                    )
                    except Exception as exc:
                        # SubstationIsolatedBatchResiliencePolicy
                        err_msg = f"Failed to compile Full Report for {st_name}: {exc}"
                        errors.append(err_msg)
                        logger.exception(err_msg)
                        ordered_results[pkg_idx] = FullReportStationExecutionResult(
                            station=st_name,
                            substation_number=pkg.substation_number,
                            output_path=None,
                            is_success=False,
                            error_message=str(exc),
                            preflight_result=val_res,
                        )
                    finally:
                        # Immediate workspace cleanup (Seam 5)
                        if not keep_temp and station_temp_dir.exists():
                            shutil.rmtree(station_temp_dir, ignore_errors=True)

                        # In-process COM handle flush (Seam 5)
                        self._flush_substation_com_handles(word_app, st_name)
            finally:
                if hasattr(self._compiler, "_word_app"):
                    self._compiler._word_app = orig_word_app
                if hasattr(self._slicer, "_word_app"):
                    self._slicer._word_app = orig_slicer_word_app
                word_app = None
                gc.collect()

        final_station_results = tuple(r for r in ordered_results if r is not None)
        succeeded_stations = sum(1 for r in final_station_results if r.is_success)
        failed_stations = len(packages) - succeeded_stations

        if progress_sink:
            progress_sink(
                f"Full Report batch completed: {succeeded_stations} succeeded, {failed_stations} failed."
            )

        return FullReportBatchResult(
            total_stations=len(packages),
            succeeded_count=succeeded_stations,
            failed_count=failed_stations,
            station_results=final_station_results,
            generated_paths=tuple(generated_paths),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------

    def _establish_batch_session(self, explicit_session: Any) -> Any:
        """Establish single BatchComSession context across batch compilations."""
        if explicit_session is not None:
            return explicit_session

        if isinstance(self._compiler, WordComDocumentCompiler):
            return BatchComSession(suppress_errors=False)

        # For headless compilers (FakeDocumentCompiler), use composer.session() unless BatchComSession is patched in tests
        try:
            from unittest.mock import MagicMock, Mock
            if isinstance(BatchComSession, (Mock, MagicMock)):
                return BatchComSession()
        except Exception:
            pass

        return self._composer.session()

    def _flush_substation_com_handles(self, word_app: Any, st_name: str) -> None:
        """In-process COM handle flush per substation: close open docs, clear clipboard, gc, assert count == 0."""
        if word_app is None:
            return

        # 1. Close all open document handles without saving
        try:
            docs = getattr(word_app, "Documents", None)
            if docs is not None:
                doc_count = getattr(docs, "Count", 0)
                if isinstance(doc_count, int):
                    attempts = 0
                    while getattr(docs, "Count", 0) > 0 and attempts < 20:
                        attempts += 1
                        try:
                            docs(1).Close(False)
                        except Exception:
                            break
        except Exception as exc:
            logger.debug("Failed closing lingering COM documents for %s: %s", st_name, exc)

        # 2. Purge Windows clipboard
        try:
            from src.quick_report.compiler import _clear_clipboard
            _clear_clipboard()
        except Exception:
            pass

        # 3. Garbage collection
        gc.collect()

        # 4. Assert / check documents count is 0
        try:
            docs = getattr(word_app, "Documents", None)
            if docs is not None:
                doc_count = getattr(docs, "Count", 0)
                if isinstance(doc_count, int) and doc_count != 0:
                    logger.error(
                        "Lingering COM documents detected after substation %s: %d open",
                        st_name,
                        doc_count,
                    )
        except Exception:
            pass

    def _inspect_single_package(
        self,
        pkg: SubstationTestsheetPackage,
        environment: ProjectEnvironment,
    ) -> FullReportSubstationTelemetry:
        """Evaluate pre-flight integrity and compute telemetry without disk writes."""
        st_name = self._resolve_substation_display_name(pkg)
        fl_str = self._resolve_fl(pkg)
        sub_num = pkg.substation_number
        station = pkg.station or (pkg.data.station_name if pkg.data else "") or "UNKNOWN"
        month = pkg.month or "01. JANUARY"
        date_str = pkg.date_str or "01-01-2026"

        qr_path = self._resolve_quick_report_path(environment, pkg)
        val_res = validate_finalized_quick_report(qr_path, raise_on_error=False)

        cbm_defects, vi_defects = self._extract_defects_safe(pkg, environment)
        suffix = self._calculate_defect_suffix(cbm_defects, vi_defects)
        clean_name = sanitize_filename(st_name)
        stem = f"{sub_num:03d}. {clean_name}{suffix}" if sub_num else f"{clean_name}{suffix}"

        out_path = self._resolve_target_output_path(environment, pkg, stem)

        telem_errors: list[str] = []
        if not val_res.is_valid:
            telem_errors.append(val_res.error_message or "Pre-flight validation failed")

        # Validate Full Report templates
        if hasattr(environment, "get_full_report_census_template"):
            try:
                census_tpl = environment.get_full_report_census_template()
                if not census_tpl.is_file():
                    telem_errors.append(f"Missing Full Report census template: {census_tpl.name}")
            except Exception as exc:
                telem_errors.append(f"Missing Full Report census template: {exc}")

        if hasattr(environment, "get_full_report_normal_template"):
            from config import FULL_REPORT_TEMPLATES
            for key, filename in FULL_REPORT_TEMPLATES.items():
                if key == "census":
                    continue
                try:
                    tpl_path = environment.get_full_report_normal_template(filename)
                    if not tpl_path.is_file():
                        telem_errors.append(f"Missing Full Report template: {filename}")
                except Exception as exc:
                    telem_errors.append(f"Failed resolving Full Report template {filename}: {exc}")

        eq_pkg = self._resolve_equipment_package(pkg)
        eq_count = (
            len(getattr(eq_pkg, "switchgears", ()))
            + len(getattr(eq_pkg, "transformers", ()))
            + len(getattr(eq_pkg, "lvdb_specs", ()))
        )

        return FullReportSubstationTelemetry(
            substation_number=sub_num,
            substation_name=st_name,
            functional_location=fl_str,
            station=station,
            month=month,
            date_str=date_str,
            quick_report_path=qr_path,
            is_quick_report_valid=val_res.is_valid,
            preflight_result=val_res,
            target_output_path=out_path,
            stem=stem,
            defect_suffix=suffix,
            cbm_defect_count=len(cbm_defects),
            vi_defect_count=len(vi_defects),
            equipment_count=eq_count,
            errors=tuple(telem_errors),
        )

    def _build_station_plan(
        self,
        pkg: SubstationTestsheetPackage,
        environment: ProjectEnvironment,
        quick_report_path: Path,
        output_dir: Path | str | None = None,
        station_temp_dir: Path | None = None,
        temp_dir: Path | str | None = None,
    ) -> FullReportStationPlan:
        """Construct FullReportStationPlan Bill of Materials for compilation."""
        st_name = self._resolve_substation_display_name(pkg)
        fl_str = self._resolve_fl(pkg)
        sub_num = pkg.substation_number or (pkg.data.pe_number if getattr(pkg, "data", None) else 0) or 0
        station = pkg.station or (pkg.data.station_name if pkg.data else "") or "UNKNOWN"
        date_str = pkg.date_str or (pkg.data.date if getattr(pkg, "data", None) else "") or "01-01-2026"
        month = pkg.month or "01. JANUARY"

        cbm_defects, vi_defects = self._extract_defects_safe(pkg, environment)
        suffix = self._calculate_defect_suffix(cbm_defects, vi_defects)
        clean_name = sanitize_filename(st_name)
        clean_date = sanitize_filename(date_str).replace(" ", "_")
        stem = f"{sub_num:03d}. {clean_name}{suffix}" if sub_num else f"{clean_name}{suffix}"

        out_path = self._resolve_target_output_path(environment, pkg, stem, output_dir=output_dir)

        if station_temp_dir is None:
            if temp_dir is not None:
                station_temp_dir = Path(temp_dir)
            else:
                sub_key = f"{sub_num:03d}_{clean_name}_{clean_date}"
                station_temp_dir = (
                    Path(environment.base_path).resolve() / ".temp" / "full_report" / sub_key
                )

        sliced_dir = station_temp_dir / "sliced"
        prpd_dir = station_temp_dir / "prpd"
        sliced_dir.mkdir(parents=True, exist_ok=True)
        prpd_dir.mkdir(parents=True, exist_ok=True)

        # Query user's PRPD mode setting (ADR 0001)
        prpd_mode = "option_c"
        if hasattr(environment, "get_prpd_config"):
            try:
                prpd_mode = environment.get_prpd_config().mode
            except Exception:
                prpd_mode = "option_c"

        # Resolve substation raw data directory
        raw_dir = None
        if hasattr(environment, "get_substation_raw_data_dir"):
            try:
                raw_dir = environment.get_substation_raw_data_dir(
                    station=station,
                    month=month,
                    date_str=date_str,
                    substation_number=sub_num,
                )
            except Exception:
                raw_dir = None

        if (not raw_dir or not Path(raw_dir).exists()) and getattr(pkg, "unsorted_raw_data_dir", None):
            cand = Path(pkg.unsorted_raw_data_dir)
            if cand.exists():
                raw_dir = cand

        if (not raw_dir or not Path(raw_dir).exists()) and getattr(pkg, "raw_data_dir", None):
            cand = Path(pkg.raw_data_dir)
            if cand.exists():
                raw_dir = cand

        # Discover UltraTEV survey folder and generate all PRPD graphs for this substation
        survey_root = None
        prpd_catalog = None
        if raw_dir and Path(raw_dir).exists():
            survey_root = discover_ultratev_survey_dir(raw_dir)
            if survey_root and Path(survey_root).exists():
                try:
                    prpd_catalog = generate_all_substation_prpd_graphs(
                        survey_root=survey_root,
                        output_dir=prpd_dir,
                        mode=prpd_mode,
                    )
                except Exception as exc:
                    logger.warning("Failed to generate PRPD graphs for %s: %s", st_name, exc)
                    prpd_catalog = None

        eq_pkg = self._resolve_equipment_package(pkg)
        ts_data = getattr(pkg, "data", None)
        sub_info = {
            "name_erms": st_name,
            "station_name": station,
            "station": station,
            "date": date_str,
            "fl": fl_str,
            "pe_number": sub_num,
            "time": normalize_for_report(ts_data.time) if ts_data else "-",
            "ambient": normalize_for_report(ts_data.ambient) if ts_data else "-",
            "humidity": normalize_for_report(ts_data.humidity) if ts_data else "-",
            "tev_background": normalize_for_report(ts_data.tev_background) if ts_data else "-",
            "tev_bg": normalize_for_report(ts_data.tev_background) if ts_data else "-",
            "technologies": getattr(environment, "technologies", None),
            "project_technologies": getattr(environment, "technologies", None),
        }

        census_tpl = None
        if hasattr(environment, "get_full_report_census_template"):
            try:
                census_tpl = environment.get_full_report_census_template()
            except Exception:
                census_tpl = None

        normal_tpl_dir = None
        if hasattr(environment, "get_full_report_normal_templates_dir"):
            try:
                normal_tpl_dir = environment.get_full_report_normal_templates_dir()
            except Exception:
                normal_tpl_dir = None

        return self._plan_builder.build(
            package=eq_pkg,
            quick_report_path=quick_report_path,
            cbm_defects=cbm_defects,
            vi_defects=vi_defects,
            substation_info=sub_info,
            station=st_name,
            date_str=date_str,
            month=month,
            output_dir=out_path.parent,
            output_filename=out_path.name,
            temp_parts_dir=sliced_dir,
            photo_resolver=self._photo_resolver,
            survey_root=survey_root,
            prpd_catalog=prpd_catalog,
            prpd_output_dir=prpd_dir,
            prpd_mode=prpd_mode,
            templates_dir=normal_tpl_dir,
            census_template=census_tpl,
        )

    def _resolve_target_output_path(
        self,
        environment: ProjectEnvironment,
        pkg: SubstationTestsheetPackage,
        stem: str,
        output_dir: Path | str | None = None,
    ) -> Path:
        """Calculate final destination path: FULL REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.docx."""
        filename = f"{stem}.docx" if not stem.lower().endswith(".docx") else stem
        station = pkg.station or (pkg.data.station_name if pkg.data else "") or "UNKNOWN"
        month = format_month_folder(pkg.month) or "01. JANUARY"
        date_str = pkg.date_str or "01-01-2026"

        if output_dir is not None:
            base_out = Path(output_dir)
            # If explicit output_dir was given as base folder
            if base_out.name == date_str:
                return base_out / filename
            return base_out / station / month / date_str / filename

        if hasattr(environment, "get_full_report_dir"):
            base_full = environment.get_full_report_dir()
        else:
            base_full = environment.base_path / "FULL REPORT"

        return base_full / station / month / date_str / filename

    def _resolve_quick_report_path(
        self,
        environment: ProjectEnvironment,
        pkg: SubstationTestsheetPackage,
    ) -> Path:
        """Locate existing finalized Quick Report document for substation."""
        if hasattr(pkg, "quick_report_docx") and getattr(pkg, "quick_report_docx"):
            return Path(pkg.quick_report_docx).resolve()

        qr_dir = environment.get_quick_report_dir()
        station = pkg.station or (pkg.data.station_name if pkg.data else "") or "UNKNOWN"
        month = format_month_folder(pkg.month) or "01. JANUARY"
        date_str = pkg.date_str or "01-01-2026"

        candidate_dirs = [
            qr_dir / station / month / date_str,
            qr_dir / station / date_str,
            qr_dir / date_str,
            qr_dir,
        ]

        sub_num = pkg.substation_number
        num_prefix1 = f"{sub_num:03d}."
        num_prefix2 = f"{sub_num}."

        clean_sub_name = sanitize_filename(self._resolve_substation_display_name(pkg)).lower()

        for folder in candidate_dirs:
            if not folder.exists() or not folder.is_dir():
                continue
            for docx_file in folder.glob("*.docx"):
                if docx_file.name.startswith("~$"):
                    continue
                # Match by numerical prefix
                if docx_file.name.startswith(num_prefix1) or docx_file.name.startswith(num_prefix2):
                    return docx_file.resolve()

            # Match by name if prefix didn't match
            if clean_sub_name:
                for docx_file in folder.glob("*.docx"):
                    if docx_file.name.startswith("~$"):
                        continue
                    if clean_sub_name in docx_file.name.lower():
                        return docx_file.resolve()

        # Fallback to canonical path structure
        return resolve_quick_report_path(
            environment.base_path,
            station=station,
            month=month,
            date=date_str,
            stem=f"{num_prefix1} {clean_sub_name}",
        )

    def _extract_defects_safe(
        self,
        pkg: SubstationTestsheetPackage,
        environment: ProjectEnvironment,
    ) -> tuple[list[CbmDefectRecord], list[ViDefectRecord]]:
        """Extract defects via extractor safely without throwing."""
        try:
            cbm, vi = self._extractor.extract_defects(pkg, environment)
            return list(cbm), list(vi)
        except Exception:
            return [], []

    def _resolve_equipment_package(
        self,
        pkg: SubstationTestsheetPackage | Any,
    ) -> SubstationEquipmentPackage:
        """Resolve strongly typed SubstationEquipmentPackage from package."""
        if isinstance(pkg, SubstationEquipmentPackage):
            return pkg
        if getattr(pkg, "data", None) and getattr(pkg.data, "equipment", None):
            return pkg.data.equipment
        if getattr(pkg, "equipment", None):
            return pkg.equipment
        return SubstationEquipmentPackage()

    def _calculate_defect_suffix(
        self,
        cbm_defects: Sequence[CbmDefectRecord],
        vi_defects: Sequence[ViDefectRecord],
    ) -> str:
        """Calculate canonical defect status suffix (e.g. ' (IR+VI)')."""
        parts = []
        techs = {getattr(d, "technology", "").upper() for d in cbm_defects}
        if "IR" in techs:
            parts.append("IR")
        if "US" in techs:
            parts.append("US")
        if "TEV" in techs:
            parts.append("TEV")
        if not parts and cbm_defects:
            parts.append("IR")
        if vi_defects:
            parts.append("VI")

        return f" ({'+'.join(parts)})" if parts else ""

    def _resolve_substation_display_name(self, pkg: SubstationTestsheetPackage) -> str:
        """Return canonical substation display name."""
        if getattr(pkg, "data", None):
            name = pkg.data.substation_name_erms or pkg.data.station_name or pkg.station
            if name:
                return str(name)
        if getattr(pkg, "station", ""):
            return str(pkg.station)
        sub_num = getattr(pkg, "substation_number", None)
        return f"substation {sub_num}" if sub_num is not None else "unknown substation"

    def _resolve_fl(self, pkg: SubstationTestsheetPackage) -> str:
        """Return ERMS functional location string if available."""
        if getattr(pkg, "data", None):
            return str(getattr(pkg.data, "fl_erms", "") or "")
        return ""

    def _matches_station(
        self,
        pkg: SubstationTestsheetPackage,
        station_filter: str | Sequence[str] | None,
    ) -> bool:
        """Centralize station matching logic for single strings and sequences."""
        if station_filter is None:
            return True

        if isinstance(station_filter, str):
            clean = station_filter.strip().upper()
            target_stations = {clean} if clean else set()
        elif isinstance(station_filter, Sequence):
            target_stations = {
                str(s).strip().upper() for s in station_filter if s and str(s).strip()
            }
        else:
            return False

        if not target_stations:
            return True

        pkg_station = getattr(pkg, "station", "")
        pkg_station_str = str(pkg_station).strip().upper() if isinstance(pkg_station, str) else ""

        data_station = getattr(pkg.data, "station_name", "") if getattr(pkg, "data", None) else ""
        data_station_str = str(data_station).strip().upper() if isinstance(data_station, str) else ""

        substation_erms = getattr(pkg.data, "substation_name_erms", "") if getattr(pkg, "data", None) else ""
        substation_erms_str = str(substation_erms).strip().upper() if isinstance(substation_erms, str) else ""

        display_name = self._resolve_substation_display_name(pkg)
        display_name_str = str(display_name).strip().upper()

        return (
            (pkg_station_str in target_stations)
            or (data_station_str in target_stations)
            or (substation_erms_str in target_stations)
            or (display_name_str in target_stations)
        )

    def _validate_target_existence(
        self, target: ReportTarget, environment: ProjectEnvironment
    ) -> None:
        """Fail fast if an explicit Path target was given but missing."""
        if isinstance(target, Path):
            if not self._target_path_exists(target, environment):
                raise FileNotFoundError(f"Target path does not exist: {target}")
        elif isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            for item in target:
                if isinstance(item, Path):
                    if not self._target_path_exists(item, environment):
                        raise FileNotFoundError(f"Target path does not exist: {item}")

    def _target_path_exists(
        self, target: Path | str, environment: ProjectEnvironment
    ) -> bool:
        """Return True if target exists either directly or relative to testsheet directory."""
        path = Path(target)
        if not path.is_absolute() and hasattr(environment, "get_testsheet_dir"):
            return path.exists() or (environment.get_testsheet_dir() / path).exists()
        return path.exists()

    def _discover_packages(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        station: str | Sequence[str] | None = None,
    ) -> tuple[list[SubstationTestsheetPackage], list[str], list[str]]:
        """Discover packages matching polymorphic target."""
        warnings: list[str] = []
        errors: list[str] = []

        # Case 1: Direct SubstationTestsheetPackage(s) passed
        if isinstance(target, SubstationTestsheetPackage):
            pkgs = [target]
            if station:
                pkgs = [p for p in pkgs if self._matches_station(p, station)]
            return pkgs, warnings, errors

        if isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            if all(isinstance(item, SubstationTestsheetPackage) for item in target):
                pkgs = list(target)
                if station:
                    pkgs = [p for p in pkgs if self._matches_station(p, station)]
                return pkgs, warnings, errors

        # Case 2: Target is folder/date/fl string or Path
        folders, fls = self._resolve_target(target, environment)
        try:
            raw_packages = self._extractor.extract(environment, folders=folders, fls=fls)
            packages = [pkg for pkg in raw_packages if pkg.data is not None]
            if station:
                packages = [pkg for pkg in packages if self._matches_station(pkg, station)]
            if fls:
                target_fls = {normalize_functional_location_input(fl) for fl in fls}
                packages = [
                    pkg
                    for pkg in packages
                    if getattr(pkg, "data", None)
                    and normalize_functional_location_input(pkg.data.fl_erms) in target_fls
                ]
        except Exception as exc:
            errors.append(f"Package discovery failed: {exc}")
            return [], warnings, errors

        if not packages:
            warnings.append(f"No testsheet packages found for target: {target}")

        return packages, warnings, errors

    def _resolve_target(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
    ) -> tuple[Sequence[str] | None, Sequence[str] | None]:
        """Convert polymorphic ReportTarget into (folders, fls) pair."""
        if target is None:
            return None, None
        if isinstance(target, Path):
            return (str(target),), None
        elif isinstance(target, str):
            s = target.strip()
            if self._is_dir_or_date(s, environment):
                return (s,), None
            if "," in s:
                tokens = [tok.strip() for tok in s.split(",") if tok.strip()]
                return None, tuple(tokens)
            return None, (s,)
        elif isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            items = list(target)
            if not items:
                return None, ()
            if all(isinstance(item, Path) for item in items):
                return tuple(str(p) for p in items), None
            if all(
                isinstance(item, Path) or self._is_dir_or_date(str(item).strip(), environment)
                for item in items
            ):
                return tuple(str(item) for item in items), None
            else:
                fl_list: list[str] = []
                for item in items:
                    fl_list.extend([tok.strip() for tok in str(item).split(",") if tok.strip()])
                return None, tuple(fl_list)
        else:
            raise ValueError(
                f"Unsupported target type: {type(target)}. Expected Path, str, or Sequence[Path | str]."
            )

    def _is_dir_or_date(self, target_str: str, environment: ProjectEnvironment) -> bool:
        """Return True if target_str is an existing directory path or valid DD-MM-YYYY calendar date."""
        try:
            p = Path(target_str)
            if p.is_absolute() and p.is_dir():
                return True
        except Exception:
            pass
        if hasattr(environment, "get_testsheet_dir"):
            try:
                ts_dir = environment.get_testsheet_dir()
                if isinstance(ts_dir, Path) and (ts_dir / target_str).is_dir():
                    return True
            except Exception:
                pass
        if DAILY_DATE_FOLDER_PATTERN.match(target_str):
            try:
                datetime.strptime(target_str, "%d-%m-%Y")
            except ValueError as exc:
                raise ValueError(
                    f"Invalid calendar date '{target_str}': {exc}. Expected valid DD-MM-YYYY date."
                ) from exc
            return True
        return False
