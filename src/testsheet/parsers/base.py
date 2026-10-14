"""Base protocol for testsheet parser strategies."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from src.testsheet.models import RawPhotoRanges, TestsheetData


@runtime_checkable
class TestsheetParserStrategy(Protocol):
    """Protocol interface for voltage-specific testsheet parser strategies."""

    __test__ = False

    def extract_testsheet_data(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Parse testsheet workbook to extract TestsheetData and photo ranges."""
        ...

    def extract_testsheet_metadata(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Fast read-only extraction of header metadata required for TOTAL PE."""
        ...

    def extract_photo_ranges(self, workbook_path: Path | str) -> RawPhotoRanges:
        """Extract IR and DG photo range bounds from testsheet workbook."""
        ...

    def can_handle_sheets(self, sheet_names: Sequence[str]) -> bool:
        """Check if this parser strategy can handle the given sheet names."""
        ...
