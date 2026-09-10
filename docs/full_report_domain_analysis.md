# Full Report Domain Analysis & Architectural Reference

This document captures the empirical analysis of manual Full Scanning Reports from `PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\FULL REPORT` to serve as the authoritative specification and reference for the upcoming Full Report automated generator implementation.

---

## 1. Overview & Philosophical Scope

In the Pahang CLI inspection ecosystem, two distinct report deliverables exist:

| Dimension | Quick Report | Full Report (`CONDITION BASED ASSESSMENT FULL SCANNING REPORT`) |
|:---|:---|:---|
| **Primary Intent** | **Exception-Oriented Defect Brief**: Built for rapid maintenance and repair triage by extracting only anomalous equipment and general substation condition. | **Exhaustive Asset Census**: Built for client contractual compliance, baseline asset profiling, and complete historical audit by capturing every piece of equipment inspected regardless of condition. |
| **Healthy Equipment** | Omitted from CBM scanning pages. A 100% healthy substation generates **0 CBM pages**. | Fully documented. Every switchgear panel, transformer component, and feeder pillar receives a dedicated scanning page with thermal, visual, ultrasound, and TEV data. |
| **CBM Summary** | Lists only active defects (`NO DEFECT FOUND` if clean). | **Executive Summary Census**: Comprehensive inventory listing every bay, panel, cable, and bushing, with color-coded operational status (**Green** for `NORMAL`, **Red** for `DEFECT`). |
| **Page Volume** | Compact (~7–12 pages average). | Comprehensive (~20–35+ pages average). |
| **Post-Processing** | Merged with processed testsheets via `PostProcessingPipelineWorkflow`. | Independent post-processing pipeline and deliverable compilation. |

---

## 2. Empirical Grounding: Analyzed Field Deliverables

