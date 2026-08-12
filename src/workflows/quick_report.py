"""Quick Report workflow orchestrator adhering to 6-stage ETL methodology."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.quick_report.composer import QuickReportComposer
from src.quick_report.extractor import QuickReportExtractor
from src.quick_report.filter import QuickReportFilter
from src.quick_report.transformer import QuickReportTransformer
from src.workflows.models import QuickReportResult

try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None
    win32com = None

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment
    from src.workflows.models import QuickReportRequest


class QuickReportWorkflow:
    """Orchestrator for Pahang 7-part quick report document generation.

    Resilience Policy: best-effort
    All-or-nothing per station, but accumulates per-station errors without aborting batch execution.
    """

    def __init__(
        self,
        extractor: QuickReportExtractor | None = None,
        filter_stage: QuickReportFilter | None = None,
        transformer: QuickReportTransformer | None = None,
        composer: QuickReportComposer | None = None,
    ) -> None:
        self.extractor = extractor or QuickReportExtractor()
        self.filter_stage = filter_stage or QuickReportFilter()
        self.transformer = transformer or QuickReportTransformer()
        self.composer = composer or QuickReportComposer()

    def execute(
        self, environment: ProjectEnvironment, request: QuickReportRequest
    ) -> QuickReportResult:
        """Execute Quick Report generation pipeline across target packages."""
        self._validate_preconditions(environment, request)

        if request.progress_sink:
            request.progress_sink("Discovering target packages for Quick Report...")

        packages = self.extractor.extract(environment, request)
        filtered_packages = self.filter_stage.filter(packages, request)

        if request.progress_sink:
            request.progress_sink(
                f"Found {len(filtered_packages)} packages to process."
            )

        generated_paths: list[Path] = []
        errors: list[str] = []

        word_app = None
        if win32com and getattr(win32com, "client", None):
            try:
                if pythoncom:
                    pythoncom.CoInitialize()
                word_app = win32com.client.Dispatch("Word.Application")
                word_app.Visible = False
                word_app.DisplayAlerts = 0
            except Exception as e:
                logging.warning(f"Could not pre-initialize Word COM: {e}")

        try:
            for i, pkg in enumerate(filtered_packages, start=1):
                if request.progress_sink:
                    request.progress_sink(
                        f"[{i}/{len(filtered_packages)}] Generating quick report for {pkg.station}..."
                    )

                try:
                    cbm_defects, vi_defects = self.extractor.extract_defects(
                        pkg, environment
                    )

                    plan = self.transformer.transform(
                        pkg=pkg,
                        cbm_defects=cbm_defects,
                        vi_defects=vi_defects,
                        environment=environment,
                        cond_template_path=request.substation_condition_template_path,
                    )
                    out_path = self.composer.load(plan, word_app=word_app)
                    if out_path:
                        generated_paths.append(out_path)
                except Exception as e:
                    errors.append(f"Failed to process {pkg.station}: {e}")
                    logging.exception(f"Failed to process {pkg.station}")
        finally:
            if word_app is not None:
                try:
                    word_app.Quit()
                except Exception:
                    pass
            if word_app is not None and pythoncom:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        return self._audit_and_build_result(
            generated_paths, [], errors
        )

    def _validate_preconditions(
        self, environment: ProjectEnvironment, request: QuickReportRequest
    ) -> None:
        """Validate input request parameters and environment template preconditions."""
        if request is None:
            raise ValueError("QuickReportRequest cannot be None.")
        if environment is None:
            raise ValueError("ProjectEnvironment cannot be None.")

        # Ensure always-required docx templates exist
        templates_to_check: list[tuple[str, Path | None]] = [
            ("VI front page", environment.get_vi_front_page_template()),
            ("Sticker page", environment.get_template("sticker_page")),
        ]

        if request.substation_condition_template_path is not None:
            templates_to_check.append(
                (
                    "Substation condition",
                    request.substation_condition_template_path,
                )
            )

        for name, template_path in templates_to_check:
            if not template_path or not template_path.exists():
                raise FileNotFoundError(
                    f"Required {name} template missing at: {template_path}"
                )

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
            generated_paths=verified_paths,
            warnings=warnings,
            errors=errors,
        )
