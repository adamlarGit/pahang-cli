"""Workflow service for orchestrating Pahang CLI operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.workflows.models import (
    PopulateTotalPeRequest,
    PopulateTotalPeResult,
    QuickReportRequest,
    QuickReportResult,
    RawMaterialRequest,
    RawMaterialResult,
    UpdateQr02CbaRequest,
    UpdateQr02CbaResult,
    WhatsAppReportRequest,
    WhatsAppReportResult,
)

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment


class WorkflowService:
    """Core workflow service executing project operations."""

    def run_populate_total_pe(
        self, environment: ProjectEnvironment, request: PopulateTotalPeRequest
    ) -> PopulateTotalPeResult:
        if request.progress_sink:
            request.progress_sink("Executing Populate TOTAL PE workflow...")
        return PopulateTotalPeResult(new_rows_added=0)

    def run_raw_material(
        self, environment: ProjectEnvironment, request: RawMaterialRequest
    ) -> RawMaterialResult:
        if request.progress_sink:
            request.progress_sink(f"Executing Raw Material workflow on {request.output_path}...")
        return RawMaterialResult(substations_count=0)

    def run_update_qr02_cba(
        self, environment: ProjectEnvironment, request: UpdateQr02CbaRequest
    ) -> UpdateQr02CbaResult:
        if request.progress_sink:
            request.progress_sink("Executing Update QR02 CBA workflow...")
        return UpdateQr02CbaResult(records_updated=0)

    def run_quick_report(
        self, environment: ProjectEnvironment, request: QuickReportRequest
    ) -> QuickReportResult:
        if request.progress_sink:
            request.progress_sink("Executing Quick Report generation...")
        return QuickReportResult(reports_generated=0)

    def run_whatsapp(
        self, environment: ProjectEnvironment, request: WhatsAppReportRequest
    ) -> WhatsAppReportResult:
        if request.progress_sink:
            request.progress_sink("Executing WhatsApp Report generation...")
        return WhatsAppReportResult(substations_count=0)
