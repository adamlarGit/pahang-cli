"""Quick Report orchestration and compilation."""

from __future__ import annotations

import gc
import logging
from pathlib import Path

from docx import Document
from docxcompose.composer import Composer
from docxtpl import DocxTemplate

from src.project.environment import ProjectEnvironment
from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS
from src.quick_report.cbm_render import (
    generate_cbm_tech_summary,
    generate_front_page,
    generate_quick_report_detail_pages,
)
from src.quick_report.utils import normalize_functional_location_input, sanitize_filename
from src.quick_report.visual_render import generate_vi_defect_page, generate_vi_summary
from src.testsheet.models import SubstationTestsheetPackage
from src.testsheet.repository import SubstationTestsheetRepository
from src.workflows.models import QuickReportMode, QuickReportRequest, QuickReportResult


class QuickReportComposer:
    """Orchestrator for Pahang 7-part quick report document generation."""

    def compose(self, environment: ProjectEnvironment, request: QuickReportRequest) -> QuickReportResult:
        """Compose quick reports based on the requested mode."""
        generated_paths: list[Path] = []
        warnings: list[str] = []
        errors: list[str] = []
        reports_generated = 0

        repo = SubstationTestsheetRepository()
        packages = []

        if request.mode == QuickReportMode.FOLDER:
            for folder_str in request.target_folders:
                candidate = Path(folder_str)
                folder_path = candidate if candidate.exists() else environment.get_testsheet_dir() / folder_str
                if folder_path.exists():
                    packages.extend(repo.discover_packages(folder_path))
        elif request.mode == QuickReportMode.FL:
            target_fls = {normalize_functional_location_input(fl) for fl in request.target_package_names}
            all_packages = repo.discover_packages(environment.get_testsheet_dir())
            packages = [
                pkg for pkg in all_packages
                if pkg.data and normalize_functional_location_input(pkg.data.fl_number) in target_fls
            ]

        if request.progress_sink:
            request.progress_sink(f"Found {len(packages)} packages to process.")

        for i, pkg in enumerate(packages, start=1):
            if request.progress_sink:
                request.progress_sink(f"[{i}/{len(packages)}] Generating quick report for {pkg.station}...")
            
            try:
                out_path = self._process_station(environment, pkg, request.substation_condition_template_path)
                if out_path:
                    generated_paths.append(out_path)
                    reports_generated += 1
            except Exception as e:
                errors.append(f"Failed to process {pkg.station}: {e}")
                logging.exception(f"Failed to process {pkg.station}")

        return QuickReportResult(
            reports_generated=reports_generated,
            generated_paths=generated_paths,
            warnings=warnings,
            errors=errors,
        )

    def _resolve_output_dir(self, environment: ProjectEnvironment, pkg: SubstationTestsheetPackage) -> Path:
        """Resolve output directory mirroring TESTSHEET hierarchy: QUICK REPORT/<STATION>/<MONTH>/<DATE>/."""
        if pkg.station and pkg.month and pkg.date_str:
            return environment.get_quick_report_dir() / pkg.station / pkg.month / pkg.date_str
        if pkg.date_str:
            return environment.get_quick_report_dir() / pkg.date_str
        return environment.get_quick_report_dir()

    def _build_substation_condition_pairs(self) -> list[tuple[str, str]]:
        """
        Build active 2-column pairs for the substation condition page.
        TODO: Implement full equipment extraction from testsheet.
        """
        return [
            ("SUBSTATION OVERVIEW", "SIGNBOARD")
        ]

    def _remove_empty_cell_borders_sub_cond(self, docx_path: Path, active_count: int) -> None:
        """Clear borders for unused substation condition cells."""
        import zipfile
        import xml.etree.ElementTree as ET

        if active_count >= 3:
            return

        temp_path = docx_path.with_suffix(".tmp.docx")
        with zipfile.ZipFile(docx_path, "r") as zin:
            with zipfile.ZipFile(temp_path, "w") as zout:
                for item in zin.infolist():
                    if item.filename == "word/document.xml":
                        xml_content = zin.read(item.filename)
                        root = ET.fromstring(xml_content)
                        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                        
                        # Assuming each pair is a row in a main table, or separate tables
                        # For now, replicate the logic to find tables and remove borders if > active_count
                        tables = root.findall(".//w:tbl", ns)
                        for i, table in enumerate(tables):
                            if i >= active_count:
                                for tc in table.findall(".//w:tc", ns):
                                    tcPr = tc.find("w:tcPr", ns)
                                    if tcPr is not None:
                                        tcBorders = tcPr.find("w:tcBorders", ns)
                                        if tcBorders is not None:
                                            for border in tcBorders:
                                                border.set(f"{{{ns['w']}}}val", "nil")

                        zout.writestr(item, ET.tostring(root))
                    else:
                        zout.writestr(item, zin.read(item.filename))
        
        temp_path.replace(docx_path)

    def _calculate_suffix(self, cbm_defects: list[dict], vi_defects: list[dict]) -> str:
        suffix_parts = []
        if any(d.get("technology") == "IR" for d in cbm_defects):
            suffix_parts.append("IR")
        if any(d.get("technology") == "US" for d in cbm_defects):
            suffix_parts.append("US")
        if any(d.get("technology") == "TEV" for d in cbm_defects):
            suffix_parts.append("TEV")
        if vi_defects:
            suffix_parts.append("VI")
            
        return f" ({'+'.join(suffix_parts)})" if suffix_parts else ""

    def _process_station(self, environment: ProjectEnvironment, pkg: SubstationTestsheetPackage, cond_template_path: Path | None) -> Path | None:
        if not pkg.data:
            return None

        pe_info = {
            "substation": {
                "name_erms": pkg.data.substation_name_erms,
                "date": pkg.data.date_str,
                "gps_coordinate": pkg.data.gps_coordinate,
                "substation_type": pkg.data.type_code,
                "building_type": pkg.data.building_type,
            }
        }

        pe_number = pkg.pe_num
        sanitized_name = sanitize_filename(pkg.data.substation_name_erms or pkg.data.substation_name)

        # TODO: Real defect fetching from QR03 CBA/VI
        cbm_defects = []
        vi_defects = []

        # Calculate suffix
        suffix = self._calculate_suffix(cbm_defects, vi_defects)
        suffix_parts = suffix.replace(" (", "").replace(")", "").split("+") if suffix else []
        output_filename = f"{pe_number:03d}. {sanitized_name}{suffix}.docx"
        
        output_dir = self._resolve_output_dir(environment, pkg)
        output_dir.mkdir(parents=True, exist_ok=True)
        final_output_path = output_dir / output_filename

        parts: list[Path] = []
        temp_dir = output_dir / "temp_parts"
        temp_dir.mkdir(exist_ok=True)

        try:
            # 1. Front Page
            fp_template = environment.get_template("vi_front_page")
            if "US" in suffix_parts or "TEV" in suffix_parts:
                fp_template = environment.get_template("vi_front_page_ir_us_tev")
            parts.append(generate_front_page(pe_info, str(fp_template), str(temp_dir), pe_number))

            # 2A. CBM Tech Summary
            if cbm_defects:
                cbm_summary_template = environment.get_template("cbm_summary_ir")
                if "US" in suffix_parts or "TEV" in suffix_parts:
                    cbm_summary_template = environment.get_template("cbm_summary_ir_us_tev")
                parts.append(generate_cbm_tech_summary(pe_info, cbm_defects, str(cbm_summary_template), str(temp_dir), pe_number))

            # 2. VI Defect Summary
            if vi_defects:
                vi_summary_template = environment.get_template("vi_summary")
                parts.append(generate_vi_summary(pe_info, vi_defects, str(vi_summary_template), str(temp_dir), pe_number))

            # 2B. CBM Defect Family Pages
            if cbm_defects:
                for spec in QUICK_REPORT_FAMILY_SPECS:
                    family_defects = [d for d in cbm_defects if d.get("equipment", "").upper() in spec.equipment_values]
                    if not family_defects:
                        continue
                        
                    template_paths = {}
                    if spec.overview_template_key:
                        t = environment.get_template(spec.overview_template_key)
                        if t: template_paths[spec.overview_template_key] = str(t)
                    for role in spec.detail_roles:
                        t = environment.get_template(role.template_key)
                        if t: template_paths[role.template_key] = str(t)
                        
                    groups = [{"item_key": d.get("equipment", ""), "defects": [d], "overview": d} for d in family_defects]
                    
                    family_pages = generate_quick_report_detail_pages(
                        groups,
                        spec,
                        template_paths,
                        str(temp_dir),
                        pe_number,
                        pe_info,
                    )
                    parts.extend(family_pages)

            # 5. Substation Condition Page
            if cond_template_path and cond_template_path.exists():
                pairs = self._build_substation_condition_pairs()
                chunks = [pairs[i:i + 3] for i in range(0, len(pairs), 3)]
                if not chunks:
                    chunks = [[]]
                    
                for idx, chunk in enumerate(chunks, start=1):
                    cond_out = temp_dir / f"{pe_number:03d}_5 SUBSTATION CONDITION part{idx}.docx"
                    
                    padded_chunk = list(chunk)
                    while len(padded_chunk) < 3:
                        padded_chunk.append(("", ""))
                        
                    context = {
                        "pairs": [{"left": p[0], "right": p[1]} for p in padded_chunk]
                    }
                    context.update(pe_info)
                    
                    doc = DocxTemplate(str(cond_template_path))
                    doc.render(context)
                    doc.save(cond_out)
                    
                    if idx == len(chunks) and len(chunk) < 3:
                        self._remove_empty_cell_borders_sub_cond(cond_out, len(chunk))
                        
                    parts.append(cond_out)

            # 6. VI Defect Pages
            if vi_defects:
                vi_defect_template = environment.get_template("vi_defect")
                vi_pages = generate_vi_defect_page(vi_defects, str(vi_defect_template), str(temp_dir), pe_number, pe_info)
                parts.extend(vi_pages)

            # 7. Sticker Page
            sticker_template = environment.get_template("sticker_page")
            sticker_out = temp_dir / f"{pe_number:03d}_11 STICKER PAGE.docx"
            import shutil
            shutil.copy2(sticker_template, sticker_out)
            parts.append(sticker_out)

            self._compile_document(parts, final_output_path)
            
        finally:
            # Cleanup temp parts
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            gc.collect()

        return final_output_path

    def _compile_document(self, parts: list[Path], output_path: Path) -> None:
        if not parts:
            return
        
        master_doc = Document(parts[0])
        composer = Composer(master_doc)
        
        for part in parts[1:]:
            doc = Document(part)
            master_doc.add_page_break()
            composer.append(doc)
            
        composer.save(output_path)
