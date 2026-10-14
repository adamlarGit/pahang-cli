# Specification: 33kV System End-to-End Workflow Expansion

## Problem Statement

The Pahang CLI was originally designed and optimized for 11kV distribution network projects (PCE / PE). The project has now expanded to include 33kV sub-transmission and distribution projects (Contract PO 42394550 - THUNDER). 

While the fundamental objectives of the CLI workflows remain consistent—extracting inspection facts, synchronizing master engineering sheets, populating census records, sorting raw field evidence, compiling reports, and submitting client deliverable packages—the physical input structures and asset topologies for 33kV differ substantially:
1. **Testsheet Structure**: 11kV uses `PCE Testsheet` and `PCE VI`. In 33kV, substations (PMU, PPU, SSU) house both 33kV and stepped-down 11kV switchgear lineups across separate sheets (`33kV (Main)`, `33kV (Extra)`, `11kV (Main)`, `11kV (Extra)`), alongside dedicated `TX` (transformers) and `Visual Inspec.` / `Visual Inspection` sheets.
2. **Switchgear Panel Layout**: 11kV switchgear panels have 4 sub-rows (Cable, Breaker, Top Panel, PT). The 33kV testsheet has 6 physical sub-rows (`BREAKER`, `CABLE `, `BUSBAR (TOP)`, `PT COMPARTMENT`, `CABLE ENTRY`, `LINK BOX`), and captures the 7th compartment (`SECONDARY COMPARTMENT` / `SECONDARY PANEL`) as an annotated entry in Column Q (`SP: <photo_num>`).
3. **Master ENGR Workbooks**: 11kV splits CBA records across per-district files under contract 750-36 (`ENGR-750-36-CBA-{STATION}-{YEAR}.xlsx`). 33kV operates under contract 750-39 with a single statewide workbook (`ENGR-750-39 -CBA-PAHANG - {YEAR}.xlsx`) where the `QR02 CBA` sheet has a shifted column layout (Columns G–R, tracking Cycles 1–4, without GPS, Site Name, or Building Type columns).
4. **Master Census (TOTAL PE)**: 33kV tracks all PPU, PMU, and SSU installations in `PYTHON/TOTAL PE.xlsx` (`DataCycle1` sheet: `PE NO`, `FL NUMBER`, `SUBSTATION NAME`, `DATE`, `TYPE`, `WO`).
5. **Substation Condition Deliverables**: 11kV condition pages reflect distribution substations (`1 TX 1 FP`, `COMPACT SUBSTATION`). 33kV substations represent complex multi-voltage facilities requiring condition photo sets for 33kV switchgear, 11kV switchgear, power transformers, cable cellars, control panels, and Neutral Earthing Resistors (NER).
6. **MSMS Job Plan & Meters**: 33kV operates under Maximo job plan `T1SUB33` (`TIER 1-ONLINE CONDITION ASSESMENT`) with specialized meters (`VI_NER_EARTH`, `VI_NER_BAR`, `VI_FCBL_SPPRT`, `VI_FCBL_SEAL`) requiring 33kV `TestsheetReadingMapper` resolution.
7. **Full Report Multi-Part Assembly**: Substations contain large multi-bay VCB and GIS switchgear lineups and high-capacity Power Transformers, requiring `MultiPartPartitionPolicy` (ADR 0005) chunking to prevent ActiveX memory exhaustion.

Without a unified voltage-polymorphic architectural expansion across all 14 actions, running 33kV projects either fails outright, corrupts master workbooks, or requires ongoing fragmented refactoring.

---

## Solution

Introduce a unified, voltage-aware architecture across Pahang CLI that provides seamless support for all 14 Project Workflow actions for 33kV projects while preserving 100% backward compatibility for 11kV workflows:
1. **Unified Menu & Voltage Seam**: Maintain the identical 14-action menu in `src/project_workflow_actions.py`, routing parsing and processing strategies via `ProjectEnvironment.voltage_type` (`"33kV"` vs `"11kV"`).
2. **Testsheet Parser Strategy**: Establish abstract `TestsheetParserStrategy` interface, retaining `PceTestsheetParser` for 11kV and adding `PpuTestsheetParser` to parse 33kV multi-sheet workbooks, metadata (`D6` Name, `D7` FL, `D8` Date), 6-compartment switchgear panels, Column Q `SP:` secondary panels, and power transformer inventories.
3. **Master ENGR 750-39 Adapter**: Add statewide contract 750-39 path resolution and introduce `Qr02Cba33kVTransaction` to safely read and update Columns G–R without corrupting neighboring cells.
4. **Adaptive Raw Material & US+TEV Ingestion**: Update folder stem parsing and acoustic survey archive discovery to handle PPU/PMU/SSU naming and multi-board cubicles.
5. **Dedicated 33kV Quick Report Generation**: Implement `PpuSubstationConditionPairBuilderPolicy` to generate accurate 2-column condition pages for PPU/SSU equipment, alongside CBM and VI defect detail pages tailored to 33kV assets.
6. **Multi-Sheet Deliverable Post-Processing**: Expand pre-flight validation, landscape testsheet COM export across active inspection sheets with programmatic per-sheet PageSetup (Landscape A4 1mm margins for Switchgear/TX; Portrait A4 standard margins for VI; strictly excluding RAW DATA), signature placeholder sanitization, diagonal blanking, and deliverable PDF compilation.
7. **TOTAL PE Census Synchronization**: Ingest 33kV testsheet packages and upsert `DataCycle1` records in `PYTHON/TOTAL PE.xlsx`.
8. **WhatsApp Daily Reporting**: Generate daily WhatsApp reports in `PYTHON/WHATSAPP/` from 33kV Quick Reports and `TOTAL PE.xlsx`.
9. **MSMS T1SUB33 Pipeline**: Consolidate Maximo work orders, propagate WONUMs to `TOTAL PE.xlsx`, ingest CSVs, and map testsheet readings to `T1SUB33` Maximo meters via `TestsheetReadingMapper`.
10. **Full Report Multi-Part Assembly**: Apply `MultiPartPartitionPolicy` for dual-voltage VCB/GIS cubicles and Power Transformers, compiling modular Word chunks and stitching them with the signed testsheet PDF into the canonical deliverable `<STEM>.pdf`.

---

## User Stories

1. As a CLI operator running a 33kV project, I want the CLI to automatically detect the active project voltage rating (`33kV`), so that all 14 workflows execute with 33kV rules without requiring manual flag toggling.
2. As a CLI operator running an 11kV project, I want all existing 11kV workflows to run with zero regressions, so that current operational routines remain completely undisturbed.
3. As a data engineer, I want the testsheet parser to parse both `33kV (Main)`/`Extra` and `11kV (Main)`/`Extra` sheets from a single 33kV workbook, so that all switchgear lineups within a PPU or PMU are captured in the domain model.
4. As a reliability engineer, I want the parser to extract all 6 physical sub-rows per switchgear panel (`BREAKER`, `CABLE`, `BUSBAR (TOP)`, `PT COMPARTMENT`, `CABLE ENTRY`, `LINK BOX`), so that measurement and thermal readings are attributed to the exact physical compartment.
5. As an inspector, I want the parser to detect `SP: <photo_num>` in Column Q remarks and record it as `SECONDARY COMPARTMENT` (`SECONDARY PANEL`), so that secondary panel thermography is captured without modifying the client's Excel sheet layout.
6. As an asset manager, I want the parser to extract transformers from the `TX` sheet and categorize units $\ge$ 5 MVA as Power Transformers (including Marshalling Kiosk, Conservator Tank, Body, and Cooling Fins), so that high-voltage auxiliary components are fully documented.
7. As an asset manager, I want the parser to categorize transformers between 100 kVA and 1000 kVA as Local / Auxiliary Transformers, so that station service units follow standard distribution reporting rules.
8. As a CLI operator running `update-qr02-cba`, I want the workflow to resolve the statewide `ENGR-750-39 -CBA-PAHANG - {YEAR}.xlsx` workbook for 33kV projects, so that updates are written to the correct contract file without station code lookups.
9. As a data engineer, I want the QR02 CBA update engine to write into Columns G through R for 33kV projects, so that cycle inspection dates and vendor codes are recorded in the correct columns without corrupting neighboring cells.
10. As a CLI operator running raw material sorting, I want the workflow to parse 33kV substation directory names (e.g., `01. PPU APMM 33-11kV (VI)`, `08. PMU GBID 275-132-33-11kV`), so that IR and DG photos are correctly organized into raw data folders.
11. As a CLI operator running `quick-report`, I want the document generator to assemble condition pages for 33kV substations with appropriate PPU/SSU photo placeholders (33kV Switchgear, 11kV Switchgear, Transformers 1 & 2, Cable Cellars, Control Panels, and NER), so that reports match on-site physical assets.
12. As a quality engineer, I want Quick Report CBM defect detail pages to support both 33kV and 11kV switchgear panels, so that diagnostic defect callouts display the proper voltage and feeder labels.
13. As a report reviewer, I want Quick Report VI defect detail pages to reflect the 33kV visual inspection checklist findings, so that all structural and electrical anomalies are clearly visible.
14. As a CLI operator running `post-processing`, I want pre-flight validation to recognize 33kV naming stems and multi-sheet testsheet workbooks, so that integrity checks pass before COM export starts.
15. As a document generator, I want Excel COM export for 33kV testsheets to enforce per-sheet PageSetup (Landscape A4 1mm margins for Switchgear/TX; Portrait A4 standard margins for VI; RAW DATA excluded), so that client deliverable PDFs are compact, standardized, and legible.
16. As a deliverable manager, I want testsheet signature sanitization to replace or remove `{{signvendor}}` and `{{signtnb}}` placeholders across all active 33kV sheets.
17. As an operator compiling final client deliverables, I want the post-processing pipeline to merge the Quick Report PDF and signed testsheet PDF into a single consolidated `<STEM>.pdf`.
18. As a data engineer, I want `populate-total-pe` to update `TOTAL PE.xlsx` (`DataCycle1`) with 33kV testsheet metadata without corrupting formulas.
19. As a project manager, I want `whatsapp` to compile daily WhatsApp reports for 33kV inspections matching `TOTAL PE.xlsx` records.
20. As a field coordinator, I want the MSMS suite to consolidate work orders, propagate WONUMs to `TOTAL PE.xlsx`, ingest CSVs, and map testsheet readings to `T1SUB33` Maximo meters.
21. As a deliverable engineer, I want Full Report generation to partition 33kV substations via `MultiPartPartitionPolicy` (Part 01 Summary, Bay Chunks, TX & Condition Chunk) and stitch them with testsheet PDFs into `<STEM>.pdf` without ActiveX memory crashes.

