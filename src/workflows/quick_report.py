"""Quick Report workflow orchestrator deep module exposing generate() and inspect()."""

from __future__ import annotations

from contextlib import nullcontext
import logging
from pathlib import Path
import re
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
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.transformer import QuickReportTransformer
from src.quick_report.utils import (
    normalize_functional_location_input,
    sanitize_filename,
)
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
_DAILY_DATE_FOLDER_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")


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
    ) -> QuickReportResult:
        """End-to-end: discover -> filter -> transform -> compile."""
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        # Fail fast if an explicit Path target was given but missing
        if isinstance(target, Path):
            if not target.is_absolute() and hasattr(environment, "get_testsheet_dir"):
                exists = target.exists() or (environment.get_testsheet_dir() / target).exists()
            else:
                exists = target.exists()
            if not exists:
                raise FileNotFoundError(f"Target path does not exist: {target}")
        elif isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            for item in target:
                if isinstance(item, Path):
                    if not item.is_absolute() and hasattr(environment, "get_testsheet_dir"):
                        exists = item.exists() or (environment.get_testsheet_dir() / item).exists()
                    else:
                        exists = item.exists()
                    if not exists:
                        raise FileNotFoundError(f"Target path does not exist: {item}")

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

        session_fn = getattr(self._compiler, "session", None)
        session_cm = session_fn() if callable(session_fn) else nullcontext()
        if not hasattr(session_cm, "__enter__"):
            session_cm = nullcontext()

        with session_cm:
            for i, plan in enumerate(plans, start=1):
                station_name = (
                    getattr(plan.package, "station", "")
                    or getattr(getattr(plan.package, "data", None), "station_name", "")
                    or f"substation {getattr(plan.package, 'substation_number', '?')}"
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
        progress_sink: ProgressSink | None = None,
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
                if isinstance(station, str):
                    norm_station = station.strip().upper()
                    filtered_packages = [
                        pkg
                        for pkg in filtered_packages
                        if (pkg.station and pkg.station.strip().upper() == norm_station)
                        or (
                            getattr(pkg, "data", None)
                            and getattr(pkg.data, "station_name", "")
                            and getattr(pkg.data, "station_name", "").strip().upper() == norm_station
                        )
                    ]
                elif isinstance(station, Sequence):
                    norm_stations = {s.strip().upper() for s in station if s and str(s).strip()}
                    filtered_packages = [
                        pkg
                        for pkg in filtered_packages
                        if (pkg.station and pkg.station.strip().upper() in norm_stations)
                        or (
                            getattr(pkg, "data", None)
                            and getattr(pkg.data, "station_name", "")
                            and getattr(pkg.data, "station_name", "").strip().upper() in norm_stations
                        )
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
                    cond_template_path=cond_tpl,
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
            is_dir = False
            try:
                p = Path(s)
                if p.is_absolute() and p.is_dir():
                    is_dir = True
            except Exception:
                pass
            if not is_dir and hasattr(environment, "get_testsheet_dir"):
                try:
                    ts_dir = environment.get_testsheet_dir()
                    if isinstance(ts_dir, Path) and (ts_dir / s).is_dir():
                        is_dir = True
                except Exception:
                    pass

            if is_dir:
                return (s,), None
            if _DAILY_DATE_FOLDER_PATTERN.match(s):
                return (s,), None
            return None, [s]
        elif isinstance(target, Sequence) and not isinstance(target, (str, bytes)):
            items = list(target)
            if not items:
                return None, ()

            if all(isinstance(item, Path) for item in items):
                return tuple(str(p) for p in items), None

            def _is_dir_or_date(item: Path | str) -> bool:
                if isinstance(item, Path):
                    return True
                val = str(item).strip()
                if _DAILY_DATE_FOLDER_PATTERN.match(val):
                    return True
                try:
                    p = Path(val)
                    if p.is_absolute() and p.is_dir():
                        return True
                except Exception:
                    pass
                try:
                    if hasattr(environment, "get_testsheet_dir"):
                        ts_dir = environment.get_testsheet_dir()
                        if isinstance(ts_dir, Path) and (ts_dir / val).is_dir():
                            return True
                except Exception:
                    pass
                return False

            if all(_is_dir_or_date(item) for item in items):
                return tuple(str(item) for item in items), None
            else:
                return None, tuple(str(item) for item in items)
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
