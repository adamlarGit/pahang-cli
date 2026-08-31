# Canonical Testsheet Reading Mapper Specification (`src/testsheet/mapper.py`)

## Purpose & Architecture

`src/testsheet/mapper.py` defines the canonical, zero-side-effect mapping dictionary between MSMS **`METERNAME`** codes and exact Excel cell coordinates on `PCE Testsheet`.

It handles:
1. **Shared Sheet Template**: Both RMU and VCB use the **identical** PCE Testsheet physical layout.
2. **Switchgear Panel Slots**: 4 slots per sheet (rows 10-25), each with 4 sub-rows (CABLE, BREAKER, TOP PANEL, PT).
3. **RMU SF6 / MRMU Resolution**: Compartments map to fixed panel slots (CBL1→1, CBL2→2, CBL3→3, FS1→4, FS2→5). Only the CABLE sub-row (offset 0) carries readings. Body goes to Overview (row 26).
4. **VCB Resolution**: Panel index from TNBLOCATION (`/11KV/N`). All 4 sub-rows carry readings per panel (CABLE=0, BREAKER=1, TOP PANEL=2, PT=3).
5. **4-Panel Rollover**: Panels 1-4 on `PCE Testsheet`, Panels 5-8 on `PCE Testsheet (2)`, etc.
6. **Transformer**: TX1 (rows 33-37) and TX2 (rows 38-42), different column layout from switchgear.

---

## 1. Sheet Physical Layout (Shared by RMU and VCB)

### A. Overall Structure

| Section | Rows | Content |
|:---|:---|:---|
| Header/Metadata | 1–6 | Date (P4), PE Name (C5), FLOC (W5), Background readings (row 6) |
| Section Headers | 7–9 | SWITCHGEAR → DETAIL / TEMPERATURE / ULTRASOUND / TEV / REMARK |
| **Panel Slot 1** | **10–13** | 4 sub-rows: CABLE (10), BREAKER (11), TOP PANEL (12), PT (13) |
| **Panel Slot 2** | **14–17** | 4 sub-rows: CABLE (14), BREAKER (15), TOP PANEL (16), PT (17) |
| **Panel Slot 3** | **18–21** | 4 sub-rows: CABLE (18), BREAKER (19), TOP PANEL (20), PT (21) |
| **Panel Slot 4** | **22–25** | 4 sub-rows: CABLE (22), BREAKER (23), TOP PANEL (24), PT (25) |
| **Overview** | **26–29** | Aggregate: CABLE (26), BREAKER (27), TOP PANEL (28), PT (29) |
| LOCAL TRANSFORMER | 30–42 | TX1+TX3 (33-37), TX2+TX4 (38-42) |
| LVDB/FP | 43+ | Feeder Pillar thermal readings |

### B. Switchgear Reading Columns (Rows 10-29)

| Column | Header | Content | METERNAME Metric Suffix |
|:---|:---|:---|:---|
| J | COMP | Compartment label (CABLE, BREAKER, TOP PANEL, PT) | — |
| **K** | **Tmin (°C)** | Minimum/Reference temperature (raw input) | `_REF` |
| **L** | **Tmax (°C)** | Maximum temperature (raw input) | `_MAX` |
| **M** | **ΔT** | `=IF(L#="","",L#-K#)` — computed difference | `_DIF` |
| **N** | **Avg (°C)** | `=IF(L#="","",((L#+K#)/2))` — computed average | `_AVG` |
| O | FILE | IR image file number | — |
| P | REMARKS | Temperature remarks | — |
| **Q** | **dB (US)** | Ultrasound reading | `US_*` |
| R | FILE (US) | Ultrasound file number | — |
| S | TYPE CHAR. (US) | Ultrasound type character | — |
| **T** | **dB (TEV)** | TEV reading | `TV_*` (dB) |
| **U** | **PULSE/CYCLE** | `=IF(T#<>"", 0, "")` — TEV pulse | `TV_*_PUL` |
| V | TYPE CHAR. (TEV) | TEV type character | — |
| W-Y | REMARK | Merged remark field (**NOT Ultrasound**) | — |

