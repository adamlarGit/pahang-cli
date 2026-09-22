# Switchgear Topology Engine — Settled Design Decisions & Technical Architecture

Produced from a grilling and domain-modeling session (2026-09-22) comparing and synthesizing two candidate plans:
- `.scratch/dynamic-vcb-and-battery/` — 4-layer pipeline with per-bay dynamic resolution
- `.scratch/switchgear-archetype/` — 5-archetype immutable profile lookup

Neither plan worked as-is. The settled design is a **hybrid hierarchical topology engine**:
1. **Board Level (Macro Archetype & VoltageClass)**: Classifies switchboard into physical hardware archetypes controlling board-level overviews, busbar geometries, heater defaults, and base panel blueprints.
2. **Bay Level (Dynamic Bay Role & Presence Gates)**: Evaluates bay roles, applies empirical presence gates (`PT` on standard bays, pure photo-presence `SECONDARY` on transition bays), and resolves exact compartment name tuples.
3. **Decoupled Downstream**: Photo-to-compartment mapping with strict zero-fallback and presentation/contract modality gating are cleanly decoupled from topology resolution.

---

## 1. Architecture: Two-Phase Resolution Pipeline

```
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 1: CLASSIFY (Executed once per switchgear board lineup)          │
│ Input:  (switchgear_type, manufacturer, model, rating)                 │
│ Output: SwitchgearArchetype + VoltageClass + overview_compartments     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 2: RESOLVE (Executed once per bay/panel)                         │
│ Input:  (archetype, bay_role, sub_row_evidence)                        │
│ Output: tuple[str, ...] (final compartment name strings)               │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Downstream Consumers (Isolated from Topology Engine)                   │
│ - Scan Adapter: 1-to-1 photo pairing with strict Zero-Fallback        │
│ - Census Builder: Executive Summary inventory & severity shading       │
│ - Contract Scope: Modality capability filtering (IR, US, TEV, VI)      │
└────────────────────────────────────────────────────────────────────────┘
```

- **Phase 1 is stable across the board**: Drives board metadata, overviews (`swg-overview.docx`), and Executive Summary group headers.
- **Phase 2 is data-driven per bay**: Evaluates testsheet sub-row evidence to emit only physically present compartments.
- **Clean Seam**: The engine returns **compartment name strings only** (`tuple[str, ...]`). It has zero dependencies on Word COM, filesystem paths, or image files.

### Synthesis of Candidate Plans

| Concept | Source Plan | Settled Decision & Rationale |
|---|---|---|
| **Archetype Classification** | `switchgear-archetype` | Kept. Renamed members to a physical topology axis rather than manufacturer brand names. |
| **Dynamic Bay Gates** | `dynamic-vcb-and-battery` | Refined. Empirical PT gate kept; SECONDARY made unconditional on standard/bus bays (heater current gate omitted); transition bays use pure photo presence. |
| **VoltageClass** | `dynamic-vcb-and-battery` | Kept as a first-class input/output seam. 11kV implemented now; 33kV dual busbar designed as clean seam. |
| **Overview Geometry** | `switchgear-archetype` | Enhanced. Fixed VCB to have 3 distinct overviews (`FRONT`, `REAR`, `TOP`); accurately resolved INDKOM INS24 (`TOP`) and TAMCO/LUCY (`BOTTOM`). |
| **Sub-Row Photo Extraction** | `dynamic-vcb-and-battery` | Kept. Sub-row photos parsed directly from 4-row testsheet blocks (`r..r+3`, Col `P`). |
| **Strict Zero-Fallback** | `dynamic-vcb-and-battery` | Kept. Reusing cable photos across breaker/busbar compartments is completely eliminated across both VCB and RMU. |
| **Battery Decoupling** | Both (Separated) | Decoupled. Battery normalization and dynamic row extraction moved to an independent workstream. |

---

## 2. Switchgear Archetypes & Overview Multi-Views

Resolution evaluates `(switchgear_type, manufacturer, model)` in strict precedence: model decides, manufacturer hints, type bounds.

