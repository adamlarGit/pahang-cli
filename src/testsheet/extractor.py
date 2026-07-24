"""Extractor for parsing testsheet Excel workbooks in Pahang CLI."""

from __future__ import annotations

from datetime import date, datetime
import re
from pathlib import Path
import openpyxl

from src.testsheet.models import PhotoRange, RawPhotoRanges, TestsheetData


def normalize_fl_erms(val: object) -> str:
    """Strip whitespace, handle .0 float suffix from FL ERMS values."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s.replace("\t", "").strip()


def clean_val(val: object) -> str | None:
    """Strip tabs/spaces, return None if empty/dash/NONE."""
    if val is None:
        return None
    s = str(val).replace("\t", "").strip()
    if not s or s in ("-", "None", "NONE", "N/A", "#REF!", "nan"):
        return None
    return s


def is_marked(val: object) -> bool:
    """Checkbox detection — True if cell has a non-negative marker."""
    if val is None:
        return False
    s = str(val).strip().upper()
    return s not in ("", "NONE", "NO", "N/A", "0", "FALSE", "-", "NAN")


def normalize_building_type(val: object) -> str | None:
    """Normalize building type strings to ATTACH, INDOOR, or OUTDOOR."""
    if val is None:
        return None
    s = str(val).strip().upper()
    if not s or s in ("-", "NONE", "N/A"):
        return None
    if "ATTACH" in s:
        return "ATTACH"
    if "INDOOR" in s or "DALAMAN" in s:
        return "INDOOR"
    if "OUTDOOR" in s or "LUARAN" in s:
        return "OUTDOOR"
    return s


def to_excel_date(val: object) -> datetime | None:
    """Parse date from cell value — handles datetime, date, and string formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    s = str(val).strip()
    if not s or s in ("-", "None", "N/A"):
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


