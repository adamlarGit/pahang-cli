"""Quick Report document Loader and compilation stage."""

from __future__ import annotations

import gc
import logging
from pathlib import Path
import shutil
from typing import Any

from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
from src.quick_report.cbm_summary import generate_cbm_tech_summary
from src.quick_report.compiler import DocumentCompiler, WordComDocumentCompiler
from src.quick_report.front_page import generate_front_page
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.sticker_page import generate_sticker_page
from src.quick_report.substation_condition import generate_substation_condition_pages
from src.quick_report.vi_defect_pages import generate_vi_defect_pages
from src.quick_report.vi_summary import generate_vi_summary

logger = logging.getLogger(__name__)


class QuickReportComposer:
    """Loader stage: renders docx report parts and compiles final Word document."""

    def __init__(self, compiler: DocumentCompiler | None = None) -> None:
        self.compiler = compiler or WordComDocumentCompiler()

    def load(self, plan: QuickReportStationPlan) -> Path:
        """Render docx parts, compile final document, and clean up temporary files."""
        plan.output_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = plan.output_dir / "temp_parts"
        temp_dir.mkdir(exist_ok=True)

        try:
            parts = self._generate_parts(plan, temp_dir)
            self.compiler.compile(parts, plan.final_output_path)
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
