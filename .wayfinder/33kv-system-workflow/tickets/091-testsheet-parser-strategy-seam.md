<!-- status: closed -->
Part of #90
Specification: [spec.md](../spec.md)

# 091: feat(33kv-testsheet): TestsheetParserStrategy seam and PceTestsheetParser refactor

**What to build:** Introduce the abstract `TestsheetParserStrategy` interface and refactor all existing 11kV parsing logic from the monolithic `TestsheetExtractor` into `PceTestsheetParser`, with 100% backward compatibility and zero 11kV regressions. Wire the voltage-routed parser factory with strict fail-fast validation.

**Blocked by:** None (can start immediately)

**Status:** closed

## Detailed Design & Architecture

1. **Protocol Interface (`src/testsheet/parsers/base.py`)**:
   - `TestsheetParserStrategy(Protocol)`:
     - `extract_testsheet_data(workbook_path: Path | str, station_hint: str = "", date_hint: str = "") -> TestsheetData`
     - `extract_testsheet_metadata(workbook_path: Path | str, station_hint: str = "", date_hint: str = "") -> TestsheetData`
     - `extract_photo_ranges(workbook_path: Path | str) -> RawPhotoRanges`
     - `can_handle_sheets(sheet_names: Sequence[str]) -> bool`

2. **Shared Cell Normalizers (`src/testsheet/parsers/common.py`)**:
   - Move cell extraction utilities (`clean_val`, `to_excel_date`, `is_marked`, `normalize_building_type`, `parse_photo_numbers`, `parse_secondary_photo`, `normalize_fl_erms`, etc.) into `common.py`.
   - Re-export all of them in `src/testsheet/extractor.py` to maintain 100% backward compatibility with existing imports.

3. **11kV Implementation (`src/testsheet/parsers/pce.py`)**:
   - `PceTestsheetParser`: Implements `TestsheetParserStrategy`, housing all 11kV extraction logic previously in `TestsheetExtractor`.
   - `can_handle_sheets` returns `True` when `"PCE Testsheet"` is present.

4. **33kV Placeholder (`src/testsheet/parsers/ppu.py`)**:
   - `PpuTestsheetParser`: Implements `TestsheetParserStrategy` as a placeholder for Ticket #92.
   - `can_handle_sheets` returns `True` when `"33kV (Main)"` or `"33kV (Extra)"` is present.
   - Parsing methods raise `NotImplementedError("PpuTestsheetParser will be implemented in Ticket #92")`.

5. **Factory & Strict Fail-Fast Policy (`src/testsheet/parsers/factory.py`)**:
   - `get_testsheet_parser(voltage_type: str | None = None, workbook_path: Path | str | None = None) -> TestsheetParserStrategy`:
     - If `voltage_type` is provided:
       - If `voltage_type == "11kV"` $\to$ returns `PceTestsheetParser()`.
       - If `voltage_type == "33kV"` $\to$ returns `PpuTestsheetParser()`.
       - Otherwise $\to$ raises `ValueError(f"Unsupported voltage type: {voltage_type}")`.
     - If `voltage_type is None` and `workbook_path` is provided:
       - Inspect sheet names via read-only openpyxl.
       - If sheets contain `"PCE Testsheet"` $\to$ returns `PceTestsheetParser()`.
       - If sheets contain `"33kV (Main)"` or `"33kV (Extra)"` $\to$ returns `PpuTestsheetParser()`.
       - If neither matches $\to$ fail fast: raise `ValueError(f"Unrecognized testsheet format in {workbook_path}: missing required sheets")`.
     - If neither `voltage_type` nor `workbook_path` is provided $\to$ raise `ValueError("Either voltage_type or workbook_path must be provided to resolve testsheet parser")`.

6. **Backward-Compatible Facade (`src/testsheet/extractor.py`)**:
   - `TestsheetExtractor`: Delegates calls to the strategy resolved via `get_testsheet_parser`.
   - Supports optional `voltage_type` or injected `strategy` in `__init__`.
   - When no `voltage_type` is supplied, dynamically resolves strategy per workbook path via `get_testsheet_parser(workbook_path=path)`.

7. **Repository Seam Integration (`src/testsheet/repository.py`)**:
   - `SubstationTestsheetRepository.__init__`: Accepts optional `voltage_type: str | None = None`, forwarded to `TestsheetExtractor`.

## Acceptance Criteria Checklist

- [x] Create `src/testsheet/parsers/base.py` defining `TestsheetParserStrategy` protocol.
- [x] Create `src/testsheet/parsers/common.py` extracting shared cell parsing helpers and re-export them from `src/testsheet/extractor.py`.
- [x] Create `src/testsheet/parsers/pce.py` with `PceTestsheetParser` implementing all 11kV testsheet extraction.
- [x] Create `src/testsheet/parsers/ppu.py` with placeholder `PpuTestsheetParser` raising `NotImplementedError`.
- [x] Create `src/testsheet/parsers/factory.py` with `get_testsheet_parser` implementing strict fail-fast validation.
- [x] Refactor `TestsheetExtractor` into a delegating facade forwarding to `TestsheetParserStrategy`.
- [x] Update `SubstationTestsheetRepository` to accept optional `voltage_type`.
- [x] Add unit tests in `tests/test_parser_strategy_factory.py` covering voltage routing, sheet inspection, fail-fast on unsupported voltages, and fail-fast on unrecognized sheets.
- [x] Run full test suite to guarantee 0 regressions across all 1,461 tests.
