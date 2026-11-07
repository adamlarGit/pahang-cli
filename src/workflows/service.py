"""Workflow service for orchestrating Pahang CLI operations."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Callable, TypeVar

from src.run_records import current_run
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
    from pathlib import Path
    from typing import Sequence
    from src.postprocessing.converters import DocumentConverter
    from src.project.environment import ProjectEnvironment
    from src.workflows.full_report_postprocessing import (
        FullReportPostProcessingResult,
        PostProcessingTarget,
        ProgressSink,
    )


_Result = TypeVar("_Result")


def _timed_work(method: Callable[..., _Result]) -> Callable[..., _Result]:
    """Time a service workflow as one Step. Every prompt has been answered by the time it's called."""
    name = f"Workflow: {method.__name__.removeprefix('run_')}"

    @wraps(method)
    def timed(*args: object, **kwargs: object) -> _Result:
        with current_run().step(name):
            return method(*args, **kwargs)

    return timed


def _record_request(environment: ProjectEnvironment, request: object) -> None:
    """Add a request and the project's workbooks to the open Run Record, if there is one."""
    run = current_run()
    run.record_request(request)
    if run.path is not None:
        try:
            workbooks = (environment.get_total_pe_path(), environment.get_data_msms_path())
            run.record_inputs(path for path in workbooks if path.exists())
        except Exception:
            pass


class WorkflowService:
    """Core workflow service executing project operations."""

    @_timed_work
    def run_generate_testsheet_folder(
        self,
        environment: ProjectEnvironment,
        request: GenerateTestsheetFolderRequest,
    ) -> GenerateTestsheetFolderResult:
        _record_request(environment, request)
        if request.progress_sink:
            request.progress_sink(
                f"Generating folder structure for {request.station} / {request.month}..."
            )
        from src.workflows.generate_testsheet_folder import GenerateTestsheetFolderStructureWorkflow

        return GenerateTestsheetFolderStructureWorkflow().execute(environment, request)

    @_timed_work
    def run_populate_total_pe(
        self, environment: ProjectEnvironment, request: PopulateTotalPeRequest
    ) -> PopulateTotalPeResult:
        _record_request(environment, request)
        if request.progress_sink:
            request.progress_sink("Executing Populate TOTAL PE workflow...")
        workflow = PopulateTotalPeWorkflow()
        return workflow.execute(environment, request)

    @_timed_work
    def run_raw_material(
        self, environment: ProjectEnvironment, request: RawMaterialRequest
    ) -> RawMaterialResult:
        _record_request(environment, request)
        if request.progress_sink:
            request.progress_sink(f"Executing Raw Material workflow on {request.output_path}...")
        workflow = RawMaterialWorkflow()
        return workflow.execute(environment, request)

    @_timed_work
    def run_update_qr02_cba(
        self, environment: ProjectEnvironment, request: UpdateQr02CbaRequest
    ) -> UpdateQr02CbaResult:
        _record_request(environment, request)
        if request.progress_sink:
            request.progress_sink("Executing Update QR02 CBA workflow...")
        from src.workflows.update_qr02_cba import UpdateQr02CbaWorkflow
        workflow = UpdateQr02CbaWorkflow()
        return workflow.execute(environment, request)


    @_timed_work
    def run_whatsapp(
        self, environment: ProjectEnvironment, request: WhatsAppReportRequest
    ) -> WhatsAppReportResult:
        _record_request(environment, request)
        if request.progress_sink:
            request.progress_sink("Executing WhatsApp Report generation...")
        from src.workflows.whatsapp import WhatsAppReportWorkflow
        workflow = WhatsAppReportWorkflow()
        return workflow.execute(environment, request)

    @_timed_work
    def run_propagate_wo(
        self, environment: ProjectEnvironment, request: PropagateWoRequest | None = None
    ) -> PropagateWoResult:
        _record_request(environment, request or PropagateWoRequest())
        if request and request.progress_sink:
            request.progress_sink("Executing Propagate Work Orders workflow...")
        from src.workflows.propagate_wo import PropagateWoWorkflow
        workflow = PropagateWoWorkflow()
        return workflow.execute(environment, request)

    @_timed_work
    def run_consolidate_msms(
        self, environment: ProjectEnvironment, request: ConsolidateMsmsRequest | None = None
    ) -> ConsolidateMsmsResult:
        _record_request(environment, request or ConsolidateMsmsRequest())
        if request and request.progress_sink:
            request.progress_sink("Executing Consolidate MSMS workflow...")
        from src.workflows.consolidate_msms import ConsolidateMsmsWorkflow
        workflow = ConsolidateMsmsWorkflow()
        return workflow.execute(environment, request)

    @_timed_work
    def run_enrich_msms(
        self, environment: ProjectEnvironment, request: EnrichMsmsRequest | None = None
    ) -> EnrichMsmsResult:
        _record_request(environment, request or EnrichMsmsRequest())
        if request and request.progress_sink:
            request.progress_sink("Executing Enrich MSMS workflow...")
        from src.workflows.enrich_msms import EnrichMsmsWorkflow
        workflow = EnrichMsmsWorkflow()
        return workflow.execute(environment, request)

    @_timed_work
    def run_ingest_msms_csv(
        self, environment: ProjectEnvironment, request: IngestMsmsCsvRequest | None = None
    ) -> IngestMsmsCsvResult:
        _record_request(environment, request or IngestMsmsCsvRequest())
        req = request or IngestMsmsCsvRequest()
        if req.progress_sink:
            req.progress_sink("Executing Ingest MSMS CSV workflow...")
        from src.workflows.ingest_msms_csv import IngestMsmsCsvWorkflow
        workflow = IngestMsmsCsvWorkflow()
        return workflow.execute(environment, req)

    @_timed_work
    def run_populate_data_msms(
        self, environment: ProjectEnvironment, request: PopulateDataMsmsRequest | None = None
    ) -> PopulateDataMsmsResult:
        _record_request(environment, request or PopulateDataMsmsRequest())
        req = request or PopulateDataMsmsRequest()
        if req.progress_sink:
            req.progress_sink("Executing Populate Data MSMS workflow...")
        from src.workflows.populate_data_msms import PopulateDataMsmsWorkflow
        workflow = PopulateDataMsmsWorkflow()
        return workflow.execute(environment, req)

    @_timed_work
    def run_postprocessing_pipeline(
        self,
        environment: ProjectEnvironment,
        request: PostProcessingRequest | None = None,
    ) -> PostProcessingSummary:
        _record_request(environment, request or PostProcessingRequest())
        from src.workflows.postprocessing_pipeline import PostProcessingPipelineWorkflow

        workflow = PostProcessingPipelineWorkflow()
        return workflow.execute(environment, request)

    @_timed_work
    def run_full_report_postprocessing(
        self,
        environment: ProjectEnvironment,
        target: PostProcessingTarget = None,
        *,
        station: str | Sequence[str] | None = None,
        progress_sink: ProgressSink | None = None,
        fail_fast: bool = False,
        output_dir: Path | str | None = None,
        converter: DocumentConverter | None = None,
    ) -> FullReportPostProcessingResult:
        from src.workflows.full_report_postprocessing import FullReportPostProcessingWorkflow

        workflow = FullReportPostProcessingWorkflow(converter=converter)
        return workflow.process(
            target=target,
            environment=environment,
            station=station,
            progress_sink=progress_sink,
            fail_fast=fail_fast,
            output_dir=output_dir,
        )