### C. Transformer Reading Columns (Rows 33-42)

| Column | Header | Content | METERNAME Metric Suffix |
|:---|:---|:---|:---|
| E | COMP. | Component label (HT CABLE, HT BUSHING, LV CABLE, LV BUSHING, BODY) | — |
| **F** | **Tmin** | Minimum/Reference temperature | `_REF` |
| **G** | **Tmax** | Maximum temperature | `_MAX` |
| **H** | **ΔT** | Temperature difference | `_DIF` |
| **I** | **Avg** | Average temperature | `_AVG` |
| J | FILE | IR image file number | — |
| **K** | **dB (US)** | Ultrasound reading (HT Cable/Bushing only) | `US_DTX_HV_*` |

### D. Transformer Row Layout

| TX | Rows (cols A-L) | HT Cable | HT Bushing | LV Cable | LV Bushing | Body |
|:---|:---|:---|:---|:---|:---|:---|
| **TX1** | 33–37 | **33** | 34 | **35** | 36 | **37** |
| **TX2** | 38–42 | **38** | 39 | **40** | 41 | **42** |
| TX3 | 33–37 (cols M-Y) | *deferred* | *deferred* | *deferred* | *deferred* | *deferred* |
| TX4 | 38–42 (cols M-Y) | *deferred* | *deferred* | *deferred* | *deferred* | *deferred* |

---

## 2. Row Computation Formulas

### A. Switchgear Row (Both RMU and VCB)

```
base_row = 10 + (local_panel_slot - 1) × 4 + compartment_offset
```

Where:
- `local_panel_slot` ∈ {1, 2, 3, 4} (within a single sheet)
- `compartment_offset`: CABLE=0, BREAKER=1, TOP_PANEL=2, PT=3

### B. 4-Panel-Per-Sheet Rollover

```
sheet_index = ⌊(panel_index - 1) / 4⌋ + 1
local_panel_slot = ((panel_index - 1) mod 4) + 1
```

- Sheet 1 (`PCE Testsheet`): panels 1-4
- Sheet 2 (`PCE Testsheet (2)`): panels 5-8
- Sheet 3 (`PCE Testsheet (3)`): panels 9-12

### C. RMU Compartment → Panel Slot Mapping (Fixed)

RMU compartments have a **fixed** slot assignment. All compartments live under a single TNBLOCATION `/11KV/N` (where N is the RMU unit index). The compartment type in the METERNAME determines the slot:

| Compartment | METERNAME Infix | Panel Slot | Row (on local sheet) | Sub-row Used |
|:---|:---|:---|:---|:---|
| Cable Compartment 1 | `RMUCBL1` / `CBL` | 1 | 10 | CABLE (offset 0) only |
| Cable Compartment 2 | `RMUCBL2` / `CBL2` | 2 | 14 | CABLE (offset 0) only |
| Cable Compartment 3 | `RMUCBL3` / `CBL3` | 3 | 18 | CABLE (offset 0) only |
| Fuse Compartment 1 | `RMUFS1` / `FS1` | 4 | 22 | CABLE (offset 0) only |
| Fuse Compartment 2 | `RMUFS2` / `FS2` | 5 | rollover → Sheet 2, row 10 | CABLE (offset 0) only |
| **RMU Body** | `RMU` | **Overview** | **26** | **Avg (N26) only** |

> **RMU constraint**: Only the CABLE sub-row (offset 0) carries readings. BREAKER, TOP PANEL, PT sub-rows are structurally present but always empty for RMU.

> **RMU Body constraint**: Overview row 26 only captures the Avg temperature (N26). Tmin (K26), Tmax (L26), and ΔT (M26) are **not available** on the testsheet — leave these blank/stub in the CSV output.