---

## Implementation Decisions

### Decision 1: Voltage-Aware Seam via `TestsheetParserStrategy`
- Abstract the testsheet parsing boundary behind a formal `TestsheetParserStrategy` interface.
- Implement `PceTestsheetParser` for 11kV projects (preserving existing `PCE Testsheet` / `PCE VI` parsing).
- Implement `PpuTestsheetParser` for 33kV projects, parsing multi-sheet workbooks:
  - `33kV (Main)`, `33kV (Extra)`, `33kV (Extra) (2)`
  - `11kV (Main)`, `11kV (Extra)`, `11kV (Extra) (2)`, `11kV (Extra) (3)`
  - `TX`
  - `Visual Inspec.` / `Visual Inspection`
  - `RAW DATA` (bounds only, skipped during rendering)
- Dispatch the parser via `TestsheetRepository` checking `environment.voltage_type == "33kV"`. If unconfigured, inspect sheet names to dynamically select the parser strategy.

### Decision 2: 6-Row Switchgear Panel Model with Column Q Secondary Panel Detection
- Switchgear panels on 33kV sheets have a fixed stride of 6 physical sub-rows:
  - `BREAKER`, `CABLE `, `BUSBAR (TOP)`, `PT COMPARTMENT`, `CABLE ENTRY`, `LINK BOX`.
- Map these physical sub-rows to canonical compartment readings.
- Inspect Column Q (`REMARKS`) across panel rows. If text matches pattern `SP:\s*(\d+)`, extract the IR photo number and record an active `SECONDARY COMPARTMENT` on the panel spec.

### Decision 3: Transformer Ingestion & Power Transformer Classification
- On the `TX` sheet, extract up to 4 Power Transformers (`TX 1`..`TX 4`) and `LOCAL TX`.
- Categorize transformers by rating:
  - Rating $\ge 5$ MVA: Classified as `PowerTransformerSpec`, capturing HV/LV cable thermals, ultrasound, Marshalling Kiosk, Conservator Tank, Body, and Cooling Fins.
  - Rating $100\text{ kVA} - 1000\text{ kVA}$: Classified as standard distribution `TransformerSpec` (cable terminations and baseline readings).