The manual full report archive at `C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\FULL REPORT\` was inspected across multiple stations and weeks:

### Kuantan Week 35 (`FULL REPORT\KUANTAN\04. WEEK 35`)

1. **`144. TELEKOM TANAH PUTIH (TEV+VI)` (29 pages):**
   - **Topology**: RMU SF6 INDKOM (4 panels: CKN00048, CKN00049, CKN00050, CKN00051), TX1 (MTM 750kVA), LVDB TX1 (Tamco), Battery Bank 1 (Sunpower).
   - **CBM Findings**: Severe internal TEV partial discharge across all 4 panels (31dB, 31dB, 29dB, 28dB with pulse counts 1.65–1.90/cycle). Each panel triggers an inline **TEV Measurement & PRPD Scatter Plot detail page**.
   - **VI Findings**: 2 items (Old Abloy padlock TX room, LVDB TX1 feeder numbering missing).

2. **`149. TAMAN BUKIT BEIRUT PERMAI (IR+VI)` (25 pages):**
   - **Topology**: RMU SF6 SIEMENS 8DJH RRT (3 panels), TX1 (EWT 750kVA), LVDB TX1 (SSE), Battery Bank 1.
   - **CBM Findings**: Switchgear and TX are CBM Normal. Thermal defect on LVDB TX1 Outgoing F2 Red Phase cable termination (46.5 °C, $\Delta T$ 5.1 °C).
   - **VI Findings**: 7 items (CPR poster old, broken fence, missing SWG earthing, shared battery charger, damaged cable insulation, missing LVDB guard, unstandardized labels).

3. **`173. TAMAN SETONGKOL PERDANA (IR+VI)` (24 pages):**
   - **Topology**: RMU SF6 INDKOM INS24 (4 panels), TX1 (SGB 1000kVA), LVDB TX1 (SSE).
   - **CBM Findings**: Thermal defect on LVDB TX1 Outgoing F3 Yellow Phase fuse connection (58.8 °C, $\Delta T$ 22.7 °C).
   - **VI Findings**: 6 items (CPR poster missing, broken fence, old abloy padlock, trenching unsealed, lighting missing, unstandardized labels).

4. **`176. BUKIT SETONGKOL MEWAH (IR+VI)` (30 pages):**
   - **Topology**: RMU SF6 TAMCO GR1 (3 panels), TX1 (MTM 500kVA), LVDB TX1 (Toprank), Battery Bank 1.
   - **CBM Findings**: Dual thermal defects: TX1 LV Bushing Blue Phase cable lug hotspot (62.8 °C, $\Delta T$ 16.9 °C) and LVDB TX1 Incoming 2 link connection Blue Phase hotspot (61.3 °C, $\Delta T$ 15.7 °C).
   - **VI Findings**: 4 items (CPR poster old, HV cable crossing, missing LVDB guard, unstandardized feeder labels).

5. **`179. CENDERAWASIH NO.1 (IR+VI)` (23 pages):**
   - **Topology**: RMU SF6 INDKOM INS24 (4 panels), TX1 (EWT 1000kVA), Feeder Pillar FP TX1 (Alaf Cekal).
   - **CBM Findings**: Thermal hotspot inside RMU Panel CKN01309 TX Fuse Compartment (33.5 °C, $\Delta T$ 1.0 °C).
   - **VI Findings**: 5 items (CPR poster old, SWG ceiling damaged, lighting unpowered, TX1 low oil level, FP TX1 unstandardized feeder labels).

### 2.1 The Canonical Benchmark Deliverable Trio

To ensure deterministic verification and ground testing in concrete reality, three manually compiled Full Report deliverables are established as the canonical benchmarks:

| PE NO | FL NUMBER | SUBSTATION NAME | DATE | AREA & WEEK | DEFECT MODALITY |
|:---|:---|:---|:---|:---|:---|
| **5** | `CRAU/PCE/J00251` | `TALAPIA` | 04-Aug-2026 | `RAUB`<br>`01. AUGUST / 01. WEEK 32` | **IR + VI** (Thermal hotspot + Visual defects) |
| **179** | `CKTN/PCE/J00030` | `CENDERAWASIH NO.1` | 28-Aug-2026 | `KUANTAN`<br>`04. WEEK 35` | **IR + VI** (TX fuse compartment hotspot + Visual defects) |
| **144** | `CKTN/PCE/J00040` | `TELEKOM TANAH PUTIH` | 24-Aug-2026 | `KUANTAN`<br>`04. WEEK 35` | **TEV + VI** (Severe multi-panel TEV partial discharge) |

**Canonical File Locations (Active Project Documents Drive)**:
- `C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\FULL REPORT\RAUB\01. AUGUST\01. WEEK 32\005. TALAPIA (IR+VI).docx`
- `C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\FULL REPORT\KUANTAN\04. WEEK 35\179. CENDERAWASIH NO.1 (IR+VI).docx`
- `C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\FULL REPORT\KUANTAN\04. WEEK 35\144. TELEKOM TANAH PUTIH (TEV+VI).docx`

### Raub Week 32 (`FULL REPORT\RAUB\01. AUGUST\01. WEEK 32`)

1. **`005. TALAPIA (IR+VI)` (26+ pages):**
   - **Topology**: RMU SF6 INDKOM (4 panels: CRA00223, CRA00224, CRA00225, CRA00226), TX1 (1000kVA), Feeder Pillar FP TX1 (10 ways), Battery Bank 1.
   - **CBM Findings**: Thermal hotspot on Feeder Pillar FP TX1 Outgoing F2 Red Phase fuse contact. 68 raw IR thermal and paired visual photos in `RAW DATA/IR/`.
   - **VI Findings**: 3 visual defect items.

### Additional Diversity References

- **`001. KG RPS ASLI BILUT (VI)` (`RAUB\01. AUGUST\01. WEEK 32`):**
  - Exemplifies a **100% CBM Normal substation**. Every switchgear panel, transformer component, and feeder pillar displays green `"No Anomaly"` banners, and the Executive Summary displays green status cells across all equipment rows.
- **`115. KO YONG SENG, BLUE VALLEY (IR+US+VI)` (`CAMERON HIGHLAND\02. WEEK 33`):**
  - Exemplifies a **3-Switchgear installation** and an **Ultrasound Defect detail page** (Tracking sound at 22dB, Phase-Resolved scatter graph, and internal microphone classification table).

---


## 3. Full Report Document Architecture

A complete Full Report deliverable consists of a single portrait Microsoft Word document (.docx) followed by appended landscape Excel testsheets (.pdf):

```
[Full Report Document Structure]
 ├── 1. Front Page / Cover
 ├── 2. Executive Summary (Comprehensive Equipment Census)
 ├── 3. Visual Defect Summary (Kejanggalan Inventory)
 ├── 4. Component CBM Scanning Stream (Exhaustive Per-Component Records)
 │    ├── Switchgear Overview (Front + Top/Bottom)
 │    ├── Switchgear Panel Scanning Pages (Cable Compartment / Entry / Fuse)
 │    │    └── [Optional Inline Defect Detail Page: TEV PRPD or IR Hotspot]
 │    ├── Transformer Component Scanning Pages (Overview, Top, HV Bushing, HV Cable, LV Bushing, LV Cable)
 │    │    └── [Optional Inline Defect Detail Page: Bushing / Lug Hotspot]
 │    ├── LVDB / Feeder Pillar Scanning Page (Overview)
 │    │    └── [Optional Inline Defect Detail Page: Outgoing Feeder / Fuse Hotspot]
 │    └── Battery Bank Scanning Page (Overview)
 ├── 5. Substation Condition Pages (2-Column Asset Condition Photo Grid)
 ├── 6. Visual Defect Detail Pages (2-Column Kejanggalan Photo Grid)
 ├── 7. Normal & Defect Sticker Page
 └── 8. Appended Testsheets (Post-Processing COM PDF Merge)
      ├── PCE CBA Test Sheet (Landscape)
      └── PCE Visual Inspection Checklist (Portrait)