### D. VCB Panel → Row Mapping (Dynamic)

For VCB, the panel index comes from TNBLOCATION (`/11KV/N` where N = panel number). Each panel uses ALL 4 compartment sub-rows:

| Compartment | METERNAME Infix | Sub-row Offset | Readings Available |
|:---|:---|:---|:---|
| Cable | `CBL` | 0 | IR (K,L,M,N), TEV (T,U), US (Q) |
| Breaker | `BR` | 1 | IR (K,L,M,N), TEV (T,U), US (Q) |
| Top Panel / Busbar | `BB` | 2 | IR (K,L,M,N), TEV (T,U), US (Q) |
| PT | `PT` | 3 | IR (K,L,M,N), TEV (T,U), US (Q) |
| **LV Control** | `LV` | — | **NOT ON TESTSHEET** (stub placeholder) |

---

## 3. Background & Metadata Readings

| METERNAME | Cell | Value Type | Notes |
|:---|:---|:---|:---|
| `BG_ROOM_TV` | `P6` | numeric | TEV background dB — direct numeric value |
| `BG_ROOM_HUM` | `S6` | numeric | Humidity % — merged cell S6:T6 |
| `BG_ROOM_TEM` | `W6` | **text→regex** | Merged W6:Y6, always format `"BACKGROUND TEMP : XX.X °C"`. Extract numeric with flexible whitespace: `r"BACKGROUND\s*TEMP\s*:\s*(\d+\.\d)\s*°?\s*C"`. Always 1 decimal place. |
| `EXECUTION_DATE` | `P4` | date | Merged P4:V4 |
| `TIME_IN` | `P5` | time | Merged P5:Q5 (format: `HHMM` integer, e.g., `1033`) |
| `TIME_OUT` | `S5` | time | Merged S5:V5 (format: `HHMM` integer, e.g., `1048`) |

---

## 4. Complete METERNAME → Cell Mapping Tables

### 4A. RMU SF6 / MRMU Switchgear (`_PE13R`)

All under TNBLOCATION `/11KV/N`. Unit index N determines sheet set. Compartment determines panel slot within that set.

#### RMU Body (Overview, row 26)

| METERNAME | Cell | Notes |
|:---|:---|:---|
| `TH_S11_RMU_AVG_PE13R` | `N26` | Only Avg available on testsheet |
| `TH_S11_RMU_MAX_PE13R` | **STUB** | Not on testsheet — leave CSV blank |
| `TH_S11_RMU_REF_PE13R` | **STUB** | Not on testsheet — leave CSV blank |
| `TH_S11_RMU_DIF_PE13R` | **STUB** | Not on testsheet — leave CSV blank |
| `TV_S11_RMU_PE13R` | `P6` | Body TEV dB = Background TEV (same physical reading) |
| `TV_S11_RMU_PUL_PE13R` | **STUB** | No pulse cell for body TEV — leave CSV blank |
| `US_S11_RMU_PE13R` | **HARDCODED: 0** | No US reading location on testsheet |

#### RMU Cable Compartment 1 (Slot 1, CABLE sub-row, row = 10)

| METERNAME | Column | Cell |
|:---|:---|:---|
| `TH_S11_RMUCBL1_AVG_PE13R` | N | `N10` |
| `TH_S11_RMUCBL1_MAX_PE13R` | L | `L10` |
| `TH_S11_RMUCBL1_REF_PE13R` | K | `K10` |
| `TH_S11_RMUCBL1_DIF_PE13R` | M | `M10` |
| `TV_S11_CBL_PE13R` | T | `T10` |
| `TV_S11_CBL_PUL_PE13R` | U | `U10` |
| `US_S11_CBL_PE13R` | Q | `Q10` |

#### RMU Cable Compartment 2 (Slot 2, CABLE sub-row, row = 14)