### Decision 4: Contract 750-39 Master ENGR Storage & QR02 Transaction
- In `WorkspaceStorage`, update `get_engr_cba_path()`: for 33kV projects, resolve directly to `ENGR-750-39 -CBA-PAHANG - {YEAR}.xlsx` (or scan for `*750-39*.xlsx` in `PYTHON/ENGR FROM DRIVE/`), bypassing station abbreviation lookups.
- Implement `Qr02Cba33kVTransaction` in `src/master/qr02.py`:
  - Target columns: Col G (`FL`), Col H (`Substation Name`), Col I (`Type`), Col J (`System`), Col K/M/O/Q (`Cycle 1..4 Date`), Col L/N/P/R (`Cycle 1..4 Vendor`).
  - GPS, Site Name, and Building Type columns are intentionally not written.

### Decision 5: Dedicated 33kV Substation Condition Policy (`PpuSubstationConditionPairBuilderPolicy`)
- In `src/quick_report/substation_condition.py`, implement condition photo pairing rules for PPU/SSU stations:
  - `SWITCHGEAR 33kV` & `SWITCHGEAR 33kV NAMEPLATE`
  - `SWITCHGEAR 11kV` & `SWITCHGEAR 11kV NAMEPLATE`
  - `TRANSFORMER 1` & `TRANSFORMER 1 NAMEPLATE`
  - `TRANSFORMER 2` & `TRANSFORMER 2 NAMEPLATE`
  - `33kV CABLE CELLAR` & `11kV CABLE CELLAR`
  - `CONTROL PANEL` & `NER` (Neutral Earthing Resistor)
- Gracefully collapse or omit empty slots if an asset category is absent.

### Decision 6: Programmatic Per-Sheet PageSetup & Post-Processing Export
- Update Excel COM conversion in `src/postprocessing/converters.py` (`ComDocumentConverter`):
  - Switchgear & TX sheets: Landscape A4, 1mm tight margins (`0.039"`), fit-to-1-page wide.
  - Visual Inspection: Portrait A4, standard margins (`0.25"/0.75"`).
  - Strictly exclude `RAW DATA` and unpopulated extra sheets.
- Update `src/workflows/diagonal_borders.py` with 33kV scan ranges:
  - Switchgear: Rows 15–62, Cols C–U.
  - TX: Rows 7–70, Cols C–AB.
  - Visual Inspection: strictly unslashed.

### Decision 7: Multi-Part Partitioning for 33kV Full Reports
- Implement `MultiPartPartitionPolicy` (ADR 0005) for 33kV VCB and GIS switchgear:
  - Chunk 1 (`Part 01 - Summary`): Front page, Executive Summary Census, Visual Defect Summary, Switchgear Overview pages.
  - Chunks 2..(N+1) (`Part {XX:02d} - Panel {no} ({name})`): Individual bay scan pages plus inline CBM defect pages across both 33kV and 11kV lineups.
  - Chunk N+2 (`Part {N+2:02d} - TX and Condition`): Power Transformers (HV/LV sides, auxiliary thermals), Local TX, battery bank, condition pages, visual defects, sticker page.
- Stage 2 Post-Processing batch converts parts to PDF, merges them in sequence, and appends the testsheet PDF into the canonical deliverable `<STEM>.pdf`.
- Field-verified manual reports in `FULL REPORT/` serve as visual benchmarks for layout and content.

---

## Testing Decisions

- **Black-box behavior testing**: Test parser strategies and workflow steps exclusively via public interfaces (`TestsheetRepository.get_package()`, `QuickReportWorkflow.generate()`, `UpdateQr02CbaWorkflow.run()`, `FullReportWorkflow.generate()`), never by inspecting internal private methods.
- **Synthetic Excel & Docx Fixtures**: Construct minimal openpyxl test workbooks reproducing 33kV layouts (`33kV (Main)`, `TX`, `Visual Inspec.`, `RAW DATA`) and synthetic contract 750-39 workbooks.
- **Regression Protection**: Run the complete existing 11kV test suite to verify 0 regressions across 11kV testsheets, master sheets, and report generation.

---

## Out of Scope

<!-- Out of scope: work ruled beyond the destination; closed, never graduates -->
- Modifying client-supplied Excel testsheet templates or row/column definitions.
- Supporting voltage classes beyond 11kV and 33kV (e.g. 132kV, 275kV).
- Older 33kV sheet naming convention (`33kV (1)`, `PMU-PPU-SSU Test Sheet (Main)`, `PMU-PPU-SSU Visual Inspec.`).

---

## Further Notes

- The 33kV project directory is: `C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER`.
- Active project key in `.cli_config.json`: `thunder_cycle_4_2026_4`.
