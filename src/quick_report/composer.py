"""Quick Report document Loader and compilation stage."""

from __future__ import annotations

import gc
from pathlib import Path
import shutil

from docx import Document
from docxcompose.composer import Composer

try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None
    win32com = None

from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS
from src.quick_report.cbm_summary import generate_cbm_tech_summary
from src.quick_report.front_page import generate_front_page
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.sticker_page import generate_sticker_page
from src.quick_report.substation_condition import generate_substation_condition_pages
from src.quick_report.vi_defect_pages import generate_vi_defect_pages as generate_vi_defect_page
from src.quick_report.vi_summary import generate_vi_summary


class QuickReportComposer:
    """Loader stage: renders docx report parts and compiles final Word document."""

    def load(self, plan: QuickReportStationPlan) -> Path:
        """Render docx parts, compile final document, and clean up temporary files."""
        plan.output_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = plan.output_dir / "temp_parts"
        temp_dir.mkdir(exist_ok=True)

        try:
            parts = self._generate_parts(plan, temp_dir)
            self._compile_document(parts, plan.final_output_path)
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

        # 2A. CBM Tech Summary
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

        # 2. VI Defect Summary
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

        # 2B. CBM Defect Family Pages
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
            vi_pages = generate_vi_defect_page(
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

    def _compile_document(self, parts: list[Path], output_path: Path) -> None:
        """Compile document parts into final output file via Word COM or docxcompose."""
        if not parts:
            return

        if win32com and getattr(win32com, "client", None):
            word = None
            main_doc = None
            part_doc = None
            try:
                if pythoncom:
                    pythoncom.CoInitialize()
                shutil.copyfile(parts[0], output_path)
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = False
                word.DisplayAlerts = 0
                main_doc = word.Documents.Open(str(Path(output_path).resolve()))
                for part in parts[1:]:
                    part_doc = word.Documents.Open(str(Path(part).resolve()))
                    if hasattr(part_doc, "Paragraphs"):
                        while len(part_doc.Paragraphs) > 0:
                            last_p = part_doc.Paragraphs.Last
                            if (
                                hasattr(last_p, "Range")
                                and last_p.Range.Text.strip() == ""
                            ):
                                prev_count = len(part_doc.Paragraphs)
                                last_p.Range.Delete()
                                if len(part_doc.Paragraphs) == prev_count:
                                    break
                            else:
                                break
                    part_doc.Content.Copy()
                    rng = main_doc.Content
                    rng.Collapse(0)  # wdCollapseEnd
                    rng.InsertBreak(7)  # wdPageBreak
                    rng = main_doc.Content
                    rng.Collapse(0)  # wdCollapseEnd
                    rng.Paste()
                    part_doc.Close(False)
                    part_doc = None
                main_doc.Save()
                main_doc.Close(False)
                main_doc = None
                word.Quit()
                word = None
                return
            except Exception:
                if part_doc:
                    try:
                        part_doc.Close(False)
                    except Exception:
                        pass
                if main_doc:
                    try:
                        main_doc.Close(False)
                    except Exception:
                        pass
                if word:
                    try:
                        word.Quit()
                    except Exception:
                        pass
                raise
            finally:
                if pythoncom:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception:
                        pass

        master_doc = Document(parts[0])
        composer = Composer(master_doc)

        for part in parts[1:]:
            doc = Document(part)
            master_doc.add_page_break()
            composer.append(doc)

        composer.save(output_path)
