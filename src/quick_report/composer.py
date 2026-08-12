"""Quick Report document Loader and compilation stage."""

from __future__ import annotations

import gc
import logging
from pathlib import Path
import shutil

logger = logging.getLogger(__name__)

try:
    import pythoncom
    import win32com.client
except ImportError:
    pythoncom = None
    win32com = None

from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
from src.quick_report.cbm_summary import generate_cbm_tech_summary
from src.quick_report.front_page import generate_front_page
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.sticker_page import generate_sticker_page
from src.quick_report.substation_condition import generate_substation_condition_pages
from src.quick_report.vi_defect_pages import generate_vi_defect_pages
from src.quick_report.vi_summary import generate_vi_summary


class QuickReportComposer:
    """Loader stage: renders docx report parts and compiles final Word document."""

    def load(self, plan: QuickReportStationPlan, word_app=None) -> Path:
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
        self, parts: list[Path], output_path: Path, word_app=None
    ) -> None:
        """Compile document parts into final output file via Word COM ActiveX Recopy & Paste."""
        if not parts:
            return

        if not (win32com and getattr(win32com, "client", None) and pythoncom):
            raise RuntimeError("win32com is required for Quick Report compilation.")

        word = None
        own_word = False
        main_doc = None
        try:
            if word_app is not None:
                word = word_app
                own_word = False
            else:
                if pythoncom:
                    pythoncom.CoInitialize()
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = False
                word.DisplayAlerts = 0
                own_word = True

            main_doc = word.Documents.Add()
            for idx, part in enumerate(parts):
                part_path = str(Path(part).resolve())
                part_doc = word.Documents.Open(part_path, False, True)
                part_doc.Content.Copy()
                part_doc.Close(False)

                rng = main_doc.Content
                rng.Collapse(0)  # wdCollapseEnd = 0
                if idx > 0:
                    rng.InsertBreak(7)  # wdPageBreak = 7
                    rng = main_doc.Content
                    rng.Collapse(0)
                rng.Paste()

            main_doc.SaveAs2(str(Path(output_path).resolve()))
            main_doc.Close(False)
            main_doc = None
        finally:
            if main_doc is not None:
                try:
                    main_doc.Close(False)
                except Exception:
                    pass
            if own_word and word:
                try:
                    word.Quit()
                except Exception:
                    pass
            if own_word and pythoncom:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