| METERNAME | Column | Cell |
|:---|:---|:---|
| `TH_S11_RMUCBL2_AVG_PE13R` | N | `N14` |
| `TH_S11_RMUCBL2_MAX_PE13R` | L | `L14` |
| `TH_S11_RMUCBL2_REF_PE13R` | K | `K14` |
| `TH_S11_RMUCBL2_DIF_PE13R` | M | `M14` |
| `TV_S11_CBL2_PE13R` | T | `T14` |
| `TV_S11_CBL2_PUL_PE13R` | U | `U14` |
| `US_S11_CBL2_PE13R` | Q | `Q14` |

#### RMU Cable Compartment 3 (Slot 3, CABLE sub-row, row = 18)

| METERNAME | Column | Cell |
|:---|:---|:---|
| `TH_S11_RMUCBL3_AVG_PE13R` | N | `N18` |
| `TH_S11_RMUCBL3_MAX_PE13R` | L | `L18` |
| `TH_S11_RMUCBL3_REF_PE13R` | K | `K18` |
| `TH_S11_RMUCBL3_DIF_PE13R` | M | `M18` |
| `TV_S11_CBL3_PE13R` | T | `T18` |
| `TV_S11_CBL3_PUL_PE13R` | U | `U18` |
| `US_S11_CBL3_PE13R` | Q | `Q18` |

#### RMU Fuse Compartment 1 (Slot 4, CABLE sub-row, row = 22)

| METERNAME | Column | Cell |
|:---|:---|:---|
| `TH_S11_RMUFS1_AVG_PE13R` | N | `N22` |
| `TH_S11_RMUFS1_MAX_PE13R` | L | `L22` |
| `TH_S11_RMUFS1_REF_PE13R` | K | `K22` |
| `TH_S11_RMUFS1_DIF_PE13R` | M | `M22` |
| `TV_S11_FS1_PE13R` | T | `T22` |
| `TV_S11_FS1_PUL_PE13R` | U | `U22` |
| `US_S11_FS1_PE13R` | Q | `Q22` |

#### RMU Fuse Compartment 2 (Slot 5 → rollover to Sheet 2, row = 10)

| METERNAME | Column | Cell (on Sheet 2) |
|:---|:---|:---|
| `TH_S11_RMUFS2_AVG_PE13R` | N | `N10` on `PCE Testsheet (2)` |
| `TH_S11_RMUFS2_MAX_PE13R` | L | `L10` on `PCE Testsheet (2)` |
| `TH_S11_RMUFS2_REF_PE13R` | K | `K10` on `PCE Testsheet (2)` |
| `TH_S11_RMUFS2_DIF_PE13R` | M | `M10` on `PCE Testsheet (2)` |
| `TV_S11_FS2_PE13R` | T | `T10` on `PCE Testsheet (2)` |
| `TV_S11_FS2_PUL_PE13R` | U | `U10` on `PCE Testsheet (2)` |
| `US_S11_FS2_PE13R` | Q | `Q10` on `PCE Testsheet (2)` |

#### RMU OIL Variant Stub (`_PE13O`)

| METERNAME | Status |
|:---|:---|
| `TH_S11_RMU_AVG_PE13O` | **STUB** — pending field data |

---

### 4B. VCB Switchgear (`_PE13V` / `_PE13V2`)

Panel index from TNBLOCATION `/11KV/N`. Row computed dynamically:
```
row = 10 + (local_panel_slot - 1) × 4 + compartment_offset
```

Where `local_panel_slot` is after 4-per-sheet rollover on panel index N.

#### VCB Cable Compartment (offset = 0)

| METERNAME | Column | Row Offset | Tech |
|:---|:---|:---|:---|
| `TH_S11_CBL_AVG_PE13V` | N | +0 | Thermal Avg |
| `TH_S11_CBL_MAX_PE13V` | L | +0 | Thermal Max |
| `TH_S11_CBL_REF_PE13V` | K | +0 | Thermal Ref |
| `TH_S11_CBL_DIF_PE13V` | M | +0 | Thermal Diff |
| `TV_S11_CBL_PE13V` | T | +0 | TEV dB |
| `TV_S11_CBL_PUL_PE13V` | U | +0 | TEV Pulse |
| `US_S11_CBL_PE13V` | Q | +0 | Ultrasound dB |

#### VCB Breaker Compartment (offset = 1)

| METERNAME | Column | Row Offset | Tech |
|:---|:---|:---|:---|
| `TH_S11_BR_AVG_PE13V` | N | +1 | Thermal Avg |
| `TH_S11_BR_MAX_PE13V` | L | +1 | Thermal Max |
| `TH_S11_BR_REF_PE13V` | K | +1 | Thermal Ref |
| `TH_S11_BR_DIF_PE13V` | M | +1 | Thermal Diff |
| `TV_S11_BR_PE13V` | T | +1 | TEV dB |
| `TV_S11_BR_PUL_PE13V` | U | +1 | TEV Pulse |
| `US_S11_BR_PE13V` | Q | +1 | Ultrasound dB |

#### VCB Top Panel / Busbar Compartment (offset = 2)

| METERNAME | Column | Row Offset | Tech |
|:---|:---|:---|:---|
| `TH_S11_BB_AVG_PE13V` | N | +2 | Thermal Avg |
| `TH_S11_BB_MAX_PE13V` | L | +2 | Thermal Max |
| `TH_S11_BB_REF_PE13V` | K | +2 | Thermal Ref |
| `TH_S11_BB_DIF_PE13V` | M | +2 | Thermal Diff |
| `TV_S11_BB_PE13V` | T | +2 | TEV dB |
| `TV_S11_BB_PUL_PE13V` | U | +2 | TEV Pulse |
| `US_S11_BB_PE13V` | Q | +2 | Ultrasound dB |

#### VCB PT Compartment (offset = 3)

| METERNAME | Column | Row Offset | Tech |
|:---|:---|:---|:---|
| `TH_S11_PT_AVG_PE13V2` | N | +3 | Thermal Avg |
| `TH_S11_PT_MAX_PE13V2` | L | +3 | Thermal Max |
| `TH_S11_PT_REF_PE13V2` | K | +3 | Thermal Ref |
| `TH_S11_PT_DIF_PE13V2` | M | +3 | Thermal Diff |
| `TV_S11_PT_PE13V` | T | +3 | TEV dB |
| `TV_S11_PT_PUL_PE13V` | U | +3 | TEV Pulse |
| `US_S11_PT_PE13V` | Q | +3 | Ultrasound dB |

#### VCB LV Control Compartment (NOT ON TESTSHEET)

| METERNAME | Status |
|:---|:---|
| `TH_S11_LV_AVG_PE13V` | **STUB** — not on testsheet, leave CSV blank |
| `TH_S11_LV_MAX_PE13V` | **STUB** |
| `TH_S11_LV_REF_PE13V` | **STUB** |
| `TH_S11_LV_DIF_PE13V` | **STUB** |

---

### 4C. Distribution Transformer (RMU: `_PE13R`, VCB: `_PE13V`)

TX index from TNBLOCATION `/TX/DTX1` → TX1 (rows 33-37), `/TX/DTX2` → TX2 (rows 38-42).

**Note**: TX columns are DIFFERENT from switchgear: F(Tmin/REF), G(Tmax/MAX), H(ΔT/DIF), I(Avg), K(US dB).

#### TX HV → HT Cable (TX1: row 33, TX2: row 38)