| Archetype | Resolution Rules | Overview Compartment Tuple | Overview Template Notes |
|---|---|---|---|
| `VCB_CUBICLE` | `type == "VCB"` (regardless of manufacturer) | `("OVERVIEW FRONT", "OVERVIEW REAR", "OVERVIEW TOP")` | Front = Breaker view, Rear = Cable view, Top = Busbar view |
| `GIS_CUBICLE` | `type == "GIS"` | **Deferred** (member defined, profile stubbed) | Multi-gas compartment views deferred until 33kV GIS workbook is available |
| `RMU_DUAL_CABLE_ENTRY` | RMU SF6 + `TAMCO` or `LUCY` (or model `GR1`, `FALCON BETA`) | `("OVERVIEW", "OVERVIEW BOTTOM")` | Bottom = Cable trench / plinth entry view |
| `RMU_FUSE_CANISTER` | RMU SF6 + `INDKOM` + model `INS24` | `("OVERVIEW", "OVERVIEW TOP")` | Top = Gas indicator gauge and fuse canister housing |
| `RMU_OIL` | `type in ("RMU OIL", "OCB")` or Lucy `VRN2a` | `("OVERVIEW", "OVERVIEW BOTTOM")` | Preserves individual OLU serial numbers |
| `RMU_STANDARD` | Fallback for generic RMUs (e.g. INDKOM `JMW12`, Siemens `8DJH`, ABB `SafeRing`) | `("OVERVIEW",)` | Standard single front overview |

### Model Token Extraction & Fallback Rules
1. **VCB Priority**: If `"VCB"` in type/name $\to$ `VCB_CUBICLE`.
2. **GIS Priority**: If `"GIS"` in type/name $\to$ `GIS_CUBICLE`.
3. **Model Token Parsing**: If model cell is blank, inspect manufacturer string for tokens (`"INS24"`, `"GR1"`, `"FALCON"`, `"JMW12"`, `"VRN2A"`, `"GV3"`).
4. **Manufacturer Fallback**:
   - `TAMCO` / `LUCY` $\to$ `RMU_DUAL_CABLE_ENTRY`
   - `INDKOM` + `INS24` $\to$ `RMU_FUSE_CANISTER`
   - `INDKOM` + other/blank $\to$ `RMU_STANDARD` (e.g. JMW12)
   - Oil / OCB $\to$ `RMU_OIL`
5. **Default Fallback**: Any unclassified RMU resolves safely to `RMU_STANDARD`.

---

## 3. Bay Roles & Blueprint Profiles

Bay roles reflect functional panel configurations that alter internal physical compartment layout. The arbitrary distinction between `FEEDER` and `INCOMING` was rejected because their internal physical compartment layouts are identical.

| Bay Role | Keyword Detection Heuristic | Target Switchgear Families |
|---|---|---|
| `STANDARD` | Default / catch-all (includes outgoing feeders, incomers, and `SPARE`) | All families |
| `TRANSFORMER` | Name contains `"TX"`, `"TRANSFORMER"`, `"ALATUBAH"`, `"TEE-OFF"`, `"KVA"` | `RMU_FUSE_CANISTER` (INDKOM INS24) |
| `TRANSITION` | Name contains `"TRANSITION"`, `"PERALIHAN"`, `"TRANSISYEN"`, `"TOOLS"` | `VCB_CUBICLE`, `GIS_CUBICLE` |
| `BUS_SECTION` | Name contains `"BUS SECTION"`, `"BUS-SECTION"`, `"SECTION"` | `VCB_CUBICLE`, `GIS_CUBICLE` |
| `BUS_COUPLER` | Name contains `"BUS COUPLER"`, `"COUPLER"` | `VCB_CUBICLE`, `GIS_CUBICLE` |

---

## 4. Compartment Blueprints & Dynamic Presence Gates

### VCB_CUBICLE Compartment Resolution

