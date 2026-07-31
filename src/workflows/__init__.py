"""Workflows package for Pahang CLI."""

from __future__ import annotations

from src.workflows.history import ProcessingHistoryStore, format_package_history_key
from src.workflows.populate_total_pe import PopulateTotalPeWorkflow
from src.workflows.quick_report import QuickReportWorkflow
from src.workflows.raw_material import AutomatedRawMaterialSummary, RawMaterialWorkflow
from src.workflows.service import WorkflowService
from src.workflows.update_qr02_cba import UpdateQr02CbaWorkflow
from src.workflows.whatsapp import WhatsAppReportWorkflow

__all__ = [
    "AutomatedRawMaterialSummary",
    "PopulateTotalPeWorkflow",
    "ProcessingHistoryStore",
    "QuickReportWorkflow",
    "RawMaterialWorkflow",
    "UpdateQr02CbaWorkflow",
    "WorkflowService",
    "format_package_history_key",
    "WhatsAppReportWorkflow",
]
