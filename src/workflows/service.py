"""Workflow service for orchestrating Pahang CLI operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.workflows.models import (
    ConsolidateMsmsRequest,
    ConsolidateMsmsResult,
    EnrichMsmsRequest,
    EnrichMsmsResult,
    GenerateTestsheetFolderRequest,
    GenerateTestsheetFolderResult,
    IngestMsmsCsvRequest,
    IngestMsmsCsvResult,
    PopulateDataMsmsRequest,
    PopulateDataMsmsResult,
    PopulateTotalPeRequest,
    PopulateTotalPeResult,
    PostProcessingRequest,
    PostProcessingSummary,
    PropagateWoRequest,

    PropagateWoResult,
    QuickReportRequest,
    QuickReportResult,
    RawMaterialRequest,
    RawMaterialResult,
    UpdateQr02CbaRequest,
    UpdateQr02CbaResult,
    WhatsAppReportRequest,
    WhatsAppReportResult,
)
from src.workflows.populate_total_pe import PopulateTotalPeWorkflow
from src.workflows.raw_material import RawMaterialWorkflow

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment


class WorkflowService:
    """Core workflow service executing project operations."""

    def run_generate_testsheet_folder(
        self,
        environment: ProjectEnvironment,
        request: GenerateTestsheetFolderRequest,
    ) -> GenerateTestsheetFolderResult:
        if request.progress_sink:
            request.progress_sink(
                f"Generating folder structure for {request.station} / {request.month}..."
            )
        from src.workflows.generate_testsheet_folder import GenerateTestsheetFolderStructureWorkflow

        return GenerateTestsheetFolderStructureWorkflow().execute(environment, request)

    def run_populate_total_pe(
        self, environment: ProjectEnvironment, request: PopulateTotalPeRequest
    ) -> PopulateTotalPeResult:
        if request.progress_sink:
            request.progress_sink("Executing Populate TOTAL PE workflow...")
        workflow = PopulateTotalPeWorkflow()
        return workflow.execute(environment, request)

    def run_raw_material(
        self, environment: ProjectEnvironment, request: RawMaterialRequest
    ) -> RawMaterialResult:
        if request.progress_sink:
            request.progress_sink(f"Executing Raw Material workflow on {request.output_path}...")
        workflow = RawMaterialWorkflow()
        return workflow.execute(environment, request)

    def run_update_qr02_cba(
        self, environment: ProjectEnvironment, request: UpdateQr02CbaRequest
    ) -> UpdateQr02CbaResult:
        if request.progress_sink:
            request.progress_sink("Executing Update QR02 CBA workflow...")
        from src.workflows.update_qr02_cba import UpdateQr02CbaWorkflow
        workflow = UpdateQr02CbaWorkflow()
        return workflow.execute(environment, request)

    def run_quick_report(
        self, environment: ProjectEnvironment, request: QuickReportRequest
    ) -> QuickReportResult:
        if request.progress_sink:
            request.progress_sink("Executing Quick Report generation...")
        from src.workflows.quick_report import QuickReportWorkflow
        workflow = QuickReportWorkflow()
        return workflow.execute(environment, request)


    def run_whatsapp(
        self, environment: ProjectEnvironment, request: WhatsAppReportRequest
    ) -> WhatsAppReportResult:
        if request.progress_sink:
            request.progress_sink("Executing WhatsApp Report generation...")
        from src.workflows.whatsapp import WhatsAppReportWorkflow
        workflow = WhatsAppReportWorkflow()
        return workflow.execute(environment, request)

    def run_propagate_wo(
        self, environment: ProjectEnvironment, request: PropagateWoRequest | None = None
    ) -> PropagateWoResult:
        if request and request.progress_sink:
            request.progress_sink("Executing Propagate Work Orders workflow...")
        from src.workflows.propagate_wo import PropagateWoWorkflow
        workflow = PropagateWoWorkflow()
        return workflow.execute(environment, request)

    def run_consolidate_msms(
        self, environment: ProjectEnvironment, request: ConsolidateMsmsRequest | None = None
    ) -> ConsolidateMsmsResult:
        if request and request.progress_sink:
            request.progress_sink("Executing Consolidate MSMS workflow...")
        from src.workflows.consolidate_msms import ConsolidateMsmsWorkflow
        workflow = ConsolidateMsmsWorkflow()
        return workflow.execute(environment, request)

    def run_enrich_msms(
        self, environment: ProjectEnvironment, request: EnrichMsmsRequest | None = None
    ) -> EnrichMsmsResult:
        if request and request.progress_sink:
            request.progress_sink("Executing Enrich MSMS workflow...")
        from src.workflows.enrich_msms import EnrichMsmsWorkflow
        workflow = EnrichMsmsWorkflow()
        return workflow.execute(environment, request)

    def run_ingest_msms_csv(
        self, environment: ProjectEnvironment, request: IngestMsmsCsvRequest | None = None
    ) -> IngestMsmsCsvResult:
        req = request or IngestMsmsCsvRequest()
        if req.progress_sink:
            req.progress_sink("Executing Ingest MSMS CSV workflow...")
        from src.workflows.ingest_msms_csv import IngestMsmsCsvWorkflow
        workflow = IngestMsmsCsvWorkflow()
        return workflow.execute(environment, req)

    def run_populate_data_msms(
        self, environment: ProjectEnvironment, request: PopulateDataMsmsRequest | None = None
    ) -> PopulateDataMsmsResult:
        req = request or PopulateDataMsmsRequest()
        if req.progress_sink:
            req.progress_sink("Executing Populate Data MSMS workflow...")
        from src.workflows.populate_data_msms import PopulateDataMsmsWorkflow
        workflow = PopulateDataMsmsWorkflow()
        return workflow.execute(environment, req)

    def run_postprocessing_pipeline(
        self,
        environment: ProjectEnvironment,
        request: PostProcessingRequest | None = None,
    ) -> PostProcessingSummary:
        from src.workflows.postprocessing_pipeline import PostProcessingPipelineWorkflow

        workflow = PostProcessingPipelineWorkflow()
        return workflow.execute(environment, request)

