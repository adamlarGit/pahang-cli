"""Quick Report workflow orchestrator deep module exposing generate() and inspect()."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

from src.quick_report.compiler import (
    DocumentCompiler,
    WordComDocumentCompiler,
)
from src.quick_report.composer import QuickReportComposer
from src.quick_report.extractor import (
    DAILY_DATE_FOLDER_PATTERN,
    QuickReportExtractor,
)
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.transformer import QuickReportTransformer
from src.quick_report.utils import (
    normalize_functional_location_input,
    sanitize_filename,
)
from src.testsheet.models import SubstationTestsheetPackage
from src.workflows.models import (
    QuickReportInspection,
    QuickReportResult,
    SubstationInspectionItem,
)

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment

logger = logging.getLogger(__name__)

ReportTarget = Path | str | Sequence[Path] | Sequence[str] | Sequence[Path | str]
ProgressSink = Callable[[str], None]


class QuickReportWorkflow:
    """Deep module orchestrating the 6-stage Quick Report ETL pipeline under SubstationIsolatedBatchResiliencePolicy.

    Presents exactly two primary entry points:
    - generate(): End-to-end extraction, planning, rendering, and COM compilation.
    - inspect(): In-process dry-run planning, suffix calculations, and template audits.

    Resilience Policy:
    SubstationIsolatedBatchResiliencePolicy isolates failures at the individual substation
    level, allowing non-failing substations in a batch to compile and generate successfully.
    """

    def __init__(
        self,
        compiler: DocumentCompiler | None = None,
        extractor: QuickReportExtractor | None = None,
        transformer: QuickReportTransformer | None = None,
        composer: QuickReportComposer | None = None,
    ) -> None:
        if compiler is not None:
            self._compiler = compiler
        elif composer is not None and getattr(composer, "compiler", None) is not None:
            self._compiler = composer.compiler
        else:
            self._compiler = WordComDocumentCompiler()

        self._extractor = extractor or QuickReportExtractor()
        self._transformer = transformer or QuickReportTransformer()
        self._composer = composer or QuickReportComposer(compiler=self._compiler)

    def generate(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        *,
        station: str | Sequence[str] | None = None,
        condition_template: Path | None = None,
        progress_sink: ProgressSink | None = None,
        com_session: Any | None = None,
    ) -> QuickReportResult:
        """End-to-end: discover -> filter -> transform -> compile."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        # Fail fast if an explicit Path target was given but missing
        if isinstance(target, Path):
            if not self._target_path_exists(target, environment):
                raise FileNotFoundError(f"Target path does not exist: {target}")
        elif isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            for item in target:
                if isinstance(item, Path):
                    if not self._target_path_exists(item, environment):
                        raise FileNotFoundError(f"Target path does not exist: {item}")

        if progress_sink:
            progress_sink("Discovering target packages for Quick Report...")

        inspection, plans = self._plan(
            target,
            environment,
            station=station,
            condition_template=condition_template,
        )

        if inspection.missing_templates:
            raise FileNotFoundError(inspection.missing_templates[0])

        if not plans:
            errors = inspection.errors
            if not errors and not inspection.targets:
                errors = (f"No testsheet packages found for target: {target}",)
            return QuickReportResult(
                reports_generated=0,
                generated_paths=(),
                warnings=inspection.warnings,
                errors=errors,
            )

        if progress_sink:
            progress_sink(f"Found {len(plans)} packages to process.")

        generated_paths: list[Path] = []
        warnings: list[str] = list(inspection.warnings)
        errors: list[str] = list(inspection.errors)

        def _execute_plan(idx: int, p: QuickReportPlan) -> None:
            station_name = self._resolve_substation_display_name(p.package)
            if progress_sink:
                pkg_date = getattr(p.package, 'date_str', '')
                if pkg_date:
                    progress_sink(f"[{idx}/{len(plans)}] [{pkg_date}] Generating quick report for {station_name}...")
                else:
                    progress_sink(f"[{idx}/{len(plans)}] Generating quick report for {station_name}...")
            try:
                out_p = self._composer.load(p)
                if out_p:
                    generated_paths.append(out_p)
            except Exception as e:
                # SubstationIsolatedBatchResiliencePolicy
                errors.append(f"Failed to process {station_name}: {e}")
                logger.exception(f"Failed to process {station_name}")

        if com_session is not None:
            with com_session as session:
                word_app = getattr(session, "word_app", None) or getattr(com_session, "word_app", None)
                orig_word_app = getattr(self._compiler, "_word_app", None)
                if word_app is not None and hasattr(self._compiler, "_word_app"):
                    self._compiler._word_app = word_app
                try:
                    for i, plan in enumerate(plans, start=1):
                        _execute_plan(i, plan)
                finally:
                    if hasattr(self._compiler, "_word_app"):
                        self._compiler._word_app = orig_word_app
        else:
            for i, plan in enumerate(plans, start=1):
                session_fn = getattr(self._compiler, "session", None)
                session_cm = session_fn() if callable(session_fn) else nullcontext()
                if not hasattr(session_cm, "__enter__"):
                    session_cm = nullcontext()

                with session_cm:
                    _execute_plan(i, plan)

        return self._audit_and_build_result(generated_paths, warnings, errors)

    def inspect(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        *,
        station: str | Sequence[str] | None = None,
        condition_template: Path | None = None,
    ) -> QuickReportInspection:
        """Dry-run discovery and plan synthesis without COM or disk writes."""
        inspection, _ = self._plan(
            target,
            environment,
            station=station,
            condition_template=condition_template,
        )
        return inspection

    def _plan(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        *,
        station: str | Sequence[str] | None = None,
        condition_template: Path | None = None,
    ) -> tuple[QuickReportInspection, list[QuickReportStationPlan]]:
        """Synthesize dry-run discovery, filtering, and defect transformation."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        folders, fls = self._resolve_target(target, environment)
        cond_tpl = self._resolve_condition_template(environment, condition_template)
        missing_templates = self._validate_templates(environment, cond_tpl)

        warnings: list[str] = []
        errors: list[str] = []
        items: list[SubstationInspectionItem] = []
        plans: list[QuickReportStationPlan] = []

        try:
            packages = self._extractor.extract(
                environment,
                folders=folders,
                fls=fls,
            )
            filtered_packages = [pkg for pkg in packages if pkg.data is not None]
            if station:
                filtered_packages = [
                    pkg for pkg in filtered_packages if self._matches_station(pkg, station)
                ]
            if fls:
                target_fls = {normalize_functional_location_input(fl) for fl in fls}
                filtered_packages = [
                    pkg
                    for pkg in filtered_packages
                    if getattr(pkg, "data", None)
                    and normalize_functional_location_input(pkg.data.fl_erms) in target_fls
                ]
        except Exception as exc:
            errors.append(f"Package discovery failed: {exc}")
            inspection = QuickReportInspection(
                targets=(),
                missing_templates=missing_templates,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )
            return inspection, []

        if not filtered_packages:
            warnings.append(f"No testsheet packages found for target: {target}")

        for pkg in filtered_packages:
            station_name = self._resolve_substation_display_name(pkg)
            try:
                cbm_defects, vi_defects = self._extractor.extract_defects(pkg, environment)
                plan = self._transformer.transform(
                    pkg=pkg,
                    cbm_defects=cbm_defects,
                    vi_defects=vi_defects,
                    environment=environment,
                    cond_template_path=cond_tpl,
                )
                plans.append(plan)

                sub_name = sanitize_filename(self._resolve_substation_display_name(pkg))
                fl_name = self._resolve_fl(pkg)

                stem = (
                    plan.output_filename[:-5]
                    if plan.output_filename.endswith(".docx")
                    else plan.output_filename
                )

                item = SubstationInspectionItem(
                    pe_number=pkg.substation_number,
                    substation_name=sub_name,
                    functional_location=fl_name,
                    defect_suffix=plan.suffix,
                    stem=stem,
                    target_output_path=plan.final_output_path,
                    cbm_defect_count=len(plan.cbm_defects),
                    vi_defect_count=len(plan.vi_defects),
                    condition_pair_count=len(plan.condition_pairs),
                    station=pkg.station or (pkg.data.station_name if pkg.data else "") or "",
                )
                items.append(item)
            except Exception as e:
                # SubstationIsolatedBatchResiliencePolicy
                errors.append(f"Failed to process {station_name}: {e}")
                logger.exception(f"Failed to process {station_name}")

        inspection = QuickReportInspection(
            targets=tuple(items),
            missing_templates=missing_templates,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )
        return inspection, plans

    def _resolve_condition_template(
        self, environment: ProjectEnvironment, condition_template: Path | None
    ) -> Path | None:
        """Resolve condition template from explicit parameter or project environment default."""
        if condition_template is not None:
            return condition_template
        if hasattr(environment, "get_sub_cond_dir"):
            try:
                candidate = environment.get_sub_cond_dir() / "MASTER_SUBSTATION_CONDITION.docx"
                return candidate
            except Exception:
                pass
        return None

    def _resolve_substation_display_name(self, pkg: SubstationTestsheetPackage) -> str:
        """Return canonical substation display name or fallback for progress and logging."""
        if getattr(pkg, "data", None):
            name = pkg.data.substation_name_erms or pkg.data.station_name or pkg.station
            if name:
                return str(name)
        if getattr(pkg, "station", ""):
            return str(pkg.station)
        sub_num = getattr(pkg, "substation_number", None)
        return f"substation {sub_num}" if sub_num is not None else "unknown substation"

    _resolve_station_display_name = _resolve_substation_display_name

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

        return (pkg_station_str in target_stations) or (data_station_str in target_stations)

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

    def _target_path_exists(
        self, target: Path | str, environment: ProjectEnvironment
    ) -> bool:
        """Return True if target exists either directly or relative to testsheet directory."""
        path = Path(target)
        if not path.is_absolute() and hasattr(environment, "get_testsheet_dir"):
            return path.exists() or (environment.get_testsheet_dir() / path).exists()
        return path.exists()

    def _resolve_target(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
    ) -> tuple[Sequence[str] | None, Sequence[str] | None]:
        """Convert polymorphic ReportTarget into (folders, fls) pair."""
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

    def _validate_templates(
        self, environment: ProjectEnvironment, condition_template: Path | None
    ) -> tuple[str, ...]:
        """Validate required document templates and return tuple of missing descriptions."""
        missing: list[str] = []
        try:
            front_page = environment.get_vi_front_page_template()
            if not front_page or not front_page.exists():
                missing.append(f"VI front page template missing at: {front_page}")
        except Exception as e:
            missing.append(f"VI front page template missing: {e}")

        try:
            sticker = environment.get_template("sticker_page")
            if not sticker or not sticker.exists():
                missing.append(f"Sticker page template missing at: {sticker}")
        except Exception as e:
            missing.append(f"Sticker page template missing: {e}")

        if condition_template is None or not condition_template.exists():
            missing.append(
                f"Substation condition template missing at: {condition_template}"
            )

        return tuple(missing)

    def _audit_and_build_result(
        self,
        generated_paths: list[Path],
        warnings: list[str],
        errors: list[str],
    ) -> QuickReportResult:
        """Verify written report files and construct QuickReportResult telemetry."""
        verified_paths: list[Path] = []
        for path in generated_paths:
            if path.exists() and path.stat().st_size > 0:
                verified_paths.append(path)
            else:
                errors.append(f"Generated report at {path} is missing or 0 bytes.")

        return QuickReportResult(
            reports_generated=len(verified_paths),
            generated_paths=tuple(verified_paths),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )
