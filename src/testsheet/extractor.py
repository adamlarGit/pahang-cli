"""Extractor for parsing testsheet Excel workbooks in Pahang CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.testsheet.models import (
    BatteryBankSpec,
    FireExtinguisherSpec,
    LVDBFeederSpec,
    LVDBSpec,
    PhotoRange,
    RawPhotoRanges,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
    ThermalReadingSpec,
    TransformerSpec,
)
from src.testsheet.parsers.base import TestsheetParserStrategy
from src.testsheet.parsers.common import (
    clean_val,
    is_marked,
    normalize_building_type,
    normalize_fl_erms,
    parse_photo_numbers,
    parse_secondary_photo,
    to_excel_date,
)
from src.testsheet.parsers.factory import get_testsheet_parser
from src.testsheet.parsers.pce import PceTestsheetParser

__all__ = [
    "clean_val",
    "is_marked",
    "normalize_building_type",
    "normalize_fl_erms",
    "parse_photo_numbers",
    "parse_secondary_photo",
    "to_excel_date",
    "TestsheetExtractor",
]


class TestsheetExtractor:
    """Facade delegating testsheet extraction to voltage-specific parser strategies."""

    __test__ = False

    def __init__(
        self,
        voltage_type: str | None = None,
        strategy: TestsheetParserStrategy | None = None,
    ) -> None:
        self.voltage_type = voltage_type
        self.strategy = strategy

    def _get_strategy(self, workbook_path: Path | str) -> TestsheetParserStrategy:
        if self.strategy is not None:
            return self.strategy
        return get_testsheet_parser(
            voltage_type=self.voltage_type, workbook_path=workbook_path
        )

    def extract_photo_ranges(self, workbook_path: Path | str) -> RawPhotoRanges:
        """Extract IR and DG photo range bounds from testsheet RAW DATA sheet."""
        strategy = self._get_strategy(workbook_path)
        return strategy.extract_photo_ranges(workbook_path)

    def extract_testsheet_metadata(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Fast read-only extraction of header metadata required for TOTAL PE."""
        strategy = self._get_strategy(workbook_path)
        return strategy.extract_testsheet_metadata(
            workbook_path, station_hint=station_hint, date_hint=date_hint
        )

    def extract_testsheet_data(
        self,
        workbook_path: Path | str,
        station_hint: str = "",
        date_hint: str = "",
    ) -> TestsheetData:
        """Parse testsheet workbook to extract TestsheetData and photo ranges."""
        strategy = self._get_strategy(workbook_path)
        return strategy.extract_testsheet_data(
            workbook_path, station_hint=station_hint, date_hint=date_hint
        )

    def __getattr__(self, name: str) -> Any:
        """Backward compatibility delegate for tests inspecting extractor methods."""
        if self.strategy is not None:
            return getattr(self.strategy, name)
        if self.voltage_type is not None:
            target = get_testsheet_parser(voltage_type=self.voltage_type)
            return getattr(target, name)
        return getattr(PceTestsheetParser(), name)
