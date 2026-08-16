<!-- label: wayfinder:map -->
# MSMS & Total PE Workflow Refactoring

## Destination

Refactor the MSMS and Total PE workflows into cleanly separated, independently invokable CLI commands following the 6-stage ETL pipeline methodology. Remove all deprecated workflow steps, clearly separate Populate Total PE (testsheet-sourced data) from Update Data MSMS (WO-sourced data), and introduce a new Populate Data MSMS workflow for filling detailed CSV readings.

**Three workflow areas, five independent commands:**

| # | Command | Source → Target | Status |
|---|---|---|---|
| 1 | Populate Total PE | Testsheet packages → TOTAL PE.xlsx | Existing, fine as-is |
| 2 | Consolidate MSMS | PYTHON/MSMS/*.xls → DATA MSMS.xlsx | New |
| 3 | Enrich MSMS | ENGR files → DATA MSMS.xlsx | Refactor |
| 4 | Propagate WO | DATA MSMS.xlsx → TOTAL PE.xlsx (WO only) | Refactor |
| 5a | Ingest MSMS CSVs | RAW DATA/ → TO BE FILLED/ | New |
| 5b | Populate Data MSMS | Testsheet data → fill CSVs in TO BE FILLED/ | New |

## Notes

- Domain: PCE substation inspection data pipeline (Pahang state TNB project)
- All workflows MUST follow [etl_pipeline_refactoring_methodology.md](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/etl_pipeline_refactoring_methodology.md)
- All workflows MUST use project-centric paths via `ProjectEnvironment` / `WorkspaceStorage`
- Domain language defined in [CONTEXT.md](file:///C:/Users/ADAM/Desktop/pahang-cli/CONTEXT.md) — use PahangStation, DailyDateFolder, ENGR Station Code, FL ERMS terminology
- Reference workflow for Location→FL ERMS conversion: [tnb/src/update_data_msms_workflow.py](file:///C:/Users/ADAM/Desktop/tnb/src/update_data_msms_workflow.py)
- Reference filled CSVs: `C:\Users\ADAM\Documents\PO 42289580 - PAHANG - 11kV SECOND CYCLE AZZAD 2026\MSMS\MSMS`
- Reference project structure: `C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD`
- Skills to consult: `/domain-modeling`, `/grilling`, `/codebase-design`

## Decisions so far

- [Audit deprecated update_data_msms code paths](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/research/001-audit-results.md) — Full inventory: 10 functions/methods to REMOVE, 8 to REFACTOR (relocate/centralize), 6 to KEEP as-is. Entire `update_data_msms.py` file deprecated.
- [Audit shared repository interfaces](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/research/008-audit-results.md) — `update_from_engr_and_msms()` deprecated, new `propagate_work_orders()` needed on TotalPeRepo. `update_msms()` refactored to `enrich_from_engr()`. New `consolidate_xls_files()` and `read_data_msms()` on MsmsRepo. 7 new WorkspaceStorage path methods for MSMS dirs.
- [Three workflow areas, independently invokable](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/map.md) — Higher-level orchestration deferred to a separate future wayfinder session. Each workflow is its own CLI command.
- [DATA MSMS.xlsx is the master WO data](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/map.md) — Consolidates scattered .xls files from PYTHON/MSMS/ into one place. Flow: .xls files → DATA MSMS.xlsx → TOTAL PE.xlsx.
- [Location → FL ERMS conversion](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/map.md) — Slash insertion at position 8 (e.g., `CKTN0001XXXX` → `CKTN0001/XXXX`). Same format as reference workflow.
- [ENGR enrichment decoupled from consolidation](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/map.md) — Kept for human verification (cross-check extracted data), but as a separate independently-triggered step. Easier to test and allows coupling to different data sources in the future.
- [ENGR→TOTAL PE path for name/date/type is deprecated](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/map.md) — Populate Total PE now owns all non-WO columns in TOTAL PE.xlsx. The old ENGR-sourced writes of Substation Name, Date, and Type into TOTAL PE are fully removed.
- [populate_total_pe.py is fine as-is](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/map.md) — Only surrounding code (shared repositories, deprecated overlap) needs cleanup.
- [CSV ingestion: RAW DATA → TO BE FILLED with canonical naming](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/map.md) — Client CSVs have unpredictable naming. Normalize to `DD-MM-YYYY_NNN.csv` (index for duplicate dates). Station is a row-level attribute (one CSV can contain multiple PahangStations), not a file-level attribute.
- [Filled CSVs stay in TO BE FILLED after automation](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/map.md) — User manually reviews/rectifies, then manually moves to COMPLETED/. Auto-move deferred to future maturity.
- [Consolidate MSMS 6-stage ETL design](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/002-design-consolidate-msms.md) — 6-stage ETL design: PreflightGuard requires pre-existing DATA MSMS.xlsx & MSMS dir; Extractor uses pd.read_html; Filter dedups and skips existing WOs; Transformer formats FL ERMS (slash at position 8) and builds ConsolidateMsmsPlan; Loader appends rows and moves processed .xls files to COMPLETED/; Auditor uses best-effort policy.
- [Enrich MSMS 6-stage ETL design](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/003-design-enrich-msms.md) — 6-stage ETL design: PreflightGuard requires pre-existing DATA MSMS.xlsx & TOTAL PE.xlsx; Extractor reads DATA MSMS.xlsx & TOTAL PE.xlsx (DataCycle1 sheet); Filter matches exact WO strings and skips non-empty target cells; Transformer maps substation_name_erms, fl_erms, cycle_date, substation_number into EnrichMsmsPlan; Loader updates blank cells in DATA MSMS.xlsx columns D–G in place; Auditor uses best-effort policy and reports match telemetry.
- [Propagate WO 6-stage ETL design](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/004-design-propagate-wo.md) — 6-stage ETL design: PreflightGuard requires pre-existing DATA MSMS.xlsx & TOTAL PE.xlsx (DataCycle1 sheet); Extractor reuses TESTSHEET date discovery; Filter scopes by optional target_date and matches fl_erms to blank WO cells; Transformer maps unique fl_erms to WO in PropagateWoPlan; Loader writes Column F in TOTAL PE.xlsx leaving other columns untouched; Auditor uses best-effort policy and reports matched, already populated, and unmatched telemetry.
- [CSV Ingestion 6-stage ETL design](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/005-design-csv-ingestion.md) — 6-stage ETL design: PreflightGuard requires RAW DATA/ dir with .csv files; Extractor reads RAW DATA/ .csv files and validates headers (WONUM, TNBLOCATION, METERNAME); Filter uses content hash to skip identical duplicates; Transformer uses multi-pattern regex (DD-MM-YYYY, DD.MM.YYYY, DDMMYYYY) to extract date and formats canonical name DD-MM-YYYY_NNN.csv; Loader moves normalized CSVs to TO BE FILLED/; Auditor uses fail-fast policy on unparseable dates.
- [METERNAME ↔ Testsheet mapping reverse-engineering](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/006-metername-mapping.md) — Full 348 METERNAME inventory categorized into research artifact table; VI boolean YES = defect present; blank unmapped cells; ACTSTART/ACTFINISH mapped to Time In/Out. Unblocks Populate Data MSMS pipeline design.
- [Implement Core Foundation: Centralized Normalizers and Canonical Testsheet Mapper](010-implement-normalizers-and-mapper.md) — Implemented `src/core/normalizers.py` (CSV, Excel, Report target normalizers, ISO-8601 formatting, BG temp regex) and `src/testsheet/mapper.py` (`TestsheetReadingMapper` with 4-panel rollover and coordinate resolution for RMU, VCB, TX, FP stubs, and background metadata). 30 unit tests passing.
- [Implement Shared Repository Interfaces & Storage Extensions](011-implement-repositories-and-storage.md) — Implemented `WorkspaceStorage` MSMS path helpers, `MsmsRepo` (`read_data_msms`, `consolidate_xls_files`, `enrich_from_engr`), and `TotalPeRepo.propagate_work_orders()`. 15 unit tests passing.
- [Implement Consolidate MSMS & Enrich MSMS Workflows](012-implement-consolidate-and-enrich.md) — Implemented 6-stage ETL `ConsolidateMsmsWorkflow` and `EnrichMsmsWorkflow` with robust preflights, HTML parsing, deduplication, FL ERMS normalization, and openpyxl persistence. 18 unit tests passing.
- [Implement Propagate Work Orders Workflow](013-implement-propagate-wo.md) — Implemented 6-stage ETL `PropagateWoWorkflow` propagating WO mappings to `TOTAL PE.xlsx` Col F with strict formula and column preservation. 19 unit tests passing.
- [Implement Ingest MSMS CSV & Populate Data MSMS Workflows](014-implement-ingest-and-populate-msms.md) — Implemented 6-stage ETL `IngestMsmsCsvWorkflow` (multi-pattern date parser, SHA-256 dedup, canonical renaming) and `PopulateDataMsmsWorkflow` (testsheet coordinate resolution, QR03 VI defect matching, in-place CSV updates). 13 unit tests passing.
- [Deprecate Legacy update_data_msms, Rewire Workflows to Normalizers & Purge Dead Code](015-deprecate-and-cleanup.md) — Rewired existing workflows to `src/core/normalizers.py`, deleted legacy `update_data_msms.py` and obsolete methods, resolved CLI action bindings, and verified full 270-test regression suite.

## Execution Tickets

1. ~[Implement Core Foundation: Centralized Normalizers and Canonical Testsheet Mapper](010-implement-normalizers-and-mapper.md)~ — **CLOSED**
2. ~[Implement Shared Repository Interfaces & Storage Extensions](011-implement-repositories-and-storage.md)~ — **CLOSED**
3. ~[Implement Consolidate MSMS & Enrich MSMS Workflows](012-implement-consolidate-and-enrich.md)~ — **CLOSED**
4. ~[Implement Propagate Work Orders Workflow](013-implement-propagate-wo.md)~ — **CLOSED**
5. ~[Implement Ingest MSMS CSV & Populate Data MSMS Workflows](014-implement-ingest-and-populate-msms.md)~ — **CLOSED**
6. ~[Deprecate Legacy update_data_msms, Rewire Workflows to Normalizers & Purge Dead Code](015-deprecate-and-cleanup.md)~ — **CLOSED**

## Refactoring Status: COMPLETE

All 6 execution tickets across Waves 1, 2, and 3 have been implemented with test-driven development, validated against specs, and integrated with 100% test pass rate across the full pytest suite (270 passed).

## Not yet specified

*(None — the planning frontier is completely clear and all execution tickets have been materialized.)*

## Out of scope

- **Higher-level orchestration / workflow chaining** — Explicitly deferred to a separate future wayfinder session per user decision.
- **CLI command interface design** — Deferred to orchestration session.
- **Auto-move to COMPLETED/ folder** — Future maturity feature, not part of this refactoring.
