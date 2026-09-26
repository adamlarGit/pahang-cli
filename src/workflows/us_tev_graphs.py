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
from typing import Any, Callable

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
)

logger = logging.getLogger(__name__)


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
    errors: list[str] = field(default_factory=list)
    elapsed_time: float = 0.0


def generate_substation_graphs(
    survey_root: Path | str,
    output_dir: Path | str,
    mode: str = "option_c",
) -> list[Path]:
    """Generate US and TEV PRPD graphs for all discovered measurements in a survey directory.

    Idempotently writes or overwrites image files at `<output_dir>/<label>.png`.
    Returns list of generated image file paths.
    """
    survey_root_path = Path(survey_root).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    measurements = discover_survey_measurements(survey_root_path)
    if not measurements:
        logger.warning("[WARN] No valid US/TEV measurements found in survey %s", survey_root_path)
        return []

    norm_mode = mode.lower()
    generated_paths: list[Path] = []

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
                    generated_paths.append(res)
    else:
        # Default / Option B (Matplotlib native decoding)
        for meas in measurements:
            target_png = out_dir / f"{meas.label}.png"
            events: list[dict[str, Any]] = []

            if meas.tech == "TEV":
                data_file = meas.meas_dir / "eventData.js"
                if not data_file.is_file():
                    logger.warning("TEV event data file missing for %s: %s", meas.label, data_file)
                    continue
                try:
                    events = decode_tev_event_data(data_file)
                except Exception as exc:
                    logger.warning("Failed decoding TEV event data for %s: %s", meas.label, exc)
                    continue
            else:
                data_file = meas.meas_dir / "ultrasonic_phase_plot.js"
                if not data_file.is_file():
                    logger.warning("US phase plot file missing for %s: %s", meas.label, data_file)
                    continue
                try:
                    events = decode_ultrasonic_phase_plot(data_file)
                except Exception as exc:
                    logger.warning("Failed decoding US phase plot for %s: %s", meas.label, exc)
                    continue

            try:
                res = generate_prpd_figure(events, meas.tech, target_png)
                if res and res.is_file():
                    generated_paths.append(res)
            except Exception as exc:
                logger.warning("Failed generating PRPD figure for %s: %s", meas.label, exc)

    return generated_paths


class UsTevGraphWorkflow:
    """Coordinates Phase-Resolved Partial Discharge (PRPD) graph generation across substations."""

    def __init__(self, mode: str = "option_c") -> None:
        self.mode = mode.lower()

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

    def run_substation(self, survey_root: Path | str, output_dir: Path | str | None = None) -> list[Path]:
        """Generate graphs for a single substation survey root."""
        s_root = Path(survey_root).resolve()
        resolved_root = discover_ultratev_survey_dir(s_root) or s_root

        out_path = Path(output_dir).resolve() if output_dir else resolved_root / "graphs"
        return generate_substation_graphs(resolved_root, out_path, self.mode)

    def run_batch(
        self,
        substations: list[tuple[Any, Path | str]],
        on_progress: Callable[[int, int, str, int, Path], None] | None = None,
    ) -> UsTevWorkflowSummary:
        """Execute batch graph generation adhering to SubstationIsolatedBatchResiliencePolicy."""
        start_time = time.time()
        summary = UsTevWorkflowSummary(total_substations=len(substations))

        # Pre-flight browser check before batch execution
        self.check_browser_prerequisite()

        total = len(substations)
        for idx, (substation_item, raw_or_survey_dir) in enumerate(substations, start=1):
            path_obj = Path(raw_or_survey_dir).resolve()
            survey_root = discover_ultratev_survey_dir(path_obj) or path_obj
            output_dir = survey_root / "graphs"

            try:
                paths = self.run_substation(survey_root, output_dir)
                count = len(paths)
                summary.total_graphs += count
                if on_progress:
                    on_progress(idx, total, str(substation_item), count, output_dir)
            except Exception as exc:
                err_msg = f"Failed generating graphs for {substation_item}: {exc}"
                logger.error(err_msg, exc_info=True)
                summary.errors.append(err_msg)

        summary.elapsed_time = time.time() - start_time
        return summary