class TestsheetExtractor:
    """Extracts metadata and photo range bounds from Pahang testsheet workbooks."""

    def extract_photo_ranges(self, workbook_path: Path | str) -> RawPhotoRanges:
        """Extract IR and DG photo range bounds from testsheet RAW DATA sheet."""
        data = self.extract_testsheet_data(workbook_path)
        return data.photo_ranges

    def extract_testsheet_data(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Parse testsheet workbook to extract TestsheetData and photo ranges."""
        path = Path(workbook_path)
        if not path.exists():
            raise FileNotFoundError(f"Testsheet workbook not found: {path}")

        pe_num = 1
        num_match = re.match(r"^(\d+)", path.name)
        if num_match:
            pe_num = int(num_match.group(1))

        substation_name = path.stem
        if num_match:
            cleaned = re.sub(r"^\d+[\.\-\s_]*", "", path.stem).strip()
            if cleaned:
                substation_name = cleaned

        wb = openpyxl.load_workbook(path, data_only=True)
        try:
            fl_erms = ""
            substation_name_erms = ""
            cycle_1: datetime | None = None

            substation_name_site = ""
            gps_coordinate = ""
            substation_type = ""
            building_type: str | None = None

            fl_number = ""
            date_str = date_hint
            station_name = station_hint
            type_code = "PE"
            wo_number = ""

            ir_start: int | None = None
            ir_end: int | None = None
            dg_start: int | None = None
            dg_end: int | None = None

            # Phase 1: PCE Testsheet (fixed cells)
            if "PCE Testsheet" in wb.sheetnames:
                ws_pce = wb["PCE Testsheet"]
                fl_erms = normalize_fl_erms(ws_pce["W5"].value)
                cleaned_sub_erms = clean_val(ws_pce["C5"].value)
                substation_name_erms = cleaned_sub_erms if cleaned_sub_erms is not None else ""
                cycle_1 = to_excel_date(ws_pce["P4"].value)

            # Phase 2: PCE VI (fixed cells, optional)
            if "PCE VI" in wb.sheetnames:
                ws_vi = wb["PCE VI"]
                cleaned_sub_site = clean_val(ws_vi["C7"].value)
                substation_name_site = cleaned_sub_site if cleaned_sub_site is not None else ""
                cleaned_gps = clean_val(ws_vi["C8"].value)
                gps_coordinate = cleaned_gps if cleaned_gps is not None else ""
                cleaned_type = clean_val(ws_vi["N1"].value)
                substation_type = cleaned_type if cleaned_type is not None else ""

                if is_marked(ws_vi["D9"].value):
                    building_type = normalize_building_type(ws_vi["C9"].value)
                elif is_marked(ws_vi["G9"].value):
                    building_type = normalize_building_type(ws_vi["F9"].value)
                elif is_marked(ws_vi["I9"].value):
                    building_type = normalize_building_type(ws_vi["H9"].value)
                elif is_marked(ws_vi["K9"].value):
                    building_type = normalize_building_type(ws_vi["J9"].value)
                elif is_marked(ws_vi["M9"].value):
                    building_type = normalize_building_type(ws_vi["L9"].value)
                elif is_marked(ws_vi["O9"].value):
                    o_val = ws_vi["P9"].value if ws_vi["P9"].value is not None else ws_vi["N9"].value
                    building_type = normalize_building_type(o_val)

            # Phase 3: RAW DATA sheet (photo range extraction only)
            if "RAW DATA" in wb.sheetnames:
                ws_raw = wb["RAW DATA"]
                for row in ws_raw.iter_rows(values_only=True):
                    row_cells = [str(c).strip() if c is not None else "" for c in row]
                    for idx, text in enumerate(row_cells):
                        text_upper = text.upper()

                        if "IR START" in text_upper or "FLIR START" in text_upper:
                            val = self._find_next_val(row_cells, idx)
                            ir_start = self._parse_int_safe(val)
                        elif "IR END" in text_upper or "FLIR END" in text_upper:
                            val = self._find_next_val(row_cells, idx)
                            ir_end = self._parse_int_safe(val)

                        elif "DG START" in text_upper or "IMG START" in text_upper:
                            val = self._find_next_val(row_cells, idx)
                            dg_start = self._parse_int_safe(val)
                        elif "DG END" in text_upper or "IMG END" in text_upper:
                            val = self._find_next_val(row_cells, idx)
                            dg_end = self._parse_int_safe(val)

                        elif "IR RANGE" in text_upper or "FLIR RANGE" in text_upper or "IR PHOTO" in text_upper:
                            val = self._find_next_val(row_cells, idx)
                            parsed_start, parsed_end = self._parse_range_val(val)
                            if ir_start is None:
                                ir_start = parsed_start
                            if ir_end is None:
                                ir_end = parsed_end
                        elif "DG RANGE" in text_upper or "IMG RANGE" in text_upper or "DG PHOTO" in text_upper:
                            val = self._find_next_val(row_cells, idx)
                            parsed_start, parsed_end = self._parse_range_val(val)
                            if dg_start is None:
                                dg_start = parsed_start
                            if dg_end is None:
                                dg_end = parsed_end

            # Map fixed-cell outputs to existing model fields where appropriate
            if fl_erms:
                fl_number = fl_erms
            if substation_name_erms:
                substation_name = substation_name_erms
            elif substation_name_site:
                substation_name = substation_name_site
            if substation_type:
                type_code = substation_type
            if cycle_1 and not date_str:
                date_str = cycle_1.strftime("%d-%m-%Y")

        finally:
            wb.close()

        photo_ranges = RawPhotoRanges(
            ir=PhotoRange(start_num=ir_start, end_num=ir_end),
            dg=PhotoRange(start_num=dg_start, end_num=dg_end),
        )

        return TestsheetData(
            pe_number=pe_num,
            substation_name=substation_name,
            station_name=station_name,
            date_str=date_str,
            fl_number=fl_number,
            type_code=type_code,
            wo_number=wo_number,
            photo_ranges=photo_ranges,
            fl_erms=fl_erms,
            substation_name_erms=substation_name_erms,
            substation_name_site=substation_name_site,
            gps_coordinate=gps_coordinate,
            substation_type=substation_type,
            building_type=building_type,
            cycle_1=cycle_1,
        )

    def _find_next_val(self, cells: list[str], current_idx: int) -> str:
        """Find the next non-empty string cell value in row after current_idx."""
        for i in range(current_idx + 1, len(cells)):
            val = cells[i].strip()
            if val:
                return val
        return ""

    def _parse_int_safe(self, val: object) -> int | None:
        """Safely convert a cell value or string into an integer."""
        if val is None or val == "":
            return None
        match = re.search(r"(\d+)", str(val))
        if match:
            return int(match.group(1))
        return None

    def _parse_range_val(self, val: str) -> tuple[int | None, int | None]:
        """Parse start and end photo integers from range string."""
        if not val:
            return None, None
        nums = [int(n) for n in re.findall(r"\d+", val)]
        if len(nums) >= 2:
            return nums[0], nums[1]
        if len(nums) == 1:
            return nums[0], nums[0]
        return None, None
