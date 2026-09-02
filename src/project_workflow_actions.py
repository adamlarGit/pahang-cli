"""Project workflow action registry for project-scoped CLI work in Pahang CLI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src import cli_selectors
from src.workflows.models import (
    GenerateTestsheetFolderRequest,
    PopulateDataMsmsRequest,
    PopulateMode,
    PopulateTotalPeRequest,
    PostProcessingMode,
    PostProcessingRequest,
    PostProcessingSummary,
    QuickReportMode,
    QuickReportRequest,
    QuickReportResult,
    RawMaterialRequest,
    UpdateQr02CbaRequest,
    WhatsAppReportRequest,
)
from src.workflows.service import WorkflowService

if TYPE_CHECKING:
    from src.postprocessing.converters import DocumentConverter
    from src.project.environment import ProjectEnvironment


def _cli_progress_sink(message: str, *args: object) -> None:
    """Clean CLI progress console printer helper for workflow execution."""
    print(f"[PROGRESS] {message}")


class ProjectWorkflowAction:
    """One project-scoped action resolved from the active project environment."""

    label: str
    _runner_factory: Callable[[], Callable[[ProjectEnvironment], object]] | None

    def __init__(
        self,
        label: str,
        runner_factory: Callable[[], Callable[[ProjectEnvironment], object]] | None = None,
    ) -> None:
        self.label = label
        self._runner_factory = runner_factory

    def run(self, environment: ProjectEnvironment) -> object:
        """Run the action for the active project environment."""
        import time

        start_t = time.time()
        try:
            return self.execute(environment)
        finally:
            elapsed = time.time() - start_t
            print(f"\n[TIMER] Workflow '{self.label}' completed in {elapsed:.2f} seconds.")

    def execute(self, environment: ProjectEnvironment) -> object:
        """Execute the workflow action (to be overridden by subclasses)."""
        if self._runner_factory is not None:
            runner = self._runner_factory()
            return runner(environment)
        raise NotImplementedError("Subclasses must implement execute(environment)")


class GenerateTestsheetFolderAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for generating TESTSHEET folder hierarchy."""

    def execute(self, environment: ProjectEnvironment) -> object:
        station = cli_selectors.select_or_create_testsheet_station(environment)
        if station is None:
            return None
        month = cli_selectors.select_or_create_testsheet_month(environment, station)
        if month is None:
            return None
        dates = cli_selectors.prompt_target_inspection_dates()
        if dates is None:
            return None
        request = GenerateTestsheetFolderRequest(
            station=station,
            month=month,
            target_dates=dates,
            progress_sink=_cli_progress_sink,
        )
        service = WorkflowService()
        result = service.run_generate_testsheet_folder(environment, request)
        print(
            f"Successfully generated folder structure for {result.station} / {result.month} "
            f"({result.total_dates_processed} date{'s' if result.total_dates_processed != 1 else ''})."
        )
        if result.warnings:
            for w in result.warnings:
                print(f"[WARNING] {w}")
        return result


class PopulateTotalPeAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for populating TOTAL PE from testsheets."""

    def execute(self, environment: ProjectEnvironment) -> object:
        options = [
            cli_selectors.SelectOption("Auto (process new/unprocessed dates only)", "auto"),
            cli_selectors.SelectOption("All (re-process all folders checking existing PEs)", "all"),
            cli_selectors.SelectOption("Select specific folder", "select"),
            cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"),
        ]
        mode_str = cli_selectors.select_one("Populate TOTAL PE - Processing Mode", options)
        if mode_str in ("__cancel__", None):
            print("Processing cancelled.")
            return None

        if mode_str == "select":
            selected_path = cli_selectors.select_pahang_date_folder(environment=environment)
            if selected_path is None:
                print("Processing cancelled.")
                return None
            request = PopulateTotalPeRequest(
                mode=PopulateMode.SPECIFIC_FOLDERS,
                target_folder_names=(selected_path.name, str(selected_path)),
                progress_sink=_cli_progress_sink,
            )
        elif mode_str == "all":
            request = PopulateTotalPeRequest(
                mode=PopulateMode.ALL,
                progress_sink=_cli_progress_sink,
            )
        else:
            request = PopulateTotalPeRequest(
                mode=PopulateMode.AUTO,
                progress_sink=_cli_progress_sink,
            )

        service = WorkflowService()
        result = service.run_populate_total_pe(environment, request)
        print(f"New rows added: {result.new_rows_added}")
        return result


class RawMaterialAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for raw material creation & sorting."""

    def execute(self, environment: ProjectEnvironment) -> object:
        selected_path = cli_selectors.select_pahang_date_folder(environment=environment)
        if selected_path is None:
            selected_path = cli_selectors.prompt_directory_path(
                "Enter target RAW MATERIAL / TESTSHEET directory path",
                default=environment.get_testsheet_dir(),
                must_exist=False,
            )
        if selected_path is None:
            print("Operation cancelled.")
            return None

        request = RawMaterialRequest(
            output_path=selected_path,
            progress_sink=_cli_progress_sink,
        )
        service = WorkflowService()
        result = service.run_raw_material(environment, request)
        print(f"Processed substations count: {result.substations_count}")
        if result.summary:
            print(f"  - IR photos copied: {result.summary.ir_copied_count}")
            print(f"  - DG photos copied: {result.summary.dg_copied_count}")
            print(f"  - US+TEV surveys extracted: {result.summary.us_tev_extracted_count}")
        if result.warnings:
            print(f"Warnings ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"  - {w}")
        return result



class UpdateQr02CbaAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for updating QR02 CBA sheets."""

    def execute(self, environment: ProjectEnvironment) -> object:
        options = [
            cli_selectors.SelectOption("Auto (process new/unprocessed only)", "auto"),
            cli_selectors.SelectOption("All (re-process everything)", "all"),
            cli_selectors.SelectOption("Select specific folder", "select"),
            cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"),
        ]
        mode_str = cli_selectors.select_one("QR02 CBA - Processing Mode", options)
        if mode_str in ("__cancel__", None):
            print("Processing cancelled.")
            return None

        if mode_str == "select":
            selected_path = cli_selectors.select_pahang_date_folder(environment=environment)
            if selected_path is None:
                print("Processing cancelled.")
                return None
            request = UpdateQr02CbaRequest(
                mode=PopulateMode.SPECIFIC_FOLDERS,
                target_package_names=(selected_path.name, str(selected_path)),
                progress_sink=_cli_progress_sink,
            )
        elif mode_str == "all":
            request = UpdateQr02CbaRequest(
                mode=PopulateMode.ALL,
                progress_sink=_cli_progress_sink,
            )
        else:
            request = UpdateQr02CbaRequest(
                mode=PopulateMode.AUTO,
                progress_sink=_cli_progress_sink,
            )

        service = WorkflowService()
        result = service.run_update_qr02_cba(environment, request)
        print(f"Records updated: {result.records_updated}")
        if result.warnings:
            print(f"Warnings ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"  - {w}")
        if result.errors:
            print(f"Errors ({len(result.errors)}):")
            for e in result.errors:
                print(f"  - {e}")
        return result


class QuickReportAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for Quick Report / Visual Report generation."""

    def execute(self, environment: ProjectEnvironment) -> object:
        options = [
            cli_selectors.SelectOption("Manual FL Input", "manual"),
            cli_selectors.SelectOption("Select Testsheet Folder", "folder"),
            cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"),
        ]
        mode_str = cli_selectors.select_one("Quick Report - Selection Mode", options)
        if mode_str in ("__cancel__", None):
            print("Processing cancelled.")
            return None

        request = None
        default_cond_template = environment.get_sub_cond_dir() / "MASTER_SUBSTATION_CONDITION.docx"

        if mode_str == "manual":
            print('Enter comma-separated Functional Locations.')
            input_locs = input("Functional Locations: ").strip()
            fl_numbers = tuple(loc.strip() for loc in input_locs.split(",") if loc.strip())
            if not fl_numbers:
                print("No functional locations provided.")
                return None
            request = QuickReportRequest(
                mode=QuickReportMode.FL,
                target_package_names=fl_numbers,
                substation_condition_template_path=default_cond_template,
                progress_sink=_cli_progress_sink,
            )
        else:
            selected_path = cli_selectors.select_pahang_date_folder(environment=environment)
            if selected_path is None:
                print("Processing cancelled.")
                return None

            request = QuickReportRequest(
                mode=QuickReportMode.FOLDER,
                target_folders=(str(selected_path),),
                substation_condition_template_path=default_cond_template,
                progress_sink=_cli_progress_sink,
            )

        service = WorkflowService()
        result = service.run_quick_report(environment, request)
        _print_quick_report_batch_summary(result)
        return result


def _print_quick_report_batch_summary(result: QuickReportResult) -> None:
    """Display clean formatted CLI summary box for quick report batch runs."""
    total_generated = result.reports_generated
    total_failed = len(result.errors)
    total_warnings = len(result.warnings)
    total_processed = total_generated + total_failed

    print("\n  =======================================================")
    print("    📌 QUICK REPORT BATCH EXECUTION SUMMARY")
    print("  =======================================================")
    print(f"    Total Processed : {total_processed}")
    print(f"    Succeeded       : {total_generated}")
    print(f"    Failed          : {total_failed}")
    print(f"    Warnings        : {total_warnings}")
    print("  =======================================================")

    if result.generated_paths:
        print("\n    📄 GENERATED QUICK REPORTS:")
        for p in result.generated_paths:
            print(f"      ✓ {p.name}")

    if result.warnings:
        print("\n    ⚠️ WARNINGS:")
        for w in result.warnings:
            print(f"      - {w}")

    if result.errors:
        print("\n    ❌ FAILED SUBSTATIONS:")
        for e in result.errors:
            err_msg = Path(e).name if ("/" in str(e) or "\\" in str(e)) else str(e)
            print(f"      - [FAILED] {err_msg}")

    print("  =======================================================\n")



VisualReportAction = QuickReportAction


class PostProcessingPipelineAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for full substation post-processing pipeline."""

    def __init__(
        self,
        label: str,
        runner_factory: Callable[[], Callable[[ProjectEnvironment], object]] | None = None,
        workflow_service: WorkflowService | None = None,
        converter: DocumentConverter | None = None,
    ) -> None:
        super().__init__(label, runner_factory=runner_factory)
        self.workflow_service = workflow_service
        self.converter = converter

    def execute(self, environment: ProjectEnvironment) -> object:
        # 1. Scope Selection
        scope_options = [
            cli_selectors.SelectOption("By Date Folder (Process all substations in a date folder)", "by_date"),
            cli_selectors.SelectOption("By Substation / FL (Select specific substations)", "by_fl"),
            cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"),
        ]
        scope_choice = cli_selectors.select_one("Post-Processing Pipeline - Scope Selection", scope_options)
        if scope_choice in ("__cancel__", None):
            print("Processing cancelled.")
            return None

        target_dates: tuple[str, ...] = ()
        target_fls: tuple[str, ...] = ()
        generate_whatsapp: bool = False

        if scope_choice == "by_date":
            mode = PostProcessingMode.BY_DATE
            selected_date_folder = cli_selectors.select_pahang_date_folder(environment=environment)
            if selected_date_folder is None:
                print("Processing cancelled.")
                return None
            target_dates = (selected_date_folder.name,)
        else:
            mode = PostProcessingMode.BY_FL
            from src.workflows.postprocessing_pipeline import discover_substation_packages

            packages = discover_substation_packages(environment)
            if packages:
                options = [
                    cli_selectors.SelectOption(
                        f"{p.station_name} [{p.fl_erms}] ({p.date_folder})",
                        p.fl_erms if p.fl_erms else p.station_name,
                    )
                    for p in packages
                ]
                selected_fls = cli_selectors.select_multiple("Select substations to process", options)
                if not selected_fls:
                    print("Processing cancelled.")
                    return None
                target_fls = tuple(selected_fls)
            else:
                print("Enter comma-separated Functional Locations or Station Names:")
                raw = input("Substations: ").strip()
                if not raw:
                    print("Processing cancelled.")
                    return None
                target_fls = tuple(p.strip() for p in raw.split(",") if p.strip())

        # 2. Digital Signatures Selection
        apply_signatures_prompt = cli_selectors.confirm("Apply digital signatures?", default=True)
        if apply_signatures_prompt is None:
            print("Processing cancelled.")
            return None

        vendor_sign_path: Path | None = None
        tnb_sign_path: Path | None = None

        if apply_signatures_prompt is True:
            from src.workflows.replace_signatures import _select_signature_path

            sign_dir = environment.get_sign_dir()
            vendor_path, vendor_key = _select_signature_path(
                "Select vendor signature person (Tested by / {{signvendor}}):",
                sign_dir,
            )
            if vendor_key in ("__cancel__", None):
                print("Processing cancelled.")
                return None

            tnb_default = vendor_key if vendor_key not in ("__none__", "__custom__") else None
            tnb_path, tnb_key = _select_signature_path(
                "Select TNB signature person (TNB Supervisor / {{signtnb}}):",
                sign_dir,
                default_folder=tnb_default,
            )
            if tnb_key in ("__cancel__", None):
                print("Processing cancelled.")
                return None

            vendor_sign_path = vendor_path
            tnb_sign_path = tnb_path

        # 3. WhatsApp Report Prompt (BY_DATE mode only)
        if mode == PostProcessingMode.BY_DATE:
            generate_whatsapp_prompt = cli_selectors.confirm("Generate WhatsApp daily report?", default=True)
            if generate_whatsapp_prompt is None:
                print("Processing cancelled.")
                return None
            generate_whatsapp = generate_whatsapp_prompt
        else:
            generate_whatsapp = False

        # 4. Dispatch Request
        request = PostProcessingRequest(
            mode=mode,
            target_dates=target_dates,
            target_fls=target_fls,
            apply_signatures=apply_signatures_prompt,
            vendor_signature_path=vendor_sign_path,
            tnb_signature_path=tnb_sign_path,
            generate_whatsapp=generate_whatsapp,
            converter=self.converter,
            progress_sink=_cli_progress_sink,
        )

        service = self.workflow_service or WorkflowService()
        summary = service.run_postprocessing_pipeline(environment, request)
        _print_postprocessing_summary(summary)
        return summary


def _print_postprocessing_summary(summary: PostProcessingSummary | None) -> None:
    """Display clean formatted CLI summary box for post-processing pipeline execution."""
    if summary is None:
        return

    total_queued = summary.total_target_count
    total_succeeded = len(summary.processed_packages)
    total_failed = len(summary.failed_packages)
    total_warnings = len(summary.warnings)
    duration_str = f"{summary.duration_seconds:.2f}s"

    print("\n  =======================================================")
    print("    📌 1-CLICK POST-PROCESSING PIPELINE SUMMARY")
    print("  =======================================================")
    print(f"    Total Queued    : {total_queued}")
    print(f"    Succeeded       : {total_succeeded}")
    print(f"    Failed          : {total_failed}")
    print(f"    Warnings        : {total_warnings}")
    print(f"    Duration        : {duration_str}")
    print("  =======================================================")

    if summary.final_deliverables:
        print("\n    📄 FINAL DELIVERABLES:")
        for path in summary.final_deliverables:
            print(f"      ✓ {path.name}")

    if summary.warnings:
        print("\n    ⚠️ WARNINGS:")
        for warning in summary.warnings:
            print(f"      - {warning}")

    if summary.failed_packages:
        print("\n    ❌ FAILED SUBSTATIONS:")
        for failure in summary.failed_packages:
            print(f"      - [FAILED] {failure.package.station_name}: {failure.error}")

    print("  =======================================================\n")


def _select_whatsapp_report_batch(root_dir: Path) -> Path | None:
    from pathlib import Path
    from src import cli_selectors
    from src.workflows.whatsapp import QUALIFYING_DOCX_PATTERN
    
    root_path = Path(root_dir)
    
    def _list_qualifying(batch_dir):
        bp = Path(batch_dir)
        if not bp.exists() or not bp.is_dir():
            return []
        q = []
        for child in bp.iterdir():
            if child.is_file() and child.suffix.lower() == ".docx":
                m = QUALIFYING_DOCX_PATTERN.match(child.name)
                if m:
                    q.append((int(m.group(1)), child))
        q.sort(key=lambda x: x[0])
        return [path for _, path in q]

    def _is_selectable(batch_dir):
        return bool(_list_qualifying(batch_dir))

    def _get_title(batch_dir):
        bp = Path(batch_dir)
        c = len(_list_qualifying(bp))
        if c:
            return f"{bp.name} ({c} DOCXs)"
        return bp.name

    def _get_lines(batch_dir):
        bp = Path(batch_dir)
        q = _list_qualifying(bp)
        if not q:
            return [f"No qualifying DOCXs in batch: {bp.name}"]
        nums = [int(QUALIFYING_DOCX_PATTERN.match(p.name).group(1)) for p in q]
        try:
            rel = " / ".join(bp.relative_to(root_path).parts)
        except ValueError:
            rel = bp.name
        return [
            "Generate WhatsApp report for this batch?",
            f"Batch: {rel}",
            f"Qualifying DOCXs: {len(q)}",
            f"First PE: {nums[0]}",
            f"Last PE: {nums[-1]}",
        ]

    return cli_selectors.select_directory_tree(
        root_path,
        title="Select Quick Report Batch",
        is_selectable=_is_selectable,
        get_child_title=lambda path, _: _get_title(path),
        get_confirmation_lines=_get_lines,
    )


class WhatsAppReportAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for generating WhatsApp reports."""

    def execute(self, environment: ProjectEnvironment) -> object:
        resources = environment.get_whatsapp_report_resources()
        report_dir = _select_whatsapp_report_batch(resources.quick_report_dir)
        if report_dir is None:
            print("Operation cancelled.")
            return None

        request = WhatsAppReportRequest(
            report_dir=report_dir,
            progress_sink=_cli_progress_sink,
        )
        service = WorkflowService()
        result = service.run_whatsapp(environment, request)
        print(f"Substations processed: {result.substations_count}")
        if getattr(result, "output_path", None):
            print(f"WhatsApp report generated: {result.output_path}")
        return result


class PropagateWoAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for propagating WO numbers to TOTAL PE."""

    def execute(self, environment: ProjectEnvironment) -> object:
        service = WorkflowService()
        result = service.run_propagate_wo(environment)
        print(
            f"Work Orders propagated: {result.updated_count} updated, "
            f"{result.matched_count} matched, {result.already_populated_count} already populated."
        )
        return result


UpdateDataMsmsAction = PropagateWoAction


class ConsolidateMsmsAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for consolidating MSMS .xls files into DATA MSMS."""

    def execute(self, environment: ProjectEnvironment) -> object:
        service = WorkflowService()
        result = service.run_consolidate_msms(environment)
        print(
            f"Files processed: {result.files_processed}, "
            f"Rows appended: {result.rows_appended}, "
            f"Duplicates skipped: {result.duplicates_skipped}"
        )
        return result


class EnrichMsmsAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for enriching DATA MSMS with TOTAL PE metadata."""

    def execute(self, environment: ProjectEnvironment) -> object:
        service = WorkflowService()
        result = service.run_enrich_msms(environment)
        print(
            f"Cells updated: {result.updated_cells_count}, "
            f"Matched: {result.matched_count}, "
            f"Unmatched: {result.unmatched_count}"
        )
        return result


class IngestMsmsCsvAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for ingesting MSMS CSVs from RAW DATA into TO BE FILLED."""

    def execute(self, environment: ProjectEnvironment) -> object:
        service = WorkflowService()
        result = service.run_ingest_msms_csv(environment)
        print(
            f"Files ingested: {result.files_ingested}, "
            f"Duplicates skipped: {result.duplicates_skipped}"
        )
        return result


class PopulateDataMsmsAction(ProjectWorkflowAction):
    """CLI Presentation Adapter for populating MSMS CSVs from testsheets."""

    def execute(self, environment: ProjectEnvironment) -> object:
        options = [
            cli_selectors.SelectOption("Auto (process new/unprocessed only)", "auto"),
            cli_selectors.SelectOption("All (re-process all CSV files)", "all"),
            cli_selectors.SelectOption("Select specific folder", "select"),
            cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"),
        ]
        mode_str = cli_selectors.select_one("Populate Data MSMS - Processing Mode", options)
        if mode_str in ("__cancel__", None):
            print("Processing cancelled.")
            return None

        overwrite = False
        target_folder_names: tuple[str, ...] = ()
        if mode_str == "select":
            selected_path = cli_selectors.select_pahang_date_folder(environment=environment)
            if selected_path is None:
                print("Processing cancelled.")
                return None
            target_folder_names = (selected_path.name, str(selected_path))
            pop_mode = PopulateMode.SPECIFIC_FOLDERS
            overwrite_prompt = cli_selectors.confirm("Overwrite already filled readings in selected folder?", default=False)
            if overwrite_prompt is True:
                overwrite = True
        elif mode_str == "all":
            pop_mode = PopulateMode.ALL
            overwrite_prompt = cli_selectors.confirm("Overwrite already filled readings in all files?", default=False)
            if overwrite_prompt is True:
                overwrite = True
        else:
            pop_mode = PopulateMode.AUTO

        request = PopulateDataMsmsRequest(
            mode=pop_mode,
            target_folder_names=target_folder_names,
            overwrite=overwrite,
            progress_sink=_cli_progress_sink,
        )

        service = WorkflowService()
        result = service.run_populate_data_msms(environment, request)
        print(
            f"CSV files processed: {result.csv_files_processed}, "
            f"Rows populated: {result.rows_populated}, "
            f"Rows skipped: {result.rows_skipped_already_filled}"
        )
        if result.warnings:
            print(f"Warnings ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"  - {w}")
        if result.errors:
            print(f"Errors ({len(result.errors)}):")
            for e in result.errors:
                print(f"  - {e}")
        return result



PROJECT_WORKFLOW_ACTIONS: tuple[ProjectWorkflowAction, ...] = (
    GenerateTestsheetFolderAction("Generate TESTSHEET Folder Structure"),
    PopulateTotalPeAction("Populate TOTAL PE (from testsheets)"),
    RawMaterialAction("Automate Raw Material Creation & Sorting (from Testsheets)"),
    UpdateQr02CbaAction("Update QR02 CBA (from testsheets)"),
    QuickReportAction("Generate Quick Report (Visual Report)"),
    PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)"),
    WhatsAppReportAction("Generate WhatsApp Report"),
    ConsolidateMsmsAction("Consolidate MSMS (PYTHON/MSMS/*.xls -> DATA MSMS)"),
    EnrichMsmsAction("Enrich MSMS (TOTAL PE -> DATA MSMS metadata)"),
    PropagateWoAction("Propagate Work Orders (DATA MSMS -> TOTAL PE)"),
    IngestMsmsCsvAction("Ingest MSMS CSVs (RAW DATA -> TO BE FILLED)"),
    PopulateDataMsmsAction("Populate Data MSMS (Testsheets -> TO BE FILLED CSVs)"),
)



def get_project_workflow_actions() -> tuple[ProjectWorkflowAction, ...]:
    """Return the immutable project workflow action registry."""
    return PROJECT_WORKFLOW_ACTIONS
