"""Utility action registry for standalone CLI work in Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class UtilityAction:
    """One standalone action that does not consume the active project."""

    label: str
    _runner_factory: Callable[[], Callable[[], object]]

    def run(self) -> object:
        """Run the standalone utility action."""
        import time

        start_t = time.time()
        try:
            runner = self._runner_factory()
            return runner()
        finally:
            elapsed = time.time() - start_t
            print(f"\n[TIMER] Utility Action '{self.label}' completed in {elapsed:.2f} seconds.")


def _load_raw_material_runner() -> Callable[[], object]:
    """Lazy loader for Raw Material Creation & Sorting utility action runner."""
    def runner() -> object:
        from src import cli_selectors
        from src.project.environment import get_or_create_utility_environment
        from src.workflows.models import RawMaterialRequest
        from src.workflows.service import WorkflowService

        print("\n[UTILITY] Standalone Raw Material Creation & Sorting...")
        env = get_or_create_utility_environment()
        
        target_dir = cli_selectors.select_pahang_date_folder(environment=env)
        if target_dir is None:
            default_p = env.get_testsheet_dir() if env else None
            target_dir = cli_selectors.prompt_directory_path(
                "Enter target RAW MATERIAL / TESTSHEET directory path",
                default=default_p,
                must_exist=False,
            )

        if target_dir is None:
            print("Operation cancelled.")
            return None

        request = RawMaterialRequest(
            output_path=target_dir,
            progress_sink=lambda msg: print(f"[PROGRESS] {msg}"),
        )
        service = WorkflowService()
        result = service.run_raw_material(env, request)
        print(f"Processed substations count: {result.substations_count}")
        if result.warnings:
            print(f"Warnings ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"  - {w}")
        return result

    return runner


def _load_rename_files_runner() -> Callable[[], object]:
    from src.workflows.rename_files import run_rename_files
    return run_rename_files


def _load_pdf_extract_runner() -> Callable[[], object]:
    from src.workflows.pdf_extract import run_pdf_extract
    return run_pdf_extract


def _load_combine_pdfs_runner() -> Callable[[], object]:
    from src.workflows.combine_pdfs import run_combine_pdfs
    return run_combine_pdfs


def _load_docx_to_pdf_runner() -> Callable[[], object]:
    from src.workflows.docx_to_pdf import run_docx_to_pdf
    return run_docx_to_pdf


def _load_testsheet_to_pdf_runner() -> Callable[[], object]:
    from src.workflows.testsheet_to_pdf import run_testsheet_to_pdf
    return run_testsheet_to_pdf


def _load_rename_flir_runner() -> Callable[[], object]:
    from src.workflows.rename_flir import run_rename_flir
    return run_rename_flir


def _load_diagonal_runner() -> Callable[[], object]:
    from src.workflows.diagonal_borders import run_diagonal
    return run_diagonal


def _load_replace_images_runner() -> Callable[[], object]:
    def _run() -> object:
        from src.project.environment import get_or_create_utility_environment
        from src.workflows.replace_signatures import run_replace_images

        env = get_or_create_utility_environment()
        return run_replace_images(env)

    return _run



def _load_whatsapp_runner() -> Callable[[], object]:
    def _run() -> None:
        from src.project.environment import get_or_create_utility_environment
        from src.workflows.service import WorkflowService
        from src.workflows.models import WhatsAppReportRequest
        from src.project_workflow_actions import _select_whatsapp_report_batch

        print("\n[Generate WhatsApp report]")
        env = get_or_create_utility_environment()
        if not env:
            print("No project environment available.")
            return None
            
        try:
            resources = env.get_whatsapp_report_resources()
            report_dir = _select_whatsapp_report_batch(resources.quick_report_dir)
            if report_dir is None:
                print("Operation cancelled.")
                return None
                
            request = WhatsAppReportRequest(report_dir=report_dir)
            service = WorkflowService()
            return service.run_whatsapp(env, request)
        except Exception as e:
            print(f"Failed to generate WhatsApp report: {e}")

    return _run


def _load_msms_runner() -> Callable[[], object]:
    def _run() -> None:
        from src.project.environment import get_or_create_utility_environment
        from src.workflows.service import WorkflowService

        print("\n[Propagate Work Orders to TOTAL PE]")
        env = get_or_create_utility_environment()
        try:
            service = WorkflowService()
            return service.run_propagate_wo(env)
        except Exception as e:
            print(f"Failed to run WO propagation: {e}")
            import traceback
            traceback.print_exc()

    return _run


def _load_remove_desktop_ini_runner() -> Callable[[], object]:
    def _run() -> object:
        from src.project.environment import get_or_create_utility_environment
        from src.remove_desktop_ini_workflow import run_remove_desktop_ini

        env = get_or_create_utility_environment()
        return run_remove_desktop_ini(env)

    return _run


def _load_combine_pdfs_with_separator_runner() -> Callable[[], object]:
    from src.workflows.combine_pdfs_with_separator import run_combine_pdfs_with_separator
    return run_combine_pdfs_with_separator


UTILITY_ACTIONS: tuple[UtilityAction, ...] = (
    UtilityAction("Create raw material folders", _load_raw_material_runner),
    UtilityAction("Rename files (match names from input dir)", _load_rename_files_runner),
    UtilityAction("Extract PE pages from PDF (black-page detection)", _load_pdf_extract_runner),
    UtilityAction("Combine PDFs from primary and secondary folders", _load_combine_pdfs_runner),
    UtilityAction("Combine PDFs with separator sheet", _load_combine_pdfs_with_separator_runner),
    UtilityAction("Convert DOCX to PDF (batch)", _load_docx_to_pdf_runner),
    UtilityAction("Convert Testsheet to PDF (batch)", _load_testsheet_to_pdf_runner),
    UtilityAction("Rename FLIR raw files numbering", _load_rename_flir_runner),
    UtilityAction("Apply diagonal borders to blank cells", _load_diagonal_runner),
    UtilityAction("Replace signature images in testsheets", _load_replace_images_runner),
    UtilityAction("Generate WhatsApp report (from Quick Reports)", _load_whatsapp_runner),
    UtilityAction("Propagate Work Orders (DATA MSMS -> TOTAL PE)", _load_msms_runner),
    UtilityAction("Remove desktop.ini files (recursive)", _load_remove_desktop_ini_runner),
)



def get_utility_actions() -> tuple[UtilityAction, ...]:
    """Return the immutable utility action registry."""
    return UTILITY_ACTIONS