```
STANDARD Bay (Incomer, Feeder, Spare):
  [Base (4)]: BREAKER COMPARTMENT, CABLE COMPARTMENT, BUSBAR COMPARTMENT, SECONDARY COMPARTMENT
  + Dynamic PT Gate: appends PT COMPARTMENT iff testsheet row r+3 has evidence
  * Rule: SECONDARY COMPARTMENT is unconditional on standard bays. Gating on heater_amp was explicitly
    rejected because malfunctioning, tripped, or de-energized heaters (recording 0.0A or "-") would
    erroneously drop the physical LV relay compartment.
  * Result: 4 compartments without PT; 5 compartments with PT.

TRANSITION Bay:
  [Base (3)]: FRONT COMPARTMENT, REAR COMPARTMENT, BUSBAR COMPARTMENT
  + Dynamic Secondary Gate (Pure Photo Presence): appends SECONDARY COMPARTMENT iff Col P secondary photo
    was recorded (secondary_photo is not None). Zero dependency on heater current.
  * Rule: TRANSITION bays NEVER have PT COMPARTMENT.
  * Result: 3 compartments without secondary photo; 4 compartments when secondary photo exists.

BUS_SECTION / BUS_COUPLER Bay:
  [Base (4)]: BREAKER COMPARTMENT, REAR COMPARTMENT, BUSBAR COMPARTMENT, SECONDARY COMPARTMENT
  * Rule: Connects busbar sections; rear riser replaces cable termination. Always includes SECONDARY COMPARTMENT.
  * Result: Always 4 compartments.
```

### RMU Blueprints (Static Profiles)

| Archetype | Bay Role | Resolved Compartments | Notes |
|---|---|---|---|
| `RMU_DUAL_CABLE_ENTRY` | `STANDARD` | `("CABLE COMPARTMENT", "CABLE ENTRY")` | Front termination + lower trench entry |
| `RMU_FUSE_CANISTER` | `STANDARD`<br>`TRANSFORMER` | `("CABLE COMPARTMENT",)`<br>`("FUSE COMPARTMENT",)` | Line switches scan cable; TX switch scans fuse canister clips |
| `RMU_OIL` | `STANDARD` | `("CABLE COMPARTMENT", "CABLE ENTRY")` | Cable box + cable entry |
| `RMU_STANDARD` | `STANDARD` | `("CABLE COMPARTMENT",)` | Single cable termination scan |

### Dynamic Presence Gates (Logic Specification)

1. **Dynamic PT Gate**:
   - Evaluated on `VCB_CUBICLE` and `GIS_CUBICLE` (`STANDARD` bays only).
   - **Condition**: Sub-row `r+3` has a non-blank photo number in Col O (`pt_photo is not None`) OR non-empty measurement cells in `K{r+3}..V{r+3}` (`has_pt_measurement is True`).
   - **Outcome**: Appends `"PT COMPARTMENT"`. If condition is false, PT compartment is omitted.
2. **Dynamic Secondary Gate (Transition Bays Only)**:
   - Evaluated on `TRANSITION` bays in `VCB_CUBICLE` and `GIS_CUBICLE`.
   - **Condition**: Non-blank secondary IR photo recorded in Col `P` (`secondary_photo is not None`).
   - **Outcome**: Appends `"SECONDARY COMPARTMENT"`.
   - **Omission of Heater Current Rule**: In real-world substations, space heaters routinely malfunction, trip, or are switched off (recording `0.0A`, `0A`, or `"-"`), but the physical LV relay compartment remains intact and testable. Gating on `heater_amp > 0` was explicitly omitted to prevent false-negative compartment drops. Standard bays and Bus Section bays include `SECONDARY COMPARTMENT` unconditionally in their base blueprint.

---

## 5. Domain Models & Sub-Row Evidence Delivery

### Data Model Extension: `SwitchgearPanelSpec`
To eliminate parallel lookups and decouple extraction from downstream adapters, [`SwitchgearPanelSpec`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/testsheet/models.py) in `src/testsheet/models.py` is extended with explicit sub-row photo attributes:

```python
@dataclass(frozen=True)
class SwitchgearPanelSpec:
    panel_no: int
    panel_feeder_no: str = ""
    name: str = ""
    panel_type: str = ""
    serial_no: str = ""
    status: str = ""
    load_amp: str = ""
    heater_amp: str = ""
    cable_type: str = ""
    us_reading: str = ""
    us_char: str = ""
    tev_reading: str = ""
    tev_ppc: str = ""
    tev_char: str = ""
    photo_numbers: tuple[int, ...] = ()
    compartments: tuple[str, ...] = ()

    # Explicit Sub-Row Evidence Attributes
    cable_photo: int | None = None          # From Col O row r
    breaker_photo: int | None = None        # From Col O row r+1
    secondary_photo: int | None = None      # From Col P row r+1 ("S.PANEL IR <num>")
    busbar_photo: int | None = None         # From Col O row r+2
    pt_photo: int | None = None             # From Col O row r+3
    has_pt_measurement: bool = False        # From Col K..V row r+3
```

