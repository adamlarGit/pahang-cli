"""Standalone US+TEV survey graph generation workflow engine (Ticket #73).

Generates PRPD graphs across discovered measurements into <SUBSTATION>/RAW DATA/US+TEV/graphs/
using Option C (composite HTML headless rendering) or Option B (pure Matplotlib scatter plot).
Adheres to SubstationIsolatedBatchResiliencePolicy and BrowserPrerequisitePolicy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import time
from typing import Any, Callable, Sequence

from src.cli_selectors import (
    SelectOption,
    prompt_target_inspection_dates_with_ranges,
    select_multiple,
    select_one,
    select_pahang_inspection_dates_interactive,
)
from src.quick_report.extractor import QuickReportExtractor
from src.quick_report.prpd import (
    DiscoveredMeasurement,
    SurveyHttpServer,
    decode_tev_event_data,
    decode_ultrasonic_phase_plot,
    discover_survey_measurements,
    discover_ultratev_survey_dir,
    find_chrome_executable,
    generate_prpd_figure,
    render_prpd_option_c_image,
    resolve_survey_container_dir,
)
from src.project.models import PrpdMode
from src.run_records import current_run
from src.testsheet.models import SubstationTestsheetPackage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsTevCandidate:
    """Discovered candidate substation containing valid US+TEV survey data."""

    package: SubstationTestsheetPackage
    raw_data_dir: Path
    survey_dir: Path
    output_dir: Path


class BrowserPrerequisiteError(RuntimeError):
    """Raised when Option C is requested but neither Google Chrome nor Microsoft Edge is available."""

    def __init__(
        self,
        message: str = (
            "Option C PRPD rendering requires Google Chrome or Microsoft Edge, but neither was found. "
            "Please install Google Chrome / Microsoft Edge or switch PRPD mode to Option B in Settings."
        ),
    ) -> None:
        super().__init__(message)


@dataclass
class UsTevWorkflowSummary:
    """Summary of execution across a batch of substations."""

    total_substations: int = 0
    total_graphs: int = 0
    total_skipped_no_data: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_time: float = 0.0


@dataclass
class SubstationGraphResult:
    """Outcome of graph generation for one substation survey."""

    generated: list[Path] = field(default_factory=list)
    skipped_no_data: list[str] = field(default_factory=list)


def generate_substation_graphs(
    survey_root: Path | str,
    output_dir: Path | str,
    mode: PrpdMode = "option_c",
) -> SubstationGraphResult:
    """Generate US and TEV PRPD graphs for all discovered measurements in a survey directory.

    Idempotently writes or overwrites image files at `<output_dir>/<label>.png`.
    Placeholder measurements (no recorded data file) are skipped and listed in
    `skipped_no_data` instead of being rendered.
    """
    survey_root_path = Path(survey_root).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    result = SubstationGraphResult()

    measurements = discover_survey_measurements(survey_root_path)
    if not measurements:
        logger.warning("[WARN] No valid US/TEV measurements found in survey %s", survey_root_path)
        return result

    recorded: list[DiscoveredMeasurement] = []
    for meas in measurements:
        if meas.has_recorded_data:
            recorded.append(meas)
        else:
            logger.warning("%s: no %s data recorded (skipped)", meas.label, meas.tech)
            result.skipped_no_data.append(meas.label)
    measurements = recorded

    norm_mode = mode.lower()

    if norm_mode == "option_c":
        with SurveyHttpServer(survey_root_path, temp_dir=out_dir) as port:
            for meas in measurements:
                target_png = out_dir / f"{meas.label}.png"
                html_file = meas.meas_dir / meas.html_file
                if not html_file.is_file():
                    logger.warning("Target HTML file not found for %s: %s", meas.label, html_file)
                    continue

                res = render_prpd_option_c_image(
                    html_file=html_file,
                    output_png=target_png,
                    survey_root=survey_root_path,
                    http_port=port,
                )
                if res and res.is_file():
                    result.generated.append(res)
    else:
        # Default / Option B (Matplotlib native decoding)
        for meas in measurements:
            target_png = out_dir / f"{meas.label}.png"
            decode = decode_tev_event_data if meas.tech == "TEV" else decode_ultrasonic_phase_plot
            try:
                events: list[dict[str, Any]] = decode(meas.data_file)
            except Exception as exc:
                logger.warning("Failed decoding %s data for %s: %s", meas.tech, meas.label, exc)
                continue

            try:
                res = generate_prpd_figure(events, meas.tech, target_png)
                if res and res.is_file():
                    result.generated.append(res)
            except Exception as exc:
                logger.warning("Failed generating PRPD figure for %s: %s", meas.label, exc)

    return result


def resolve_us_tev_graphs_output_dir(survey_dir: Path | str) -> Path:
    """Resolve canonical graphs output directory via 2-level bounded container check.

    Checks survey_dir.name then survey_dir.parent.name for 'US' or 'US+TEV'.
    Target: <SUBSTATION>/RAW DATA/<CONTAINER>/graphs/
    Raises ValueError if neither container is detected.
    """
    return resolve_survey_container_dir(survey_dir) / "graphs"


class UsTevGraphWorkflow:
    """Coordinates Phase-Resolved Partial Discharge (PRPD) graph generation across substations."""

    def __init__(self, mode: PrpdMode = "option_c") -> None:
        self.mode: PrpdMode = mode.lower() if isinstance(mode, str) else mode  # type: ignore[assignment]

    def check_browser_prerequisite(self) -> str:
        """Validate Chromium browser presence if running in Option C."""
        if self.mode == "option_c":
            try:
                browser = find_chrome_executable()
                if not browser:
                    raise BrowserPrerequisiteError()
                return browser
            except (FileNotFoundError, Exception) as exc:
                if isinstance(exc, BrowserPrerequisiteError):
                    raise
                raise BrowserPrerequisiteError() from exc
        return ""

    def run_substation(self, survey_root: Path | str, output_dir: Path | str | None = None) -> SubstationGraphResult:
        """Generate graphs for a single substation survey root."""
        s_root = Path(survey_root).resolve()
        resolved_root = discover_ultratev_survey_dir(s_root) or s_root

        if output_dir:
            out_path = Path(output_dir).resolve()
        else:
            out_path = resolve_us_tev_graphs_output_dir(resolved_root)

        return generate_substation_graphs(resolved_root, out_path, self.mode)

    def run_batch(
        self,
        substations: Sequence[tuple[Any, ...]],
        on_progress: Callable[[int, int, str, int, int, Path], None] | None = None,
    ) -> UsTevWorkflowSummary:
        """Execute batch graph generation adhering to SubstationIsolatedBatchResiliencePolicy."""
        start_time = time.time()
        summary = UsTevWorkflowSummary(total_substations=len(substations))

        # Pre-flight browser check before batch execution
        self.check_browser_prerequisite()

        total = len(substations)
        for idx, item in enumerate(substations, start=1):
            substation_item = item[0]
            raw_or_survey_dir = item[1]
            explicit_output_dir = item[2] if len(item) >= 3 else None

            path_obj = Path(raw_or_survey_dir).resolve()
            survey_root = discover_ultratev_survey_dir(path_obj) or path_obj

            item_label = (
                _format_package_label(substation_item)
                if hasattr(substation_item, "station") or hasattr(substation_item, "substation_number") or hasattr(substation_item, "data")
                else str(substation_item)
            )

            try:
                if explicit_output_dir is not None:
                    output_dir = Path(explicit_output_dir).resolve()
                else:
                    output_dir = resolve_us_tev_graphs_output_dir(survey_root)

                result = self.run_substation(survey_root, output_dir)
                count = len(result.generated)
                skipped = len(result.skipped_no_data)
                summary.total_graphs += count
                summary.total_skipped_no_data += skipped
                if count:
                    current_run().record_outputs([output_dir])
                if on_progress:
                    on_progress(idx, total, item_label, count, skipped, output_dir)
            except Exception as exc:
                err_msg = f"Failed generating graphs for {item_label}: {exc}"
                current_run().record_error(err_msg, exc)
                logger.error(err_msg, exc_info=True)
                summary.errors.append(err_msg)

        if total and len(summary.errors) >= total:
            current_run().mark_failed()

        summary.elapsed_time = time.time() - start_time
        return summary


def discover_us_tev_candidate_substations(
    environment: Any,
    target_dates: Sequence[Path | str],
) -> list[UsTevCandidate]:
    """Discover testsheet packages across target dates that contain valid US+TEV survey folders.

    Returns list of UsTevCandidate dataclasses.
    """
    extractor = QuickReportExtractor()
    packages = extractor.extract(environment, folders=target_dates)

    candidates: list[UsTevCandidate] = []
    for pkg in packages:
        raw_dir = environment.storage.get_substation_raw_data_dir(
            pkg.station,
            pkg.month,
            pkg.date_str,
            pkg.substation_number,
        )
        if not raw_dir:
            continue
        raw_dir_path = Path(raw_dir)
        survey_dir = discover_ultratev_survey_dir(raw_dir_path)
        if survey_dir is not None and survey_dir.exists():
            output_dir = resolve_us_tev_graphs_output_dir(survey_dir)
            candidates.append(
                UsTevCandidate(
                    package=pkg,
                    raw_data_dir=raw_dir_path,
                    survey_dir=survey_dir,
                    output_dir=output_dir,
                )
            )

    return candidates


def _format_package_label(pkg: Any) -> str:
    """Resolve human-readable substation name from package with inspection date prefix."""
    name = getattr(pkg, "substation_name", None) or getattr(pkg, "substation_folder", None)
    if not name and getattr(pkg, "data", None):
        name = pkg.data.substation_name_site or pkg.data.substation_name_erms
    if not name and hasattr(pkg, "substation_number"):
        name = f"PE {pkg.substation_number}"
    date_tag = getattr(pkg, "date_str", "")
    return f"[{date_tag}] {name}" if date_tag else str(name or "Unknown Substation")


def select_us_tev_substations_interactive(
    candidates: list[UsTevCandidate],
) -> list[UsTevCandidate]:
    """Interactive single merged checklist selector for candidate substations across all dates."""
    if not candidates:
        return []

    options: list[SelectOption[UsTevCandidate]] = []
    for candidate in candidates:
        pkg = candidate.package
        title = _format_package_label(pkg)
        options.append(SelectOption(title=title, value=candidate, checked=True))

    selected = select_multiple(
        "Select substations to generate US+TEV survey graphs ('a' toggles all):",
        options,
    )
    if not selected:
        return []
    return list(selected)


def run_generate_us_tev_graphs_action(environment: Any) -> UsTevWorkflowSummary | None:
    """CLI utility action to independently generate US+TEV survey graphs."""
    print("\n[UTILITY] Standalone US+TEV Survey Graph Generation...")
    options = [
        SelectOption("Browse Date Folders (Interactive Checklist)", "browse_dates"),
        SelectOption("Enter Target Date(s) (Text Input / Range)", "enter_dates"),
        SelectOption("Cancel", "__cancel__", shortcut_key="c"),
    ]

    while True:
        mode_str = select_one("Generate US+TEV Survey Graphs - Select Date Mode", options)
        if mode_str in ("__cancel__", None):
            print("Operation cancelled.")
            return None

        if mode_str == "browse_dates":
            selected_dates = select_pahang_inspection_dates_interactive(environment)
        else:
            selected_dates = prompt_target_inspection_dates_with_ranges(environment)

        if not selected_dates:
            continue
        break

    folder_dates = [d.name if isinstance(d, Path) else str(d) for d in selected_dates]
    candidates = discover_us_tev_candidate_substations(environment, folder_dates)
    if not candidates:
        print("\n[WARN] No substations with valid US+TEV survey data found in selected date(s).")
        return None

    selected_candidates = select_us_tev_substations_interactive(candidates)
    if not selected_candidates:
        print("No substations selected. Operation cancelled.")
        return None

    prpd_config = environment.get_prpd_config()
    render_mode = getattr(prpd_config, "mode", "option_c")

    current_run().record_request(
        {
            "workflow": "US+TEV Survey Graphs",
            "dates": folder_dates,
            "mode": render_mode,
            "substations": [_format_package_label(candidate.package) for candidate in selected_candidates],
        }
    )
    for candidate in selected_candidates:
        current_run().record_input_folder(candidate.survey_dir, recursive=True)
    current_run().record_inputs(candidate.package.testsheet_path for candidate in selected_candidates)

    workflow = UsTevGraphWorkflow(mode=render_mode)
    try:
        workflow.check_browser_prerequisite()
    except BrowserPrerequisiteError as exc:
        current_run().record_failure(f"Browser Prerequisite Error: {exc}", exc)
        print(f"\n[ERROR] Browser Prerequisite Error: {exc}")
        return None

    print(
        f"\n[INFO] Starting US+TEV graph generation for {len(selected_candidates)} "
        f"substation(s) in {render_mode.upper()} mode..."
    )

    batch: list[tuple[Any, Path, Path]] = [
        (cand.package, cand.survey_dir, cand.output_dir)
        for cand in selected_candidates
    ]

    def _on_progress(idx: int, total: int, pe_name: str, count: int, skipped: int, out_dir: Path) -> None:
        skipped_note = f", skipped {skipped} (no data)" if skipped else ""
        print(f"[{idx}/{total}] {pe_name}: Generated {count} graphs{skipped_note} -> {out_dir}")

    summary = workflow.run_batch(batch, on_progress=_on_progress)

    print("\n" + "=" * 80)
    print("US+TEV SURVEY GRAPH GENERATION SUMMARY")
    print("=" * 80)
    print(f"Total Substations Processed: {summary.total_substations}")
    print(f"Total Graphs Generated:     {summary.total_graphs}")
    print(f"Skipped (no data recorded): {summary.total_skipped_no_data}")
    print(f"Elapsed Time:               {summary.elapsed_time:.2f} seconds")
    if summary.errors:
        print(f"\nErrors ({len(summary.errors)}):")
        for err in summary.errors:
            print(f"  - {err}")
    print("=" * 80)
    return summary

