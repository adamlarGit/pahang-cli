"""33kV PPU testsheet parser placeholder."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Sequence

from src.testsheet.models import RawPhotoRanges, TestsheetData
from src.testsheet.parsers.base import TestsheetParserStrategy


class PpuTestsheetParser(TestsheetParserStrategy):
    """Parser strategy for 33kV PPU testsheets (Ticket #92 implementation placeholder)."""

    __test__ = False
    HANDLED_SHEETS: ClassVar[tuple[str, ...]] = ("33kV (Main)", "33kV (Extra)")

    def extract_testsheet_data(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Parse 33kV testsheet workbook."""
        raise NotImplementedError("PpuTestsheetParser will be implemented in Ticket #92")

    def extract_testsheet_metadata(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Fast read-only extraction of header metadata required for TOTAL PE."""
        raise NotImplementedError("PpuTestsheetParser will be implemented in Ticket #92")

    def extract_photo_ranges(self, workbook_path: Path | str) -> RawPhotoRanges:
        """Extract IR and DG photo range bounds from 33kV testsheet."""
        raise NotImplementedError("PpuTestsheetParser will be implemented in Ticket #92")

    def can_handle_sheets(self, sheet_names: Sequence[str]) -> bool:
        """Return True if sheets contain 33kV (Main) or 33kV (Extra)."""
        return any(s in sheet_names for s in self.HANDLED_SHEETS)
