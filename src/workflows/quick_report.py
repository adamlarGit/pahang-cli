"""Quick Report workflow orchestrator adhering to 6-stage ETL methodology."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.workflows.models import QuickReportRequest, QuickReportResult

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment


class QuickReportWorkflow:
    """
    Orchestrator for Pahang 7-part quick report document generation.

    Resilience Policy: best-effort
    All-or-nothing per station, but accumulates per-station errors without aborting batch execution.
    """

    def execute(
        self, environment: ProjectEnvironment, request: QuickReportRequest
    ) -> QuickReportResult:
        """Execute Quick Report generation pipeline across target packages."""
        from src.quick_report.composer import QuickReportComposer
        composer = QuickReportComposer()
        return composer.compose(environment, request)
