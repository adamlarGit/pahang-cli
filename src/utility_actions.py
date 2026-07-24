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


def _load_raw_material_runner():
    return _make_stub_runner("Create raw material folders")


def _load_rename_files_runner():
    return _make_stub_runner("Rename files")


def _load_pdf_extract_runner():
    return _make_stub_runner("Extract PE pages from PDF")


def _load_combine_pdfs_runner():
    return _make_stub_runner("Combine PDFs")


def _load_docx_to_pdf_runner():
    return _make_stub_runner("Convert DOCX to PDF")


def _load_testsheet_to_pdf_runner():
    return _make_stub_runner("Convert Testsheet to PDF")


def _load_rename_flir_runner():
    return _make_stub_runner("Rename FLIR raw files")


def _load_diagonal_runner():
    return _make_stub_runner("Apply diagonal borders")


def _load_replace_images_runner():
    return _make_stub_runner("Replace signature images")


def _load_whatsapp_runner():
    from src.project_workflow_actions import WhatsAppReportAction

    return lambda: WhatsAppReportAction("Generate WhatsApp report").execute(None)


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
)


def get_utility_actions() -> tuple[UtilityAction, ...]:
    """Return the immutable utility action registry."""
    return UTILITY_ACTIONS
