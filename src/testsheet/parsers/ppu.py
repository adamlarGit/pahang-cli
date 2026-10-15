"""33kV PPU testsheet parser implementing TestsheetParserStrategy."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import ClassVar, Sequence
import warnings
import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from src.core.normalizers import (
    format_humidity_str,
    format_load_amp,
    format_testsheet_time,
    parse_background_temp,
)
from src.testsheet.models import (
    PhotoRange,
    RawPhotoRanges,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
    VisualInspectionFinding,
)
from src.testsheet.parsers.base import TestsheetParserStrategy
from src.testsheet.parsers.common import (
    clean_val,
    find_next_val,
    is_marked,
    normalize_fl_erms,
    parse_int_safe,
    parse_photo_numbers,
    parse_range_val,
    to_excel_date,
)


class PpuTestsheetParser(TestsheetParserStrategy):
    """Parser strategy for 33kV PPU/SSU/PMU multi-sheet workbooks."""

    __test__ = False
    HANDLED_PREFIXES: ClassVar[tuple[str, ...]] = (
        "33kV (Main)",
        "33kV (Extra)",
        "11kV (Main)",
        "11kV (Extra)",
    )

    def can_handle_sheets(self, sheet_names: Sequence[str]) -> bool:
        """Return True if sheets contain 33kV or 11kV PPU sheets."""
        for s in sheet_names:
            s_clean = s.strip()
            if any(s_clean.startswith(prefix) for prefix in self.HANDLED_PREFIXES):
                return True
        return False

    def extract_photo_ranges(self, workbook_path: Path | str) -> RawPhotoRanges:
        """Extract IR and DG photo range bounds from 33kV testsheet RAW DATA sheet."""
        path = Path(workbook_path)
        if not path.exists():
            raise FileNotFoundError(f"Testsheet workbook not found: {path}")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            try:
                if "RAW DATA" in wb.sheetnames:
                    return self._parse_raw_data_sheet(wb["RAW DATA"])
            finally:
                wb.close()

        return RawPhotoRanges()

    def extract_testsheet_metadata(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Fast read-only extraction of header metadata required for TOTAL PE."""
        path = Path(workbook_path)
        if not path.exists():
            raise FileNotFoundError(f"Testsheet workbook not found: {path}")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            try:
                sheet_names = wb.sheetnames
                ws_33_main = wb["33kV (Main)"] if "33kV (Main)" in sheet_names else None
                ws_11_main = wb["11kV (Main)"] if "11kV (Main)" in sheet_names else None

                # Substation number resolution hierarchy
                substation_number = self._resolve_substation_number(path, ws_33_main, ws_11_main)

                # Header metadata priority: 33kV (Main) -> 11kV (Main)
                ws_header = ws_33_main if ws_33_main is not None else ws_11_main
                meta = self._extract_header_metadata(ws_header, station_hint, date_hint)

                # Substation type
                substation_type = self._resolve_substation_type(meta["substation_name_site"], path.name)

                # GPS from Visual Inspec. sheet
                gps_coordinate = ""
                ws_vi = self._find_vi_sheet(wb)
                if ws_vi is not None:
                    gps_val = clean_val(ws_vi["D3"].value)
                    if gps_val:
                        gps_coordinate = gps_val

                equipment = SubstationEquipmentPackage(
                    switchgears=(meta["swg_meta"],) if meta["swg_meta"] is not None else ()
                )

            finally:
                wb.close()

        return TestsheetData(
            substation_number=substation_number,
            station_name=station_hint or meta["substation_name_erms"],
            date_str=meta["date_str"],
            fl_erms=meta["fl_erms"],
            fl_site=meta["fl_site"],
            substation_name_erms=meta["substation_name_erms"],
            substation_name_site=meta["substation_name_site"],
            gps_coordinate=gps_coordinate,
            substation_type=substation_type,
            ambient=meta["ambient"],
            humidity=meta["humidity"],
            time=meta["time_str"],
            tev_background=meta["tev_background"],
            cycle_1=meta["cycle_1"],
            equipment=equipment,
        )

    def extract_testsheet_data(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Parse 33kV testsheet workbook."""
        path = Path(workbook_path)
        if not path.exists():
            raise FileNotFoundError(f"Testsheet workbook not found: {path}")

        wb = openpyxl.load_workbook(path, data_only=True)
        try:
            sheet_names = wb.sheetnames
            ws_33_main = wb["33kV (Main)"] if "33kV (Main)" in sheet_names else None
            ws_11_main = wb["11kV (Main)"] if "11kV (Main)" in sheet_names else None

            # 1. Substation number resolution hierarchy
            substation_number = self._resolve_substation_number(path, ws_33_main, ws_11_main)

            # 2. Header metadata extraction (33kV -> 11kV fallback)
            ws_header = ws_33_main if ws_33_main is not None else ws_11_main
            meta = self._extract_header_metadata(ws_header, station_hint, date_hint)

            # Substation type
            substation_type = self._resolve_substation_type(meta["substation_name_site"], path.name)

            # GPS from Visual Inspec. sheet
            gps_coordinate = ""
            ws_vi = self._find_vi_sheet(wb)
            if ws_vi is not None:
                gps_val = clean_val(ws_vi["D3"].value)
                if gps_val:
                    gps_coordinate = gps_val

            # 3. Switchgear lineups assembly
            switchgears: list[SwitchgearSpec] = []

            # 33kV Lineup
            if ws_33_main is not None:
                extra_33 = self._find_extra_sheets(wb, "33kV (Extra)")
                swg_33 = self._parse_switchgear_lineup(ws_33_main, extra_sheets=extra_33)
                if swg_33 is not None:
                    switchgears.append(swg_33)

            # 11kV Lineup
            if ws_11_main is not None:
                extra_11 = self._find_extra_sheets(wb, "11kV (Extra)")
                swg_11 = self._parse_switchgear_lineup(ws_11_main, extra_sheets=extra_11)
                if swg_11 is not None:
                    switchgears.append(swg_11)

            if not switchgears:
                raise ValueError(
                    f"No populated 33kV or 11kV switchgear lineups found in {path.name}"
                )

            # 4. Visual Inspection findings
            visual_findings: list[VisualInspectionFinding] = []
            if ws_vi is not None:
                visual_findings = self._parse_visual_inspection_findings(ws_vi)

            # 5. Photo range bounds
            photo_ranges = RawPhotoRanges()
            if "RAW DATA" in wb.sheetnames:
                photo_ranges = self._parse_raw_data_sheet(wb["RAW DATA"])

        finally:
            wb.close()

        equipment = SubstationEquipmentPackage(
            switchgears=tuple(switchgears),
        )

        return TestsheetData(
            substation_number=substation_number,
            station_name=station_hint or meta["substation_name_erms"],
            date_str=meta["date_str"],
            fl_erms=meta["fl_erms"],
            fl_site=meta["fl_site"],
            photo_ranges=photo_ranges,
            substation_name_erms=meta["substation_name_erms"],
            substation_name_site=meta["substation_name_site"],
            gps_coordinate=gps_coordinate,
            substation_type=substation_type,
            ambient=meta["ambient"],
            humidity=meta["humidity"],
            time=meta["time_str"],
            tev_background=meta["tev_background"],
            cycle_1=meta["cycle_1"],
            equipment=equipment,
            visual_findings=tuple(visual_findings),
        )

    def _resolve_substation_number(
        self,
        path: Path,
        ws_33: Worksheet | None,
        ws_11: Worksheet | None,
    ) -> int:
        """Resolve substation number in strict hierarchy: V2 33kV -> V2 11kV -> filename prefix -> ValueError."""
        # 1. Cell V2 on 33kV (Main)
        if ws_33 is not None:
            num = self._parse_positive_int(ws_33["V2"].value)
            if num is not None:
                return num

        # 2. Cell V2 on 11kV (Main)
        if ws_11 is not None:
            num = self._parse_positive_int(ws_11["V2"].value)
            if num is not None:
                return num

        # 3. Filename leading numeric prefix
        m = re.match(r"^(\d+)", path.name)
        if m:
            num = int(m.group(1))
            if num > 0:
                return num

        # 4. Fail fast
        raise ValueError(f"Unable to determine substation number for {path.name}")

    def _extract_header_metadata(
        self,
        ws_header: Worksheet | None,
        station_hint: str = "",
        date_hint: str = "",
    ) -> dict[str, Any]:
        """Extract header metadata cells (D6..D9, U6..U8, L6..L11) from main switchgear sheet."""
        fl_site = ""
        fl_erms = ""
        substation_name_site = ""
        substation_name_erms = ""
        date_str = date_hint
        cycle_1: datetime | None = None
        time_str = "-"
        ambient = "-"
        humidity = "-"
        tev_background = "-"
        swg_meta: SwitchgearSpec | None = None

        if ws_header is not None:
            raw_name = clean_val(ws_header["D6"].value) or ""
            substation_name_site = raw_name
            substation_name_erms = raw_name or station_hint

            raw_fl = ws_header["D7"].value
            fl_site = clean_val(raw_fl) or ""
            fl_erms = normalize_fl_erms(raw_fl)

            cycle_1 = to_excel_date(ws_header["D8"].value)
            if cycle_1 is not None and not date_str:
                date_str = cycle_1.strftime("%d-%m-%Y")

            time_str = format_testsheet_time(ws_header["D9"].value)
            ambient = parse_background_temp(ws_header["U6"].value)
            humidity = format_humidity_str(ws_header["U7"].value)
            tev_bg_val = clean_val(ws_header["U8"].value)
            if tev_bg_val is not None:
                tev_background = str(tev_bg_val)

            # Switchgear Details (L6..L11)
            manufacturer = clean_val(ws_header["L6"].value) or ""
            year = clean_val(ws_header["L7"].value) or ""
            model = clean_val(ws_header["L8"].value) or ""
            serial_no = clean_val(ws_header["L9"].value) or ""
            swg_type = clean_val(ws_header["L10"].value) or ""
            rating = clean_val(ws_header["L11"].value) or ""
            if any((manufacturer, year, model, serial_no, swg_type, rating)):
                swg_meta = SwitchgearSpec(
                    switchgear_type=swg_type,
                    manufacturer=manufacturer,
                    model=model,
                    manufactured_year=year,
                    rating=rating,
                    serial_no=serial_no,
                )

        return {
            "fl_site": fl_site,
            "fl_erms": fl_erms,
            "substation_name_site": substation_name_site,
            "substation_name_erms": substation_name_erms,
            "date_str": date_str,
            "cycle_1": cycle_1,
            "time_str": time_str,
            "ambient": ambient,
            "humidity": humidity,
            "tev_background": tev_background,
            "swg_meta": swg_meta,
        }

    def _parse_positive_int(self, val: object) -> int | None:
        """Convert a cell value into a positive integer, returning None on invalid/non-positive."""
        if val is None or val == "":
            return None
        val_str = str(val).strip()
        if val_str in ("", "-", "None", "N/A"):
            return None
        try:
            num = int(float(val_str))
            if num > 0:
                return num
        except (ValueError, TypeError):
            pass
        return None

    def _resolve_substation_type(self, name: str, filename: str) -> str:
        """Extract substation type (PPU, SSU, PMU, MPPU) from station name or filename."""
        for candidate in (name, filename):
            m = re.search(r"\b(PPU|SSU|PMU|MPPU)\b", candidate, re.IGNORECASE)
            if m:
                return m.group(1).upper()
        return ""

    def _find_vi_sheet(self, wb: openpyxl.Workbook) -> Worksheet | None:
        """Locate Visual Inspection worksheet by known name patterns."""
        for sname in wb.sheetnames:
            s_clean = sname.strip().lower()
            if s_clean in ("visual inspec.", "visual inspection", "visual inspec"):
                return wb[sname]
            if s_clean.startswith("visual inspec"):
                return wb[sname]
        return None

    def _find_extra_sheets(self, wb: openpyxl.Workbook, prefix: str) -> list[Worksheet]:
        """Find and sequentially sort extra switchgear sheets (e.g. 33kV (Extra))."""
        matched: list[Worksheet] = []
        for sname in wb.sheetnames:
            s_clean = sname.strip()
            if s_clean.startswith(prefix):
                matched.append(wb[sname])

        def sort_key(ws: Worksheet) -> int:
            m = re.search(r"\((\d+)\)", ws.title)
            if m:
                return int(m.group(1))
            return 1

        return sorted(matched, key=sort_key)

    def _parse_switchgear_lineup(
        self,
        ws_main: Worksheet,
        extra_sheets: list[Worksheet],
    ) -> SwitchgearSpec | None:
        """Parse switchgear lineup across main and extra sheets."""
        # Details from L6..L11
        manufacturer = clean_val(ws_main["L6"].value) or ""
        manufactured_year = clean_val(ws_main["L7"].value) or ""
        model = clean_val(ws_main["L8"].value) or ""
        serial_no = clean_val(ws_main["L9"].value) or ""
        switchgear_type = clean_val(ws_main["L10"].value) or ""
        rating = clean_val(ws_main["L11"].value) or ""

        # Panels extraction across main sheet and extra sheets
        panels: list[SwitchgearPanelSpec] = []
        panel_counter = 1

        for ws in [ws_main] + extra_sheets:
            sheet_panels = self._parse_sheet_panels(ws, start_index=panel_counter)
            panels.extend(sheet_panels)
            panel_counter += len(sheet_panels)

        # Overview Bays (Rows 63-74 on main sheet)
        overview_rhs = self._extract_overview_photos(ws_main, start_row=63, end_row=68)
        overview_lhs = self._extract_overview_photos(ws_main, start_row=69, end_row=74)

        all_overview_photos: list[int] = []
        for n in overview_rhs + overview_lhs:
            if n not in all_overview_photos:
                all_overview_photos.append(n)

        # If no physical panels found, return None (overview photos alone do not constitute an active lineup)
        if not panels:
            return None

        # Prepend synthetic OVERVIEW RHS and OVERVIEW LHS panels
        synthetic_panels: list[SwitchgearPanelSpec] = []
        if overview_rhs:
            synthetic_panels.append(
                SwitchgearPanelSpec(
                    panel_no=0,
                    panel_feeder_no="OVERVIEW RHS",
                    name="OVERVIEW RHS",
                    photo_numbers=overview_rhs,
                )
            )
        if overview_lhs:
            synthetic_panels.append(
                SwitchgearPanelSpec(
                    panel_no=0,
                    panel_feeder_no="OVERVIEW LHS",
                    name="OVERVIEW LHS",
                    photo_numbers=overview_lhs,
                )
            )

        full_panel_list = tuple(synthetic_panels + panels)

        return SwitchgearSpec(
            switchgear_type=switchgear_type,
            manufacturer=manufacturer,
            model=model,
            manufactured_year=manufactured_year,
            rating=rating,
            serial_no=serial_no,
            panels=full_panel_list,
            photo_numbers=tuple(all_overview_photos),
        )

    def _parse_sheet_panels(
        self,
        ws: Worksheet,
        start_index: int = 1,
    ) -> list[SwitchgearPanelSpec]:
        """Parse 6-row stride switchgear panels from Rows 15 to 62."""
        panels: list[SwitchgearPanelSpec] = []
        panel_idx = start_index

        for r in range(15, 63, 6):
            if r > ws.max_row:
                break

            feeder_no = clean_val(ws[f"B{r}"].value) or ""
            name = clean_val(ws[f"C{r}"].value) or ""

            # Unpopulated template bays (blank panel no and feeder name) are skipped
            if not feeder_no and not name:
                continue

            status = clean_val(ws[f"D{r}"].value) or clean_val(ws[f"E{r}"].value) or ""
            load_raw = clean_val(ws[f"F{r}"].value) or ""
            norm_load = format_load_amp(load_raw)
            load_amp = "" if norm_load == "-" else norm_load
            cable_type = clean_val(ws[f"G{r}"].value) or ""
            heater_amp = clean_val(ws[f"H{r}"].value) or ""
            panel_type = clean_val(ws[f"J{r}"].value) or ""
            breaker_serial = clean_val(ws[f"V{r}"].value) or clean_val(ws[f"I{r}"].value) or ""

            # 6-Row Stride photo parsing (Col P)
            # Row 1 (r): Breaker
            breaker_photos = parse_photo_numbers(ws[f"P{r}"].value)
            breaker_photo = breaker_photos[0] if breaker_photos else None

            # Row 2 (r+1): Cable
            cable_photos = parse_photo_numbers(ws[f"P{r + 1}"].value)
            cable_photo = cable_photos[0] if cable_photos else None

            # Row 3 (r+2): Busbar (Top)
            busbar_photos = parse_photo_numbers(ws[f"P{r + 2}"].value)
            busbar_photo = busbar_photos[0] if busbar_photos else None

            # Row 4 (r+3): PT Compartment
            pt_photos = parse_photo_numbers(ws[f"P{r + 3}"].value)
            pt_photo = pt_photos[0] if pt_photos else None

            # Row 5 (r+4): Cable Entry
            cable_entry_photos = parse_photo_numbers(ws[f"P{r + 4}"].value)
            cable_entry_photo = cable_entry_photos[0] if cable_entry_photos else None

            # Row 6 (r+5): Link Box
            link_box_photos = parse_photo_numbers(ws[f"P{r + 5}"].value)
            link_box_photo = link_box_photos[0] if link_box_photos else None

            # Secondary Compartment: Inspect Column Q across panel rows for regex SP: <photo>
            secondary_photo: int | None = None
            for sub_r in range(r, r + 6):
                if sub_r <= ws.max_row:
                    q_val = str(ws[f"Q{sub_r}"].value or "").strip()
                    if q_val:
                        m_sp = re.search(r"(?:\bSP:|\bSP\s*:)\s*(\d+)", q_val, re.IGNORECASE)
                        if m_sp:
                            secondary_photo = int(m_sp.group(1))
                            break

            # PT measurement detection in Row 4 (r+3)
            has_pt = False
            pt_row = r + 3
            if pt_row <= ws.max_row:
                for col in ("K", "L", "M", "N", "R", "S", "T", "U", "V"):
                    if clean_val(ws[f"{col}{pt_row}"].value) is not None:
                        has_pt = True
                        break

            # Aggregate all distinct photo integers for this panel in order
            discovered: list[int] = []
            for n_list in (
                breaker_photos,
                cable_photos,
                busbar_photos,
                pt_photos,
                cable_entry_photos,
                link_box_photos,
            ):
                for n in n_list:
                    if n not in discovered:
                        discovered.append(n)
            if secondary_photo is not None and secondary_photo not in discovered:
                discovered.append(secondary_photo)

            panel = SwitchgearPanelSpec(
                panel_no=panel_idx,
                panel_feeder_no=feeder_no,
                name=name,
                panel_type=panel_type,
                serial_no=breaker_serial,
                status=status,
                load_amp=load_amp,
                cable_type=cable_type,
                heater_amp=heater_amp,
                breaker_photo=breaker_photo,
                cable_photo=cable_photo,
                busbar_photo=busbar_photo,
                pt_photo=pt_photo,
                cable_entry_photo=cable_entry_photo,
                link_box_photo=link_box_photo,
                secondary_photo=secondary_photo,
                has_pt_measurement=has_pt,
                photo_numbers=tuple(discovered),
            )
            panels.append(panel)
            panel_idx += 1

        return panels

    def _extract_overview_photos(
        self,
        ws: Worksheet,
        start_row: int,
        end_row: int,
    ) -> tuple[int, ...]:
        """Extract overview photo numbers from Column P within row range."""
        photos: list[int] = []
        for r in range(start_row, end_row + 1):
            if r <= ws.max_row:
                nums = parse_photo_numbers(ws[f"P{r}"].value)
                for n in nums:
                    if n not in photos:
                        photos.append(n)
        return tuple(photos)

    def _parse_visual_inspection_findings(
        self,
        ws: Worksheet,
    ) -> list[VisualInspectionFinding]:
        """Parse Visual Inspec. sheet checklist defects (Rows 8-76) and Category 8 (Rows 78-80)."""
        findings: list[VisualInspectionFinding] = []
        current_category = ""

        # Checklist Rows 8-76
        for r in range(8, 77):
            if r > ws.max_row:
                break

            b_val = clean_val(ws[f"B{r}"].value)
            c_val = clean_val(ws[f"C{r}"].value)

            if not b_val and not c_val:
                continue

            # Section header (e.g. "1. CIVIL & STRUCTURAL")
            if b_val and re.match(r"^\d+\.\s+[A-Za-z]", b_val):
                current_category = b_val
                continue

            # Item number (e.g. "1.1", "2.1")
            is_item = b_val and re.match(r"^\d+\.\d+", b_val)
            item_no = b_val if is_item else ""
            description = c_val or ""

            # Check status
            status = "YES"
            d_val = ws[f"D{r}"].value
            e_val = ws[f"E{r}"].value

            if clean_val(d_val) == "NO" or clean_val(e_val) == "NO":
                status = "NO"
            elif is_marked(e_val) and not is_marked(d_val):
                status = "NO"
            elif is_marked(d_val):
                status = "YES"
            else:
                status = ""

            remarks = clean_val(ws[f"F{r}"].value) or ""
            if not remarks:
                # Check for remarks in neighboring columns
                for col in ("G", "H", "I"):
                    val = clean_val(ws[f"{col}{r}"].value)
                    if val:
                        remarks = val
                        break

            # Record items marked 'NO' or having non-empty remarks
            if status == "NO" or bool(remarks):
                findings.append(
                    VisualInspectionFinding(
                        category=current_category,
                        item_no=item_no,
                        description=description,
                        status=status,
                        remarks=remarks,
                    )
                )

        # Category 8 "Other Findings" (Rows 78-80)
        for r in range(78, 81):
            if r > ws.max_row:
                break
            desc_val = clean_val(ws[f"C{r}"].value) or ""
            remark_val = clean_val(ws[f"F{r}"].value) or ""

            if desc_val.upper() in ("OTHER FINDINGS", "8.", "8", "NO", "YES"):
                desc_val = ""
            if remark_val.upper() in ("OTHER FINDINGS", "8.", "8", "NO", "YES"):
                remark_val = ""

            if not desc_val and not remark_val:
                for col in ("B", "D", "E"):
                    val = clean_val(ws[f"{col}{r}"].value)
                    if val and val.upper() not in ("OTHER FINDINGS", "8.", "8", "NO", "YES") and not re.match(r"^8\.\d+$", val):
                        desc_val = val
                        break

            if desc_val or remark_val:
                item_no = clean_val(ws[f"B{r}"].value) or f"8.{r - 77}"
                findings.append(
                    VisualInspectionFinding(
                        category="Other Findings",
                        item_no=item_no,
                        description=desc_val or remark_val,
                        status="NO",
                        remarks=remark_val or desc_val,
                    )
                )

        return findings

    def _parse_raw_data_sheet(self, ws_raw: Worksheet) -> RawPhotoRanges:
        """Extract IR and DG photo range bounds from RAW DATA sheet."""
        ir_start: int | None = None
        ir_end: int | None = None
        dg_start: int | None = None
        dg_end: int | None = None

        for row in ws_raw.iter_rows(values_only=True):
            row_cells = [str(c).strip() if c is not None else "" for c in row]
            if not row_cells:
                continue

            # 1. Grid table schema (e.g. ['IR', 49, 66] / ['DG', 1715, 1739])
            first_cell = row_cells[0].upper()
            if first_cell in ("IR", "FLIR") and len(row_cells) >= 3:
                if ir_start is None and row_cells[1]:
                    ir_start = parse_int_safe(row_cells[1])
                if ir_end is None and row_cells[2]:
                    ir_end = parse_int_safe(row_cells[2])
            elif first_cell in ("DG", "IMG") and len(row_cells) >= 3:
                if dg_start is None and row_cells[1]:
                    dg_start = parse_int_safe(row_cells[1])
                if dg_end is None and row_cells[2]:
                    dg_end = parse_int_safe(row_cells[2])

            # 2. Label-based schema
            for idx, text in enumerate(row_cells):
                text_upper = text.upper()
                if "IR START" in text_upper or "FLIR START" in text_upper:
                    val = find_next_val(row_cells, idx)
                    parsed = parse_int_safe(val)
                    if parsed is not None:
                        ir_start = parsed
                elif "IR END" in text_upper or "FLIR END" in text_upper:
                    val = find_next_val(row_cells, idx)
                    parsed = parse_int_safe(val)
                    if parsed is not None:
                        ir_end = parsed
                elif "DG START" in text_upper or "IMG START" in text_upper:
                    val = find_next_val(row_cells, idx)
                    parsed = parse_int_safe(val)
                    if parsed is not None:
                        dg_start = parsed
                elif "DG END" in text_upper or "IMG END" in text_upper:
                    val = find_next_val(row_cells, idx)
                    parsed = parse_int_safe(val)
                    if parsed is not None:
                        dg_end = parsed
                elif "IR RANGE" in text_upper or "FLIR RANGE" in text_upper:
                    val = find_next_val(row_cells, idx)
                    s, e = parse_range_val(val)
                    if ir_start is None:
                        ir_start = s
                    if ir_end is None:
                        ir_end = e
                elif "DG RANGE" in text_upper or "IMG RANGE" in text_upper:
                    val = find_next_val(row_cells, idx)
                    s, e = parse_range_val(val)
                    if dg_start is None:
                        dg_start = s
                    if dg_end is None:
                        dg_end = e

        return RawPhotoRanges(
            ir=PhotoRange(start_num=ir_start, end_num=ir_end),
            dg=PhotoRange(start_num=dg_start, end_num=dg_end),
        )
