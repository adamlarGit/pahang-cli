"""Factory for resolving testsheet parser strategies."""

from __future__ import annotations

from pathlib import Path
import warnings
import openpyxl

from src.testsheet.parsers.base import TestsheetParserStrategy
from src.testsheet.parsers.pce import PceTestsheetParser
from src.testsheet.parsers.ppu import PpuTestsheetParser


def get_testsheet_parser(
    voltage_type: str | None = None,
    workbook_path: Path | str | None = None,
) -> TestsheetParserStrategy:
    """Resolve and return appropriate TestsheetParserStrategy.

    Follows strict fail-fast validation:
    1. If voltage_type is provided: routes to 11kV or 33kV, or raises ValueError.
    2. If voltage_type is None and workbook_path is provided: inspects sheet names.
    3. If neither is provided: raises ValueError.
    """
    if voltage_type is not None:
        if voltage_type == "11kV":
            return PceTestsheetParser()
        elif voltage_type == "33kV":
            return PpuTestsheetParser()
        else:
            raise ValueError(f"Unsupported voltage type: {voltage_type}")

    if workbook_path is not None:
        path = Path(workbook_path)
        if not path.exists():
            raise FileNotFoundError(f"Testsheet workbook not found: {path}")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            try:
                sheet_names = wb.sheetnames
            finally:
                wb.close()

        # 1. 33kV sheets take priority
        ppu_parser = PpuTestsheetParser()
        if ppu_parser.can_handle_sheets(sheet_names):
            return ppu_parser

        # 2. 11kV PCE sheets
        pce_parser = PceTestsheetParser()
        if pce_parser.can_handle_sheets(sheet_names):
            return pce_parser

        # 3. 11kV backward-compatibility fallback for synthetic/legacy workbooks with RAW DATA only
        if "RAW DATA" in sheet_names:
            return pce_parser

        raise ValueError(
            f"Unrecognized testsheet format in {workbook_path}: missing required sheets"
        )

    raise ValueError(
        "Either voltage_type or workbook_path must be provided to resolve testsheet parser"
    )
