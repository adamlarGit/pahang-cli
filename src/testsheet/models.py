"""Domain models for testsheets and photo ranges in Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PhotoRange:
    """Numerical bounds (start and end photo numbers) for raw photo matching."""

    start_num: int | None = None
    end_num: int | None = None

    def contains(self, photo_num: int) -> bool:
        """Return True if photo_num is within bounds inclusive (supporting single photos)."""
        if self.start_num is None and self.end_num is None:
            return False
        start = self.start_num if self.start_num is not None else self.end_num
        end = self.end_num if self.end_num is not None else self.start_num
        if start is None or end is None:
            return False
        min_val = min(start, end)
        max_val = max(start, end)
        return min_val <= photo_num <= max_val

    @property
    def is_valid(self) -> bool:
        """Return True if at least start_num or end_num is specified."""
        return self.start_num is not None or self.end_num is not None


@dataclass(frozen=True)
class RawPhotoRanges:
    """Container for IR (Infrared) and DG (Digital) photo range bounds."""

    ir: PhotoRange = PhotoRange()
    dg: PhotoRange = PhotoRange()


@dataclass(frozen=True)
class TestsheetData:
    """Extracted data from a substation testsheet Excel workbook."""

    __test__ = False

    pe_number: int
    substation_name: str
    station_name: str = ""
    date_str: str = ""
    fl_number: str = ""
    type_code: str = "PE"
    wo_number: str = ""
    photo_ranges: RawPhotoRanges = RawPhotoRanges()


@dataclass(frozen=True)
class SubstationTestsheetPackage:
    """Discovered testsheet workbook and unsorted raw data context package."""

    __test__ = False

    testsheet_path: Path
    unsorted_raw_data_dir: Path
    station: str
    month: str
    date_str: str
    pe_num: int
    data: TestsheetData | None = None