```

### Detailed Section Specifications

#### Part 1: Front Page / Cover
- **Header**: TNB Logo (left), EET Engineering Services Logo (right).
- **Title**: `CONDITION BASED ASSESSMENT FULL SCANNING REPORT` (`SBUM DIAGNOSTIC PAHANG`, `TNB BAHAGIAN PEMBAHAGIAN PAHANG`).
- **Metadata Table**: Functional Location (ERMS + Site), Substation Name (ERMS + Site), GPS Coordinates, Substation Type (`PCE`), Area, State (`PAHANG`), PO Number (`42360565`), Inspection Date.
- **Crew & Calibration Block**: Scanned By (Thermography, Ultrasound, TEV names + ILSAS/cert numbers); Instruments & Calibration Expiry Dates (FLIR T640, UTP-2).
- **Signboard Image**: Framed digital photo of the physical PE signboard.

#### Part 2: Executive Summary (Equipment Census)
- **Table Structure**: `NO. | EQUIPMENT | DEFECT AREA | IR (Abs T/ΔT) | U/S | TEV | SEVERITY`
- **Exhaustive Inventory**: Lists every asset and testable component:
  - `RMU SF6 / VCB`: OVERVIEW, OVERVIEW TOP/BOTTOM, and every individual panel's CABLE COMPARTMENT, CABLE ENTRY, or FUSE COMPARTMENT.
  - `TX1..TXn`: OVERVIEW, OVERVIEW TOP, HV BUSHING, HV CABLES, LV BUSHING, LV CABLES.
  - `LVDB / FP`: OVERVIEW, plus specific outgoing defective ways.
  - `BATTERY 1`: OVERVIEW.
- **Color-Coding**:
  - Healthy tested components: **Green fill** in Severity column (`NORMAL`), `-` in measurement columns.
  - Anomalous tested components: **Red fill** in Severity column (`DEFECT`), measured readings populated.

#### Part 3: Visual Defect Summary (Kejanggalan Inventory)
- **Table Structure**: `NO. | EQUIPMENT | DEFECT DESCRIPTION | ADDITIONAL REMARKS`
- Matches the Visual Inspection checklist. If 0 defects exist, displays single row: `"NO DEFECT FOUND"`.

#### Part 4: Component CBM Scanning Stream
- Every single equipment component receives a full dedicated page.
- **Standard Switchgear Panel 4-Quadrant Layout**:
  - **Top Left**: Thermal IR image with crosshairs (`Ar1`, `Sp1`, `Sp2`, `Dt1`).
  - **Top Right**: Visual digital photo of the panel.
  - **Middle Left**: Thermal Parameter Table (`Sp1`, `Sp2`, `Ar1`, `Ambient`, `ΔT`, `Load`, `Defect`).
  - **Middle Right**: Electrical Parameter Table (`Serial No`, `Heater`, `CB Position`, `Busbar Position`, `Cable Type`).
  - **Bottom Left**: Ultrasound Waveform scatter graph + Table (`Decibel`, `Sound characteristic`, `Severity`, `Sound clip icon`).
  - **Bottom Right**: TEV Waveform scatter graph + Table (`TEV Background`, `Reading`, `Pulse/Cycle`, `Severity`).
  - **Bottom Banner**:
    - **Green Banner** (Healthy): `Analysis: No Anomaly. | Recommendation: -`
    - **Red Banner** (Defective): `Analysis: Please refer to the following page for details defect. | Recommendation: Please refer to the following page for details defect.`
- **Inline Defect Detail Pages**:
  - Inserted **immediately following** an anomalous component scanning page.
  - Supports TEV (PRPD scatter graph + table), Ultrasound (phase plot + frequency spectrum table), or IR (zoomed thermal view + fault analysis).

#### Part 5: Substation Condition Pages
- Standard 2-column photo grid matching Quick Report: Substation Overview, Signboard, Switchgear + Nameplate, Transformer + Nameplate, LVDB/FP + Nameplate, Battery Charger + Nameplate, RTU + Nameplate, SF6 Indicator, EFI, Fire Extinguishers (SWG & TX rooms) with BOMBA tags, Transformer Oil Level Indicator.

#### Part 6: Visual Defect Detail Pages
- Standard 2-column photo grid showing each reported visual defect with marked red arrows/boxes, equipment category, and defect description captions.

#### Part 7: Sticker Page
- Displays on-site inspection stickers:
  - Green **Normal Sticker** (`Condition Assessment` sticker with date and inspector name).
  - Red **Defect Notification Sticker(s)** placed on defective panels, transformer bushings, or LVDBs.

#### Part 8: Appended Testsheets (PDF Merge)
- In post-processing, the compiled Word document is converted to PDF and merged with the landscape Excel testsheets (`PCE Testsheet` + `PCE VI`).

---

## 4. Deliverable Naming & Directory Conventions

- **Workspace Root Directory**: `FULL REPORT/` (sibling to `QUICK REPORT/`, `TESTSHEET/`, `RAW MATERIAL/`, `WHATSAPP/`).
- **Path Hierarchy**: `FULL REPORT/<STATION>/<MONTH>/<DD-MM-YYYY>/` (or `<STATION>/<WEEK>/`).
- **Filename Convention**: `<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>).docx` and `.pdf`
  - Exactly matches `PahangRenamedSubstationStem`.
  - Examples:
    - `144. TELEKOM TANAH PUTIH (TEV+VI).docx`
    - `149. TAMAN BUKIT BEIRUT PERMAI (IR+VI).docx`
    - `001. KG RPS ASLI BILUT (VI).docx`
    - `005. KUALA SEMANTAN.docx` (if no defects exist)

---

## 5. Domain Concepts for Future Full Report Implementation

When designing the Full Report workflow in the dedicated wayfinder session, the following domain models and policies should be established:

1. **`FullReportDocument` / `FullReportStationPlan`**:
   Top-level domain models orchestrating the generation of a complete Full Scanning Report.
2. **`ExecutiveSummaryCensus`**:
   The domain model responsible for traversing `SubstationEquipmentPackage` and compiling the exhaustive multi-equipment status table with green/red classification.
3. **`ComponentScanPagePlan` & `ScanModality`**:
   Domain model specifying per-component 4-quadrant scanning pages (IR, visual, US, TEV) across switchgear bays, transformers, and feeder pillars.
4. **`DefectInterleavingPolicy`**:
   The presentation rule governing the dynamic insertion of inline defect detail pages immediately following defective component scanning pages.
5. **Shared Subsystem Reuse (DRY Principles)**:
   The Full Report generator should directly reuse existing core domain extractors and renderers:
   - `FrontPageRenderer`
   - `ViSummaryRenderer` & `ViDefectPagesRenderer`
   - `SubstationConditionPairBuilderPolicy`
   - `StickerPageRenderer`
   - `BatchComSession`
6. **Dedicated Template Directory Decoupling**:
   - `templates/FULL REPORT/NORMAL IR US TEV/`: Houses baseline component scanning templates (`swg-overview.docx`, `swg-panel.docx`, `tx-overview.docx`, `tx-hv-sides.docx`, `tx-lv-sides.docx`, `fp-overview.docx`, `battery-overview.docx`). Initialized as identical copies of Quick Report's `DEFECT IR US TEV/` templates, this dedicated hierarchy decouples Full Report healthy scanning layouts and allows independent formatting or styling divergence without risk of breaking Quick Report deliverables.
   - `templates/FULL REPORT/`: Will house the modular `executive_summary_census.docx` template.