### Extraction Mapping in `src/testsheet/extractor.py`
The 4-row sub-grid (`r` = 10, 14, 18, 22) in `PCE Testsheet` is parsed:
- `cable_photo`: extracted from `O{r}`.
- `breaker_photo`: extracted from `O{r+1}`.
- `secondary_photo`: extracted from `P{r+1}` matching regex `r"(?:S\.?\s*PANEL\s*IR|IR)\s*(\d+)"` or bare digits.
- `busbar_photo`: extracted from `O{r+2}`.
- `pt_photo`: extracted from `O{r+3}`.
- `has_pt_measurement`: `True` if any cell in `K{r+3}..V{r+3}` contains non-empty, non-sentinel data.

---

## 6. Downstream Photo Mapping & Strict Zero-Fallback Policy

Handled exclusively within [`SwitchgearScanAdapter`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/full_report/scan_adapters.py) in `src/full_report/scan_adapters.py`.

### 1-to-1 Photo Assignment Rules
1. **VCB Panels**:
   - `"BREAKER COMPARTMENT"` $\to$ `panel.breaker_photo`
   - `"CABLE COMPARTMENT"` $\to$ `panel.cable_photo`
   - `"BUSBAR COMPARTMENT"` $\to$ `panel.busbar_photo`
   - `"PT COMPARTMENT"` $\to$ `panel.pt_photo`
   - `"SECONDARY COMPARTMENT"` $\to$ `panel.secondary_photo`
   - `"FRONT COMPARTMENT"` (Transition) $\to$ `panel.cable_photo` (Row `r`)
   - `"REAR COMPARTMENT"` (Transition/Bus Section) $\to$ `panel.breaker_photo` (Row `r+1`)
2. **RMU Panels**:
   - `"CABLE COMPARTMENT"` $\to$ `panel.photo_numbers[0]` if present, else `None`.
   - `"CABLE ENTRY"` $\to$ `panel.photo_numbers[1]` if `len(panel.photo_numbers) > 1`, else `None`.
   - `"FUSE COMPARTMENT"` $\to$ `panel.photo_numbers[0]` if present, else `None`.

### The Strict Zero-Fallback Rule
- If a resolved compartment's specific photo attribute is `None`, the adapter sets `ir_img = ""` and `vis_img = ""`.
- A blank image placeholder renders in the Word template, and measurement parameter tables display `"-"`.
- **Prohibition**: Under no circumstances will missing breaker, busbar, PT, secondary, or cable-entry photos fall back to `photo_numbers[0]`. Diagnostic evidence must never be repeated or falsified.

---

## 7. Executive Summary Census Presentation & TNB Inspection Standards

### Why Healthy Thermal Photos Display `"-"` in Census Tables
In TNB distribution CBM inspection practice:
1. **Field Testsheet Recording**: Inspectors do **not** record baseline numerical temperatures (°C) into spreadsheet cells for healthy equipment. In `PCE Testsheet`, only photo index numbers are recorded in Col O.
2. **Thermal Radiometric Data**: The thermal measurement lives inside the FLIR `.jpg` image and is viewed on the dedicated scanning page (`swg-panel.docx`) via FLIR ActiveX `CIRViewer`.
3. **Defect Tracking (`QR03 CBA.xlsx`)**: Numerical temperatures and $\Delta T$ values are extracted into spreadsheets **if and only if** an anomaly / hotspot is confirmed.

### Executive Summary Table 2 Rendering Rules

$$\text{NO.} \mid \text{EQUIPMENT} \mid \text{DEFECT AREA} \mid \text{IR (Abs T/ΔT)} \mid \text{U/S (dB)} \mid \text{TEV (dB)} \mid \text{SEVERITY}$$

- **Healthy Tested Components** (Standard, PT, Secondary, or Overview):
  - Measurement columns display empty dash: `IR: "-"`, `U/S: "-"`, `TEV: "-"`.
  - Severity cell text is cleared and background is filled with **Solid Green** (`#00B050`), representing verified normal condition.
- **Defective Components**:
  - Measurement columns populate exact numerical values from `QR03 CBA.xlsx` (e.g. `IR: "68.4 °C / ΔT 37.4 °C"`, `TEV: "28 dB"`).
  - Severity cell text is cleared and background is filled with **Solid Red** (`#EE0000`) (`DEFECT`).
