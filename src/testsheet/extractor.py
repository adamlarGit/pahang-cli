"""Extractor for parsing testsheet Excel workbooks in Pahang CLI."""

from __future__ import annotations

import re
from pathlib import Path
import openpyxl

from src.testsheet.models import PhotoRange, RawPhotoRanges, TestsheetData


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
            ws = None
            if "RAW DATA" in wb.sheetnames:
                ws = wb["RAW DATA"]
            elif "PCE Testsheet" in wb.sheetnames:
                ws = wb["PCE Testsheet"]
            else:
                ws = wb.active

            fl_number = ""
            date_str = date_hint
            station_name = station_hint
            type_code = "PE"
            wo_number = ""

            ir_start: int | None = None
            ir_end: int | None = None
            dg_start: int | None = None
            dg_end: int | None = None

            if ws is not None:
                for row in ws.iter_rows(values_only=True):
                    row_cells = [str(c).strip() if c is not None else "" for c in row]
                    for idx, text in enumerate(row_cells):
                        text_upper = text.upper()

                        if any(k in text_upper for k in ["PE NO", "PE NUMBER", "PE #"]):
                            val = self._find_next_val(row_cells, idx)
                            parsed_pe = self._parse_int_safe(val)
                            if parsed_pe is not None:
                                pe_num = parsed_pe

                        elif any(k in text_upper for k in ["SUBSTATION NAME", "PE NAME", "NAMA PE"]):
                            val = self._find_next_val(row_cells, idx)
                            if val and not any(k in val.upper() for k in ["SUBSTATION", "NAME", "NAMA"]):
                                substation_name = val

                        elif any(k in text_upper for k in ["FL NUMBER", "FUNCTIONAL LOCATION", "FL NO"]):
                            val = self._find_next_val(row_cells, idx)
                            if val and not any(k in val.upper() for k in ["FL", "NUMBER", "LOCATION"]):
                                fl_number = val

                        elif text_upper in ["STATION", "STATION NAME", "STESEN"]:
                            val = self._find_next_val(row_cells, idx)
                            if val and not any(k in val.upper() for k in ["STATION", "NAME", "STESEN"]):
                                station_name = val

                        elif text_upper in ["DATE", "TARIKH", "INSPECTION DATE"]:
                            val = self._find_next_val(row_cells, idx)
                            if val and not any(k in val.upper() for k in ["DATE", "TARIKH"]):
                                date_str = val

                        elif text_upper in ["TYPE", "SUBSTATION TYPE", "JENIS"]:
                            val = self._find_next_val(row_cells, idx)
                            if val and not any(k in val.upper() for k in ["TYPE", "JENIS"]):
                                type_code = val

                        elif text_upper in ["WO", "WORK ORDER", "W.O."]:
                            val = self._find_next_val(row_cells, idx)
                            if val and not any(k in val.upper() for k in ["WO", "WORK", "ORDER"]):
                                wo_number = val

                        elif "IR START" in text_upper or "FLIR START" in text_upper:
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
