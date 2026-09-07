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

ReportTarget = Path | str | Sequence[str]
ProgressSink = Callable[[str], None]


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
        condition_template: Path | None = None,
        progress_sink: ProgressSink | None = None,
    ) -> QuickReportResult:
        """End-to-end: discover -> filter -> transform -> compile."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        request = self._resolve_request(
            target, environment, condition_template, progress_sink=progress_sink
        )

        missing_templates = self._validate_templates(
            environment, request.substation_condition_template_path
        )
        if missing_templates:
            return QuickReportResult(
                reports_generated=0,
                generated_paths=(),
                warnings=(),
                errors=tuple(f"Required template missing: {t}" for t in missing_templates),
            )

        if progress_sink:
            progress_sink("Discovering target packages for Quick Report...")

        try:
            packages = self._extractor.extract(environment, request)
            filtered_packages = self._filter.filter(packages, request)
        except Exception as exc:
            return QuickReportResult(
                reports_generated=0,
                generated_paths=(),
                warnings=(),
                errors=(f"Package discovery failed: {exc}",),
            )

        if not filtered_packages:
            return QuickReportResult(
                reports_generated=0,
                generated_paths=(),
                warnings=(),
                errors=(f"No testsheet packages found for target: {target}",),
            )

        if progress_sink:
            progress_sink(f"Found {len(filtered_packages)} packages to process.")

        generated_paths: list[Path] = []
        warnings: list[str] = []
        errors: list[str] = []

        session_fn = getattr(self._compiler, "session", None)
        session_cm = session_fn() if callable(session_fn) else nullcontext()
        if not hasattr(session_cm, "__enter__"):
            session_cm = nullcontext()

        with session_cm:
            for i, pkg in enumerate(filtered_packages, start=1):
                station_name = (
                    getattr(pkg, "station", "")
                    or getattr(getattr(pkg, "data", None), "station_name", "")
                    or f"substation {getattr(pkg, 'substation_number', '?')}"
                )
                if progress_sink:
                    progress_sink(
                        f"[{i}/{len(filtered_packages)}] Generating quick report for {station_name}..."
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
        condition_template: Path | None = None,
    ) -> QuickReportInspection:
        """Dry-run discovery and plan synthesis without COM or disk writes."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        request = self._resolve_request(target, environment, condition_template)
        missing_templates = self._validate_templates(
            environment, request.substation_condition_template_path
        )

        warnings: list[str] = []
        errors: list[str] = []
        items: list[SubstationInspectionItem] = []

        try:
            packages = self._extractor.extract(environment, request)
            filtered_packages = self._filter.filter(packages, request)
        except Exception as exc:
            errors.append(f"Failed to discover packages: {exc}")
            return QuickReportInspection(
                targets=(),
                missing_templates=missing_templates,
                warnings=tuple(warnings),
                errors=tuple(errors),
            )

        if not filtered_packages:
            warnings.append(f"No packages found for target: {target}")

        for pkg in filtered_packages:
            try:
                cbm_defects, vi_defects = self._extractor.extract_defects(pkg, environment)
                plan = self._transformer.transform(
                    pkg=pkg,
                    cbm_defects=cbm_defects,
                    vi_defects=vi_defects,
                    environment=environment,
                    cond_template_path=request.substation_condition_template_path,
                )

                sub_name = (
                    getattr(getattr(pkg, "data", None), "substation_name_erms", "")
                    or getattr(pkg, "station", "")
                    or ""
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
                station_name = (
                    getattr(pkg, "station", "")
                    or getattr(getattr(pkg, "data", None), "station_name", "")
                    or f"substation {getattr(pkg, 'substation_number', '?')}"
                )
                errors.append(f"Failed to inspect {station_name}: {e}")
                logger.exception(f"Failed to inspect {station_name}")

        return QuickReportInspection(
            targets=tuple(items),
            missing_templates=missing_templates,
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

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
    ) -> QuickReportRequest:
        """Convert polymorphic ReportTarget into an internal QuickReportRequest."""
        cond_tpl = self._resolve_condition_template(environment, condition_template)

        if isinstance(target, Path):
            return QuickReportRequest(
                mode=QuickReportMode.FOLDER,
                target_folders=(str(target),),
                substation_condition_template_path=cond_tpl,
                progress_sink=progress_sink,
            )
        elif isinstance(target, str):
            return QuickReportRequest(
                mode=QuickReportMode.FOLDER,
                target_folders=(target,),
                substation_condition_template_path=cond_tpl,
                progress_sink=progress_sink,
            )
        elif isinstance(target, Sequence):
            return QuickReportRequest(
                mode=QuickReportMode.FL,
                target_package_names=tuple(target),
                substation_condition_template_path=cond_tpl,
                progress_sink=progress_sink,
            )
        else:
            raise TypeError(
                f"Unsupported target type: {type(target)}. Expected Path, str, or Sequence[str]."
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
