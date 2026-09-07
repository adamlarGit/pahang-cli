"""Quick Report workflow orchestrator deep module exposing generate() and inspect()."""

from __future__ import annotations

from contextlib import nullcontext
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

from src.quick_report.compiler import (
    DocumentCompiler,
    WordComDocumentCompiler,
)

try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None
    win32com = None
from src.quick_report.composer import QuickReportComposer
from src.quick_report.extractor import QuickReportExtractor
from src.quick_report.filter import QuickReportFilter
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.transformer import QuickReportTransformer
from src.quick_report.utils import (
    is_pahang_date_str,
    sanitize_filename,
    validate_date_string,
)
from src.workflows.models import (
    QuickReportInspection,
    QuickReportMode,
    QuickReportRequest,
    QuickReportResult,
    SubstationInspectionItem,
)

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment

logger = logging.getLogger(__name__)

ReportTarget = Path | str | Sequence[Path] | Sequence[str] | Sequence[Path | str]
ProgressSink = Callable[[str], None]


def _is_date_or_folder(item: Path | str, environment: ProjectEnvironment) -> bool:
    """Check if an item represents a Pahang date string or an existing folder path."""
    if isinstance(item, Path):
        return True
    if is_pahang_date_str(item):
        return True
    s = str(item).strip()
    try:
        p = Path(s)
        if p.is_dir() is True:
            return True
    except Exception:
        pass
    try:
        if hasattr(environment, "get_testsheet_dir"):
            ts_dir = environment.get_testsheet_dir()
            if isinstance(ts_dir, Path) and (ts_dir / s).is_dir() is True:
                return True
    except Exception:
        pass
    return False


