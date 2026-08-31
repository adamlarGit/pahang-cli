<!-- label: wayfinder:grilling -->
<!-- status: closed -->
<!-- claimed-by: assistant -->
<!-- blocked-by: none -->
# Reverse-engineer METERNAME ↔ testsheet field mapping

## Question

What is the complete mapping between testsheet workbook cells (PCE Testsheet, PCE VI, RAW DATA sheets) and the CSV METERNAME codes used in the MSMS system?

## Context

This is the **hardest design problem** in the Populate Data MSMS workflow. The testsheet workbooks store readings in **named cells across worksheets**, while the CSVs expect them as **flat rows keyed by METERNAME**.

**CSV side** (target — columns to fill):
- `TNBNEWREADING` — the measurement value (numeric for GAUGE, YES/NO for CHARACTERISTIC)
- `TNBNEWREADINGDATE` — timestamp (always paired with TNBNEWREADING)
- `ACTSTART` / `ACTFINISH` — work execution time window
- `TNBCOMMENTS` — defect remarks (sparse)

**CSV row identity** (how to find the right row):
- `WONUM` — work order number (from TOTAL PE via DATA MSMS)
- `METERNAME` — measurement code (e.g., `TH_S11_RMU_REF_PE13R`, `VI11_SG_VDIS_RMU`)
- `TNBLOCATION` — equipment-specific FL path (e.g., `.../11KV/1`, `.../TX/DTX1`, `.../FP/FP1`)
- `METER.DESCRIPTION` — human-readable name (e.g., "PCE: TH RMU Body: Ref Temp")

**Testsheet side** (source — where readings come from):
- `PCE Testsheet` sheet: thermal (TH), ultrasound (US), TEV readings by equipment
- `PCE VI` sheet: visual inspection items (building type, defects, etc.)
- Cell locations defined in `TestsheetExtractor`

**Equipment types** that affect the mapping:
- RMU (Ring Main Unit)
- VCB (Vacuum Circuit Breaker)
- Transformer (TX/DTX)
- Feeder Pillar (FP/LVDB)

## Deliverable

Complete inventory exported to [research/006-metername-mapping-table.md](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/research/006-metername-mapping-table.md).

## Resolution

- **Mapping Mechanics**: The full 348 METERNAME inventory across 18 reference CSVs is categorized by prefix:
  1. `TH_S11_*` / `TH_DTX_*` / `TH_TX_*` / `TH_FP*`: Thermal numeric GAUGE readings mapped from `PCE Testsheet` switchgear/transformer/feeder tables.
  2. `TV_S11_*` / `US_S11_*` / `US_DTX_*`: TEV & Ultrasound numeric GAUGE readings mapped from `PCE Testsheet`.
  3. `VI11_SG_*` / `VI11_TX_*` / `VI11_SUB_*` / `VI11_SEC_*` / `VI11_FP_*`: Visual Inspection CHARACTERISTIC boolean (`YES`/`NO`) readings mapped from `PCE VI` checklist rows (B23:B45).
  4. `BG_ROOM_*`: Room environment GAUGE readings mapped from `PCE Testsheet` cell P6 (TEV), S6 (Humidity), W6 (Ambient Temp).
- **LVDB / Feeder Pillar Column Mapping & Active Gating**:
  - Incomer 1–3 (`TH_FPIN1..3_*`): Columns `D`, `E`, `G` (Row 44/46 config, Row 45/47 cable type).
  - Outgoing 1–10 (`TH_FPOT1..10_*`): Columns `I` through `R` (Row 44/46 config, Row 45/47 cable type).
  - Active check: Non-empty cable insulation type in Row 45 (LVDB 1) or Row 47 (LVDB 2) — e.g., `XLPE`, `PILC`, `ABC`, `BUSBAR`.
  - Inactive / Unused / Spare: Empty/blank cell, `-`, `SPARE`, or `N/A`. Inactive feeder rows remain completely blank (`""`).
  - Thermal Synthesis: For active feeders, synthesize `AVG`, `MAX`, `REF`, and `DEL` based on board average temperature from `R50` (LVDB 1) or `R54` (LVDB 2), with substation jitter and $\Delta T < 1.0^\circ\text{C}$.
- **Substation Variant Suffixes**:
  - `_PE13R`: RMU Switchgear variant
  - `_PE13V`: VCB Switchgear variant
  - `_PE13O`: Outdoor Substation variant
- **Visual Inspection Boolean Convention**:
  - `TNBNEWREADING = YES` represents **Defect Present** (Not Good / Failed check item).
  - `TNBNEWREADING = NO` represents **Normal / Satisfactory Condition**.
- **Missing / Unmapped Cells**:
  - Leave `TNBNEWREADING` and `TNBNEWREADINGDATE` **blank/empty** if the corresponding testsheet cell is empty or marked N/A.
- **Timestamps**:
  - `ACTSTART` = `Date (P4)` + `Time In (P5)`
  - `ACTFINISH` = `Date (P4)` + `Time Out (S5)`
  - `TNBNEWREADINGDATE` = Execution timestamp (ISO-8601 string format).


