"""Quick Report document Loader and compilation stage."""

from __future__ import annotations

import ctypes
import gc
import logging
from pathlib import Path
import shutil
import time

from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
from src.quick_report.cbm_summary import generate_cbm_tech_summary
from src.quick_report.front_page import generate_front_page
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.sticker_page import generate_sticker_page
from src.quick_report.substation_condition import generate_substation_condition_pages
from src.quick_report.vi_defect_pages import generate_vi_defect_pages
from src.quick_report.vi_summary import generate_vi_summary

logger = logging.getLogger(__name__)

try:
    import pywintypes
except ImportError:
    pywintypes = None


def _clear_clipboard() -> None:
    """Clear Windows clipboard to eliminate Word COM OLE serialization stall on document close."""
    for _ in range(3):
        try:
            if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
                if ctypes.windll.user32.OpenClipboard(None):
                    ctypes.windll.user32.EmptyClipboard()
                    ctypes.windll.user32.CloseClipboard()
                    return
        except Exception:
            pass
        time.sleep(0.01)


def _collapse_and_escape_table(main_doc):
    """Collapse range to document end, inserting a minimal paragraph after table if selection is inside a table."""
    rng = main_doc.Content
    rng.Collapse(0)  # wdCollapseEnd = 0
    if rng.Information(12):  # 12 = wdWithInTable
        if main_doc.Tables.Count > 0:
            last_table = main_doc.Tables(main_doc.Tables.Count)
            last_table.Range.InsertParagraphAfter()
            # Minimize the escape paragraph to prevent blank page overflow.
            escape_rng = last_table.Range
            escape_rng.Collapse(0)  # wdCollapseEnd
            escape_rng.MoveEnd(1, 1)  # wdCharacter = 1, extend by 1 char
            escape_rng.Font.Size = 1
            escape_rng.ParagraphFormat.SpaceBefore = 0
            escape_rng.ParagraphFormat.SpaceAfter = 0
            escape_rng.ParagraphFormat.LineSpacingRule = 0  # wdLineSpaceSingle
        rng = main_doc.Content
        rng.Collapse(0)
    return rng


def _paste_with_retry(rng, max_attempts: int = 5, delay: float = 0.15) -> None:
    """Retry rng.PasteAndFormat(16) / rng.Paste() up to max_attempts times to preserve source formatting and handle COM errors."""
    exceptions: tuple[type[BaseException], ...]
    if pywintypes and hasattr(pywintypes, "com_error"):
        exceptions = (pywintypes.com_error, Exception)
    else:
        exceptions = (Exception,)

    for attempt in range(1, max_attempts + 1):
        try:
            if hasattr(rng, "PasteAndFormat"):
                try:
                    rng.PasteAndFormat(16)  # 16 = wdFormatOriginalFormatting
                    return
                except (AttributeError, TypeError):
                    rng.Paste()
                    return
            else:
                rng.Paste()
                return
        except exceptions as exc:
            if attempt == max_attempts:
                logger.error("rng paste failed after %d attempts: %s", max_attempts, exc)
                raise
            time.sleep(delay)


class QuickReportComposer:
    """Loader stage: renders docx report parts and compiles final Word document."""

    def load(self, plan: QuickReportStationPlan, word_app) -> Path:
        """Render docx parts, compile final document, and clean up temporary files."""
        plan.output_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = plan.output_dir / "temp_parts"
        temp_dir.mkdir(exist_ok=True)

        try:
            parts = self._generate_parts(plan, temp_dir)
            self._compile_document(parts, plan.final_output_path, word_app=word_app)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            gc.collect()

        return plan.final_output_path

    def _generate_parts(self, plan: QuickReportStationPlan, temp_dir: Path) -> list[Path]:
        """Generate individual docx parts for a substation quick report plan."""
        parts: list[Path] = []
        pe_info = plan.pe_info
        pkg = plan.package
        substation_number = pkg.substation_number
        cbm_defects = plan.cbm_defects
        vi_defects = plan.vi_defects

        # 1. Front Page
        parts.append(
            generate_front_page(
                pe_info,
                str(plan.front_page_template),
                str(temp_dir),
                substation_number,
            )
        )

        # 2. CBM Tech Summary
        if cbm_defects and plan.cbm_summary_template:
            parts.append(
                generate_cbm_tech_summary(
                    pe_info,
                    cbm_defects,
                    str(plan.cbm_summary_template),
                    str(temp_dir),
                    substation_number,
                )
            )

        # 3. VI Defect Summary
        if vi_defects and plan.vi_summary_template:
            parts.append(
                generate_vi_summary(
                    pe_info,
                    vi_defects,
                    str(plan.vi_summary_template),
                    str(temp_dir),
                    substation_number,
                )
            )

        # 4. CBM Defect Family Pages
        for family_plan in plan.cbm_defect_family_plans:
            family_pages = generate_cbm_defect_pages(
                family_plan,
                temp_dir,
                substation_number,
                pe_info,
            )
            parts.extend(family_pages)

        # 5. Substation Condition Page
        if plan.cond_template_path and plan.cond_template_path.exists():
            cond_pages = generate_substation_condition_pages(
                pe_info=pe_info,
                condition_pairs_or_pkg=plan.condition_pairs,
                template_path=plan.cond_template_path,
                output_dir=temp_dir,
                substation_number=substation_number,
            )
            parts.extend(cond_pages)

        # 6. VI Defect Pages
        if vi_defects and plan.vi_defect_template:
            vi_pages = generate_vi_defect_pages(
                vi_defects,
                str(plan.vi_defect_template),
                str(temp_dir),
                substation_number,
                pe_info,
            )
            parts.extend(vi_pages)

        # 7. Sticker Page
        parts.append(
            generate_sticker_page(
                pe_info,
                str(plan.sticker_template),
                str(temp_dir),
                substation_number,
            )
        )

        return parts

    def _compile_document(
        self, parts: list[Path], output_path: Path, word_app
    ) -> None:
        """Compile document parts into final output file via Word COM ActiveX Recopy & Paste."""
        if not parts:
            return
        if word_app is None:
            raise RuntimeError("word_app is required for Quick Report compilation.")

        main_doc = None
        try:
            main_doc = word_app.Documents.Add()
            for idx, part in enumerate(parts):
                part_path = str(Path(part).resolve())
                part_doc = None
                try:
                    part_doc = word_app.Documents.Open(part_path, False, True)
                    part_doc.Content.Copy()

                    rng = _collapse_and_escape_table(main_doc)
                    if idx > 0:
                        rng.InsertBreak(7)  # wdPageBreak = 7
                        rng = _collapse_and_escape_table(main_doc)

                    _paste_with_retry(rng)
                finally:
                    _clear_clipboard()
                    if part_doc is not None:
                        try:
                            part_doc.Close(False)
                        except Exception:
                            pass
                        part_doc = None

            main_doc.SaveAs2(str(Path(output_path).resolve()))
            main_doc.Close(False)
            main_doc = None
        finally:
            _clear_clipboard()
            if main_doc is not None:
                try:
                    main_doc.Close(False)
                except Exception:
                    pass