| METERNAME (RMU) | METERNAME (VCB) | Column | DTX1 Cell | DTX2 Cell |
|:---|:---|:---|:---|:---|
| `TH_DTX_HV_AVG_PE13R` | `TH_DTX_HV_AVG_PE13V` | I | `I33` | `I38` |
| `TH_DTX_HV_MAX_PE13R` | `TH_DTX_HV_MAX_PE13V` | G | `G33` | `G38` |
| `TH_DTX_HV_REF_PE13R` | `TH_DTX_HV_REF_PE13V` | F | `F33` | `F38` |
| `TH_DTX_HV_DIF_PE13R` | `TH_DTX_HV_DIF_PE13V` | H | `H33` | `H38` |
| `US_DTX_HV_PE13R` | `US_DTX_PE13V` | K | `K33` | `K38` |

#### TX LV → LV Cable (TX1: row 35, TX2: row 40)

| METERNAME (RMU) | METERNAME (VCB) | Column | DTX1 Cell | DTX2 Cell |
|:---|:---|:---|:---|:---|
| `TH_DTX_LV_AVG_PE13R` | `TH_DTX_LV_AVG_PE13V` | I | `I35` | `I40` |
| `TH_DTX_LV_MAX_PE13R` | `TH_DTX_LV_MAX_PE13V` | G | `G35` | `G40` |
| `TH_DTX_LV_REF_PE13R` | `TH_DTX_LV_REF_PE13V` | F | `F35` | `F40` |
| `TH_DTX_LV_DIF_PE13R` | `TH_DTX_LV_DIF_PE13V` | H | `H35` | `H40` |

#### TX Body (TX1: row 37, TX2: row 42)

| METERNAME (RMU) | METERNAME (VCB) | Column | DTX1 Cell | DTX2 Cell |
|:---|:---|:---|:---|:---|
| `TH_TX_RMU_AVG_PE13R` | `TH_S11_VCB_AVG_PE13V` | I | `I37` | `I42` |
| `TH_TX_RMU_MAX_PE13R` | `TH_S11_VCB_MAX_PE13V` | G | `G37` | `G42` |
| `TH_TX_RMU_REF_PE13R` | `TH_S11_VCB_REF_PE13V` | F | `F37` | `F42` |
| `TH_TX_RMU_DIF_PE13R` | `TH_S11_VCB_DIF_PE13V` | H | `H37` | `H42` |

> **TX3/TX4**: Deferred to future. Uses columns M-Y on the same row ranges.

---

### 4D. LV Distribution Board / Feeder Pillar (`TNBLOCATION = .../FP/FP1`, `.../FP/FP2`)

The `PCE Testsheet` captures LVDB / Feeder Pillar electrical network topology, cable configurations, and average board temperatures across Rows 44–55:
- **LVDB / FP 1**: Rows 44 (Config / Destination) & 45 (Cable Type / Active Marker) | Thermal Reading Source: **`R50`**
- **LVDB / FP 2**: Rows 46 (Config / Destination) & 47 (Cable Type / Active Marker) | Thermal Reading Source: **`R54`**

#### 1. Incomer & Outgoing Feeder Physical Column Coordinates

