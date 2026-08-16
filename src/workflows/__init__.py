"""Workflows package for Pahang CLI."""

from __future__ import annotations

from src.workflows.consolidate_msms import (
    ConsolidateMsmsAuditor,
    ConsolidateMsmsExtractor,
    ConsolidateMsmsFilter,
    ConsolidateMsmsLoader,
    ConsolidateMsmsPlan,
    ConsolidateMsmsPreflightGuard,
    ConsolidateMsmsRow,
    ConsolidateMsmsWorkflow,
)
from src.workflows.enrich_msms import (
    EnrichCellUpdate,
    EnrichMsmsAuditor,
    EnrichMsmsExtractor,
    EnrichMsmsFilter,
    EnrichMsmsLoader,
    EnrichMsmsPlan,
    EnrichMsmsPreflightGuard,
    EnrichMsmsWorkflow,
    TotalPeLookups,
)
from src.workflows.generate_testsheet_folder import (
    GenerateTestsheetFolderAuditor,
    GenerateTestsheetFolderExtractionData,
    GenerateTestsheetFolderExtractor,
    GenerateTestsheetFolderFilter,
    GenerateTestsheetFolderLoader,
    GenerateTestsheetFolderPreflightGuard,
    GenerateTestsheetFolderStructureWorkflow,
    GenerateTestsheetFolderTransformer,
)
from src.workflows.history import ProcessingHistoryStore, format_package_history_key
from src.workflows.populate_total_pe import PopulateTotalPeWorkflow
from src.workflows.propagate_wo import (
    PropagateWoAuditor,
    PropagateWoExtractor,
    PropagateWoFilter,
    PropagateWoLoader,
    PropagateWoPlan,
    PropagateWoPreflightGuard,
    PropagateWoWorkflow,
)
from src.workflows.quick_report import QuickReportWorkflow
from src.workflows.raw_material import AutomatedRawMaterialSummary, RawMaterialWorkflow
from src.workflows.service import WorkflowService
from src.workflows.update_qr02_cba import UpdateQr02CbaWorkflow
from src.workflows.whatsapp import WhatsAppReportWorkflow

__all__ = [
    "AutomatedRawMaterialSummary",
    "ConsolidateMsmsAuditor",
    "ConsolidateMsmsExtractor",
    "ConsolidateMsmsFilter",
    "ConsolidateMsmsLoader",
    "ConsolidateMsmsPlan",
    "ConsolidateMsmsPreflightGuard",
    "ConsolidateMsmsRow",
    "ConsolidateMsmsWorkflow",
    "EnrichCellUpdate",
    "EnrichMsmsAuditor",
    "EnrichMsmsExtractor",
    "EnrichMsmsFilter",
    "EnrichMsmsLoader",
    "EnrichMsmsPlan",
    "EnrichMsmsPreflightGuard",
    "EnrichMsmsWorkflow",
    "GenerateTestsheetFolderAuditor",
    "GenerateTestsheetFolderExtractionData",
    "GenerateTestsheetFolderExtractor",
    "GenerateTestsheetFolderFilter",
    "GenerateTestsheetFolderLoader",
    "GenerateTestsheetFolderPreflightGuard",
    "GenerateTestsheetFolderStructureWorkflow",
    "GenerateTestsheetFolderTransformer",
    "PopulateTotalPeWorkflow",
    "ProcessingHistoryStore",
    "PropagateWoAuditor",
    "PropagateWoExtractor",
    "PropagateWoFilter",
    "PropagateWoLoader",
    "PropagateWoPlan",
    "PropagateWoPreflightGuard",
    "PropagateWoWorkflow",
    "QuickReportWorkflow",
    "RawMaterialWorkflow",
    "TotalPeLookups",
    "UpdateQr02CbaWorkflow",
    "WorkflowService",
    "format_package_history_key",
    "WhatsAppReportWorkflow",
]

