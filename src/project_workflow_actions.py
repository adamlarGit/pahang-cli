"""Project workflow action registry for project-scoped CLI work in Pahang CLI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from src import cli_selectors
from src.workflows.models import (
    PopulateMode,
    PopulateTotalPeRequest,
    QuickReportMode,
    QuickReportRequest,
    RawMaterialRequest,
    UpdateQr02CbaRequest,
    WhatsAppReportRequest,
)
from src.workflows.service import WorkflowService

if TYPE_CHECKING:
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
                target_folder_names=(selected_path.name,),
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

    def execute(self, environment: ProjectEnvironment) -> object:
        service = WorkflowService()
        return service.run_postprocessing_pipeline(environment)


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


class UpdateDataMsmsAction(ProjectWorkflowAction):
    def execute(self, environment: ProjectEnvironment) -> object:
        service = WorkflowService()
        return service.run_update_data_msms(environment)

PROJECT_WORKFLOW_ACTIONS: tuple[ProjectWorkflowAction, ...] = (
    PopulateTotalPeAction("Populate TOTAL PE (from testsheets)"),
    RawMaterialAction("Automate Raw Material Creation & Sorting (from Testsheets)"),
    UpdateQr02CbaAction("Update QR02 CBA (from testsheets)"),
    QuickReportAction("Generate Quick Report (Visual Report)"),
    PostProcessingPipelineAction("Run Full Substation Post-Processing Pipeline (1-Click)"),
    WhatsAppReportAction("Generate WhatsApp Report"),
    UpdateDataMsmsAction("Update DATA_MSMS and TOTAL PE WO"),
)


def get_project_workflow_actions() -> tuple[ProjectWorkflowAction, ...]:
    """Return the immutable project workflow action registry."""
    return PROJECT_WORKFLOW_ACTIONS