class QuickReportWorkflow:
    """Deep module orchestrating the 6-stage Quick Report ETL pipeline.

    Presents exactly two primary entry points:
    - generate(): End-to-end extraction, planning, rendering, and COM compilation.
    - inspect(): In-process dry-run planning, suffix calculations, and template audits.
    """

    def __init__(
        self,
        compiler: DocumentCompiler | None = None,
        extractor: QuickReportExtractor | None = None,
        filter_stage: QuickReportFilter | None = None,
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
        self._filter = filter_stage or QuickReportFilter()
        self._transformer = transformer or QuickReportTransformer()
        self._composer = composer or QuickReportComposer(compiler=self._compiler)

    @property
    def extractor(self) -> QuickReportExtractor:
        return self._extractor

    @extractor.setter
    def extractor(self, val: QuickReportExtractor) -> None:
        self._extractor = val

    @property
    def filter_stage(self) -> QuickReportFilter:
        return self._filter

    @filter_stage.setter
    def filter_stage(self, val: QuickReportFilter) -> None:
        self._filter = val

    @property
    def transformer(self) -> QuickReportTransformer:
        return self._transformer

    @transformer.setter
    def transformer(self, val: QuickReportTransformer) -> None:
        self._transformer = val

    @property
    def composer(self) -> QuickReportComposer:
        return self._composer

    @composer.setter
    def composer(self, val: QuickReportComposer) -> None:
        self._composer = val

    def generate(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        *,
        station: str | None = None,
        condition_template: Path | None = None,
        progress_sink: ProgressSink | None = None,
    ) -> QuickReportResult:
        """End-to-end: discover -> filter -> transform -> compile."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        if progress_sink:
            progress_sink("Discovering target packages for Quick Report...")

        inspection, plans = self._plan(
            target,
            environment,
            station=station,
            condition_template=condition_template,
            progress_sink=progress_sink,
        )

        if inspection.missing_templates:
            return QuickReportResult(
                reports_generated=0,
                generated_paths=(),
                warnings=inspection.warnings,
                errors=tuple(
                    f"Required template missing: {t}" for t in inspection.missing_templates
                ),
            )

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

        session_fn = getattr(self._compiler, "session", None)
        session_cm = session_fn() if callable(session_fn) else nullcontext()
        if not hasattr(session_cm, "__enter__"):
            session_cm = nullcontext()

        with session_cm:
            for i, plan in enumerate(plans, start=1):
                station_name = (
                    getattr(plan.package, "station", "")
                    or getattr(getattr(plan.package, "data", None), "station_name", "")
                    or f"substation {plan.substation_number}"
                )
                if progress_sink:
                    progress_sink(
                        f"[{i}/{len(plans)}] Generating quick report for {station_name}..."
                    )

                try:
                    out_path = self._composer.load(plan)
                    if out_path:
                        generated_paths.append(out_path)
                except Exception as e:
                    # SubstationIsolatedBatchResiliencePolicy
                    errors.append(f"Failed to process {station_name}: {e}")
                    logger.exception(f"Failed to process {station_name}")

        return self._audit_and_build_result(generated_paths, warnings, errors)

    def inspect(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        *,
        station: str | None = None,
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
        station: str | None = None,
        condition_template: Path | None = None,
        progress_sink: ProgressSink | None = None,
    ) -> tuple[QuickReportInspection, list[QuickReportStationPlan]]:
        """Synthesize dry-run discovery, filtering, and defect transformation."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        request = self._resolve_request(
            target,
            environment,
            condition_template=condition_template,
            progress_sink=progress_sink,
            station=station,
        )

        missing_templates = self._validate_templates(
            environment, request.substation_condition_template_path
        )

        warnings: list[str] = []
        errors: list[str] = []
        items: list[SubstationInspectionItem] = []
        plans: list[QuickReportStationPlan] = []

        try:
            packages = self._extractor.extract(environment, request)
            filtered_packages = self._filter.filter(packages, request, station=station)
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
            station_name = (
                getattr(pkg, "station", "")
                or getattr(getattr(pkg, "data", None), "station_name", "")
                or f"substation {getattr(pkg, 'substation_number', '?')}"
            )
            try:
                cbm_defects, vi_defects = self._extractor.extract_defects(pkg, environment)
                plan = self._transformer.transform(
                    pkg=pkg,
                    cbm_defects=cbm_defects,
                    vi_defects=vi_defects,
                    environment=environment,
                    cond_template_path=request.substation_condition_template_path,
                )
                plans.append(plan)

                sub_name = (
                    sanitize_filename(pkg.data.substation_name_erms or pkg.data.station_name)
                    if pkg.data
                    else sanitize_filename(pkg.station or "")
                )
                fl_name = getattr(getattr(pkg, "data", None), "fl_erms", "") or ""
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

    def execute(
        self, environment: ProjectEnvironment, request: QuickReportRequest
    ) -> QuickReportResult:
        """Legacy execute() entry point for backward compatibility."""
        self._validate_preconditions(environment, request)

        if getattr(request.mode, "value", str(request.mode)).lower() == "fl":
            target: ReportTarget = list(request.target_package_names)
        else:
            target = (
                Path(request.target_folders[0])
                if request.target_folders
                else environment.get_testsheet_dir()
            )

        return self.generate(
            target,
            environment,
            station=request.station,
            condition_template=request.substation_condition_template_path,
            progress_sink=request.progress_sink,
        )

    def _resolve_condition_template(
        self, environment: ProjectEnvironment, condition_template: Path | None
    ) -> Path | None:
        """Resolve condition template from explicit parameter or project environment default."""
        if condition_template is not None:
            return condition_template
        if hasattr(environment, "get_sub_cond_dir"):
            try:
                candidate = environment.get_sub_cond_dir() / "MASTER_SUBSTATION_CONDITION.docx"
                if candidate.exists():
                    return candidate
            except Exception:
                pass
        return None

    def _resolve_request(
        self,
        target: ReportTarget,
        environment: ProjectEnvironment,
        condition_template: Path | None = None,
        progress_sink: ProgressSink | None = None,
        station: str | None = None,
    ) -> QuickReportRequest:
        """Convert polymorphic ReportTarget into an internal QuickReportRequest."""
        cond_tpl = self._resolve_condition_template(environment, condition_template)

        if isinstance(target, Path):
            validate_date_string(target.name)
            return QuickReportRequest(
                mode=QuickReportMode.FOLDER,
                target_folders=(str(target),),
                substation_condition_template_path=cond_tpl,
                progress_sink=progress_sink,
                station=station,
            )
        elif isinstance(target, str):
            validate_date_string(target)
            return QuickReportRequest(
                mode=QuickReportMode.FOLDER,
                target_folders=(target,),
                substation_condition_template_path=cond_tpl,
                progress_sink=progress_sink,
                station=station,
            )
        elif isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            items = list(target)
            for item in items:
                if isinstance(item, str):
                    validate_date_string(item)
                elif isinstance(item, Path):
                    validate_date_string(item.name)

            if any(_is_date_or_folder(item, environment) for item in items):
                return QuickReportRequest(
                    mode=QuickReportMode.FOLDER,
                    target_folders=tuple(str(item) for item in items),
                    substation_condition_template_path=cond_tpl,
                    progress_sink=progress_sink,
                    station=station,
                )
            else:
                return QuickReportRequest(
                    mode=QuickReportMode.FL,
                    target_package_names=tuple(str(item) for item in items),
                    substation_condition_template_path=cond_tpl,
                    progress_sink=progress_sink,
                    station=station,
                )
        else:
            raise TypeError(
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

        if condition_template is not None and not condition_template.exists():
            missing.append(
                f"Substation condition template missing at: {condition_template}"
            )

        return tuple(missing)

    def _validate_preconditions(
        self, environment: ProjectEnvironment, request: QuickReportRequest
    ) -> None:
        """Validate input request parameters and environment template preconditions (legacy)."""
        if request is None:
            raise ValueError("QuickReportRequest cannot be None.")
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        missing = self._validate_templates(
            environment, request.substation_condition_template_path
        )
        if missing:
            raise FileNotFoundError(missing[0])

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
