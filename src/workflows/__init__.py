"""Workflows package for Pahang CLI."""

from __future__ import annotations

from src.workflows.history import ProcessingHistoryStore, format_package_history_key
from src.workflows.populate_total_pe import PopulateTotalPeWorkflow
from src.workflows.raw_material import AutomatedRawMaterialSummary, RawMaterialWorkflow
from src.workflows.service import WorkflowService
from src.workflows.update_qr02_cba import UpdateQr02CbaWorkflow, run_update_qr02_cba
from src.workflows.whatsapp import (
    run_generate_whatsapp_report,
    select_quick_report_batch,
)

__all__ = [
    "AutomatedRawMaterialSummary",
    "PopulateTotalPeWorkflow",
    "ProcessingHistoryStore",
    "RawMaterialWorkflow",
    "UpdateQr02CbaWorkflow",
    "WorkflowService",
    "format_package_history_key",
    "run_generate_whatsapp_report",
    "run_update_qr02_cba",
    "select_quick_report_batch",
]
