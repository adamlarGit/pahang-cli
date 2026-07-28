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


def _make_stub_runner(action_name: str) -> Callable[[], object]:
    def runner() -> object:
        print(f"\n[UTILITY STUB] Running {action_name}...")
        return True

    return runner


def _load_raw_material_runner() -> Callable[[], object]:
    """Lazy loader for Raw Material Creation & Sorting utility action runner."""
    def runner() -> object:
        from src import cli_selectors
        from src.project.environment import ProjectEnvironment, load_project_environment
        from src.workflows.models import RawMaterialRequest
        from src.workflows.service import WorkflowService

        print("\n[UTILITY] Standalone Raw Material Creation & Sorting...")
        env = None
        try:
            env = load_project_environment()
        except Exception:
            pass

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

        if env is None:
            from src.project.models import ProjectMetadata
            from src.project.storage import LocalWorkspaceStorage

            base_p = target_dir
            for parent in target_dir.parents:
                if (parent / "TESTSHEET").exists() or (parent / "PYTHON").exists():
                    base_p = parent
                    break
            meta = ProjectMetadata(key="utility", name="Utility Action", base_path=base_p)
            storage = LocalWorkspaceStorage(base_p)
            env = ProjectEnvironment(metadata=meta, storage=storage)

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
    return _make_stub_runner("Rename files")


def _load_pdf_extract_runner() -> Callable[[], object]:
    return _make_stub_runner("Extract PE pages from PDF")


def _load_combine_pdfs_runner() -> Callable[[], object]:
    return _make_stub_runner("Combine PDFs")


def _load_docx_to_pdf_runner() -> Callable[[], object]:
    return _make_stub_runner("Convert DOCX to PDF")


def _load_testsheet_to_pdf_runner() -> Callable[[], object]:
    return _make_stub_runner("Convert Testsheet to PDF")


def _load_rename_flir_runner() -> Callable[[], object]:
    return _make_stub_runner("Rename FLIR raw files")


def _load_diagonal_runner() -> Callable[[], object]:
    return _make_stub_runner("Apply diagonal borders")


def _load_replace_images_runner() -> Callable[[], object]:
    return _make_stub_runner("Replace signature images")


def _load_whatsapp_runner() -> Callable[[], object]:
    from src.project_workflow_actions import WhatsAppReportAction

    return lambda: WhatsAppReportAction("Generate WhatsApp report").execute(None)


def _load_remove_desktop_ini_runner() -> Callable[[], object]:
    from src.remove_desktop_ini_workflow import run_remove_desktop_ini

    return run_remove_desktop_ini


UTILITY_ACTIONS: tuple[UtilityAction, ...] = (
    UtilityAction("Create raw material folders", _load_raw_material_runner),
    UtilityAction("Rename files (match names from input dir)", _load_rename_files_runner),
    UtilityAction("Extract PE pages from PDF (black-page detection)", _load_pdf_extract_runner),
    UtilityAction("Combine PDFs from primary and secondary folders", _load_combine_pdfs_runner),
    UtilityAction("Convert DOCX to PDF (batch)", _load_docx_to_pdf_runner),
    UtilityAction("Convert Testsheet to PDF (batch)", _load_testsheet_to_pdf_runner),
    UtilityAction("Rename FLIR raw files numbering", _load_rename_flir_runner),
    UtilityAction("Apply diagonal borders to blank cells", _load_diagonal_runner),
    UtilityAction("Replace signature images in testsheets", _load_replace_images_runner),
    UtilityAction("Generate WhatsApp report (from Quick Reports)", _load_whatsapp_runner),
    UtilityAction("Remove desktop.ini files (recursive)", _load_remove_desktop_ini_runner),
)


def get_utility_actions() -> tuple[UtilityAction, ...]:
    """Return the immutable utility action registry."""
    return UTILITY_ACTIONS