- **Dynamically Gated Compartments**:
  - When present and healthy $\to$ rendered with `"-"` and Green shading.
  - When present and defective $\to$ rendered with defect readings and Red shading.
  - When absent on site (e.g. standard feeder bay without PT) $\to$ **completely omitted** from the table (no row generated, preventing dummy rows).

---

## 8. VoltageClass Seam (11kV vs 33kV)

Implemented in `src/core/topology.py` as a first-class parameter:

```python
class VoltageClass(str, Enum):
    LV = "LV"
    KV_6_6 = "6.6kV"
    KV_11 = "11kV"      # Fully implemented in active cycle
    KV_22 = "22kV"
    KV_33 = "33kV"      # Designed seam
```

- **11kV (Active Scope)**: Single busbar compartment per panel. Overview uses standard front/rear/top views.
- **33kV (Designed Seam)**: Profiles structured to support dual busbar compartments (`BUSBAR MAIN`, `BUSBAR RESERVE`), `BUS_COUPLER` bays, and LHS/RHS multi-angle overview views.

---

## 9. Module Boundaries & Implementation Plan

### Module Placement
- **Engine Core**: `src/core/topology.py` — Pure domain module. Contains `SwitchgearArchetype`, `VoltageClass`, `BayRole`, blueprints, dynamic presence gates, and `SwitchgearTopologyEngine`.
- **Data Models**: `src/testsheet/models.py` — Holds extended `SwitchgearPanelSpec`.
- **Extraction**: `src/testsheet/extractor.py` — Populates sub-row photos.
- **Full Report Adapters**: `src/full_report/scan_adapters.py` & `src/full_report/census.py` — Consume engine output.

### Scratch Organization & Ticket Sequence
Legacy scratch folders `.scratch/dynamic-vcb-and-battery/` and `.scratch/switchgear-archetype/` are archived. Implementation is tracked under `.scratch/switchgear-topology/issues/`:

1. **Issue 01: Core Domain Models & Switchgear Topology Engine**
   - Implement `src/core/topology.py` (`SwitchgearArchetype`, `VoltageClass`, `BayRole`, `SwitchgearTopologyEngine`).
   - Pure unit test suite in `tests/test_topology.py` covering all 6 archetypes, 5 bay roles, and dynamic gates.
2. **Issue 02: SwitchgearPanelSpec Model Extension & Sub-Row Extraction**
   - Add sub-row photo attributes to `SwitchgearPanelSpec`.
   - Update `_extract_panels` in `src/testsheet/extractor.py` to parse rows `r..r+3` and Col `P`.
   - Add extraction unit tests against benchmark workbooks (`157`, `082`, `156`).
3. **Issue 03: Scan Adapters & Executive Summary Census Integration**
   - Wire `SwitchgearTopologyEngine` into `SwitchgearScanAdapter` with strict zero-fallback.
   - Wire engine into `ExecutiveSummaryCensusBuilder` to generate dynamic census rows.
   - Update `build_switchgear_scan_spec` and `build_switchgear_panel_scan_spec` in `src/full_report/models.py`.
4. **Issue 04: Benchmark Deliverables & Regression Suite Alignment**
   - Align PE 179 Cenderawasih NO.1 (14 pages: 6 SWG), PE 144 Telekom Tanah Putih (15 pages: 6 SWG), PE 005 Talapia (19 pages: 10 SWG).
   - Add benchmark assertion for PE 157 Perpustakaan Awam (VCB: 3 overviews, 4 panels $\times$ 4 comp, 1 panel $\times$ 5 comp).
   - Ensure 100% green pass rate across `pytest tests/test_full_report_*.py`.
5. **Issue 05: Legacy Category Purge & Documentation Update**
   - Completely delete `SwitchgearCategory` and legacy procedural helpers.
   - Update `CONTEXT.md` with ubiquitous vocabulary (`SwitchgearArchetype`, `BayRole`, `SwitchgearTopologyEngine`).
   - Perform full test suite regression audit.

### Decoupled Workstream
- Battery bank dynamic extraction (rows 58–68) and composite string normalization are tracked independently in `.scratch/battery-discovery/` for execution in a subsequent milestone.