| Feeder Channel | Feeder Name / Config | Cable Type (Active Gate) | Target MSMS Meter Base | Thermal Reading Cell |
|---|:---:|:---:|---|:---:|
| **Incomer 1 (IN1)** | `D44` (FP1) / `D46` (FP2) | **`D45`** (FP1) / **`D47`** (FP2) | `TH_FPIN1_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Incomer 2 (IN2)** | `E44` (FP1) / `E46` (FP2) | **`E45`** (FP1) / **`E47`** (FP2) | `TH_FPIN2_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Incomer 3 (IN3)** | `G44` (FP1) / `G46` (FP2) | **`G45`** (FP1) / **`G47`** (FP2) | `TH_FPIN3_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 1 (OT1)** | `I44` (FP1) / `I46` (FP2) | **`I45`** (FP1) / **`I47`** (FP2) | `TH_FPOT1_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 2 (OT2)** | `J44` (FP1) / `J46` (FP2) | **`J45`** (FP1) / **`J47`** (FP2) | `TH_FPOT2_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 3 (OT3)** | `K44` (FP1) / `K46` (FP2) | **`K45`** (FP1) / **`K47`** (FP2) | `TH_FPOT3_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 4 (OT4)** | `L44` (FP1) / `L46` (FP2) | **`L45`** (FP1) / **`L47`** (FP2) | `TH_FPOT4_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 5 (OT5)** | `M44` (FP1) / `M46` (FP2) | **`M45`** (FP1) / **`M47`** (FP2) | `TH_FPOT5_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 6 (OT6)** | `N44` (FP1) / `N46` (FP2) | **`N45`** (FP1) / **`N47`** (FP2) | `TH_FPOT6_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 7 (OT7)** | `O44` (FP1) / `O46` (FP2) | **`O45`** (FP1) / **`O47`** (FP2) | `TH_FPOT7_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 8 (OT8)** | `P44` (FP1) / `P46` (FP2) | **`P45`** (FP1) / **`P47`** (FP2) | `TH_FPOT8_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 9 (OT9)** | `Q44` (FP1) / `Q46` (FP2) | **`Q45`** (FP1) / **`Q47`** (FP2) | `TH_FPOT9_*` | **`R50`** (FP1) / **`R54`** (FP2) |
| **Outgoing 10 (OT10)**| `R44` (FP1) / `R46` (FP2) | **`R45`** (FP1) / **`R47`** (FP2) | `TH_FPOT10_*` | **`R50`** (FP1) / **`R54`** (FP2) |

#### 2. Active Feeder Gating Rules & Thermal Synthesis
- An Incomer or Outgoing feeder is considered **active** if its corresponding cell in Row 45 (for LVDB 1) or Row 47 (for LVDB 2) contains a non-empty cable insulation type (e.g., `XLPE`, `PILC`, `ABC`, `BUSBAR`).
- A feeder is considered **inactive / unused / spare** if the cell is empty/blank, `-`, `SPARE`, or `N/A`.
- If inactive or spare, the target thermal meter in the MSMS CSV remains completely blank (`""`).
- When active, the feeder's 4 thermal readings (`AVG`, `MAX`, `REF`, `DEL`) are synthesized from the base board average temperature at `R50` (LVDB 1) or `R54` (LVDB 2):
  - **Indoor / Attached Substation** (`PE`, `ATTACH`, `INDOOR`): Base jitter $\in [-0.5, +0.5]^\circ\text{C}$.
  - **Outdoor / Compact / PAT Substation** (`CS`, `PAT`, `POLE`, `OUTDOOR`, `_PE13O`): Base jitter $\in [-1.0, +1.0]^\circ\text{C}$.
  - $T_{\text{avg}} = \text{round}(T_{\text{board}} + \text{jitter}, 1)$
  - $\Delta T$ is generated strictly between $0.2^\circ\text{C}$ and $0.8^\circ\text{C}$ (ensuring $\Delta T < 1.0^\circ\text{C}$ always).
  - $T_{\text{ref}} = \text{round}(T_{\text{avg}} - \Delta T / 2, 1)$
  - $T_{\text{max}} = \text{round}(T_{\text{ref}} + \Delta T, 1)$
  - Invariants: $\Delta T = T_{\text{max}} - T_{\text{ref}}$ is exact, and $\Delta T < 1.0^\circ\text{C}$.
- `TH_EARTH_*` and outgoings beyond populated channels remain blank (`""`).

#### 3. Visual Inspection Checks
The 4 characteristic inspection checks under Feeder Pillar (`VI11_FP_PLOCK_RMU`, `VI11_FP_LVDBGUARD_RMU`, `VI11_FP_LINK/FUSE_RMU`, `VI11_FP_TDI_RMU`) are resolved via the structured `QR03 VI` defect list (see Section 4E).

---

### 4E. Visual Inspection Defect Mapping (`QR03 VI` $\to$ `VI11_*`)

Visual Inspection items (`CHARACTERISTIC` meters starting with `VI11_`) are resolved **exclusively from the structured `QR03 VI` defect list** in the ENGR workbooks (via `MasterQr03DefectRepository` in `src/quick_report/defects.py`):

1. **Defect Present**:
   - If a defect record is present in `QR03 VI` matching the inspection check category:
     - `TNBNEWREADING = "YES"`
     - `TNBCOMMENTS = <defect remarks>` (from Column K / `ADDITIONAL REMARKS`)
     - `TNBNEWREADINGDATE = <ISO-8601 execution timestamp>`

2. **No Defect (Satisfactory / Normal)**:
   - If no matching defect is recorded in `QR03 VI`:
     - **Skip row completely**: Do not modify or write to this CSV row at all (preserve existing content untouched).

---

## 5. Resolution Logic Summary

### A. For METERNAME → (sheet_name, cell_coordinate)

1. **Parse TNBLOCATION** → extract `(equipment_category, equipment_index)`:
   - `/11KV/N` → `('11KV', N)` — switchgear panel or RMU unit
   - `/TX/DTXN` → `('TX', N)` — transformer index
   - `/FP/FPN` → `('FP', N)` — feeder pillar index

2. **Determine switchgear type** from METERNAME suffix:
   - `_PE13R` → RMU
   - `_PE13V` / `_PE13V2` → VCB
   - `_PE13O` → OLU (stub)

3. **For VCB**: Panel index = equipment_index from TNBLOCATION.
   - Apply 4-per-sheet rollover → `(sheet_name, local_panel_slot)`
   - Determine compartment offset from METERNAME infix (CBL=0, BR=1, BB=2, PT=3, LV=stub)
   - Row = 10 + (local_panel_slot - 1) × 4 + compartment_offset
   - Column from metric suffix (AVG→N, MAX→L, REF→K, DIF→M, TEV→T, PUL→U, US→Q)

4. **For RMU**: Compartment slot from METERNAME infix (CBL1=1, CBL2=2, CBL3=3, FS1=4, FS2=5, Body=overview).
   - For compartments 1-5: apply 4-per-sheet rollover → `(sheet_name, local_slot)`
   - Row = 10 + (local_slot - 1) × 4 + 0 (always CABLE sub-row)
   - For Body: row = 26, only AVG column (N26). MAX/REF/DIF are stubs.
   - Column from metric suffix (same as VCB)
   - Body TEV dB = P6. Body US = hardcoded 0. Body TEV Pulse = stub.

5. **For Transformer**: DTX index from TNBLOCATION.
   - DTX1 → rows 33-37, DTX2 → rows 38-42
   - HV → HT Cable row (+0), LV → LV Cable row (+2), Body → Body row (+4)
   - Column from metric suffix (AVG→I, MAX→G, REF→F, DIF→H, US→K)

6. **For Background/Metadata**: Fixed cells (P6, S6, W6, P4, P5, S5).

### B. BG_ROOM_TEM Regex Extraction

Cell W6 contains a text string. Extract numeric value with:
```python
import re
match = re.search(r"BACKGROUND\s*TEMP\s*:\s*(\d+\.\d)\s*°?\s*C", cell_value, re.IGNORECASE)
if match:
    temperature = float(match.group(1))
```

---

## 6. Verification Sources

All cell coordinates in this specification were empirically verified against:
- **RMU testsheet**: `066. CENTERPOINT.xlsx` (INDKOM INS24, 12kV, 4 feeders)
- **VCB testsheet**: `064. SSU BUKIT RANGIN.xlsx` (TAMCO VHIH 12kV, 7 panels across 2 sheets)
- **MSMS CSVs**: 18 files, 17,727 rows, covering T1SUB11_RMU (118 WOs), T1SUB11_VCB (3 WOs), T1SUB11_OLU (6 WOs)
