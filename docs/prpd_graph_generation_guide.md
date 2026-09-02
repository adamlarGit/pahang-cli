# UltraTEV PRPD Graph Generation Technical Guide

## Overview

This guide documents the exact specification, binary decoding logic, mathematical binning formulas, and implementation for generating **Phase-Resolved Partial Discharge (PRPD)** graph images from UltraTEV survey data.

Future agents and developers should refer to this document to reproduce, maintain, or embed PRPD graphs directly into Quick Reports, Full Reports, or standalone analyses.

---

## 1. Directory Structure of Raw UltraTEV Data

Inside each substation's raw material directory:
```text
RAW MATERIAL/<STATION>/<MONTH>/<DATE>/<PE_FOLDER>/RAW DATA/US+TEV/<SURVEY_STEM>/
├── index.html
├── survey_metadata.js
├── survey_summary.js
├── resources/
│   ├── graphs/
│   │   ├── prpd.js
│   │   ├── utp2_event.js
│   │   └── ...
│   └── scripts/
│       └── deserialise_utp2_bundle.js
├── SWG/
│   ├── FEEDER_1/
│   │   ├── <TIMESTAMP>_TEV/
│   │   │   ├── TEV.html                  <-- Target HTML Web App
│   │   │   ├── eventData.js              <-- TEV Raw Event Data (FlatBuffers)
│   │   │   ├── measurement_metadata.js   <-- Measurement Table JSON
│   │   │   └── wfmData.js
│   │   └── <TIMESTAMP>_Ultrasonic/
│   │       ├── Ultrasonic.html           <-- Target HTML Web App
│   │       ├── ultrasonic_phase_plot.js  <-- Ultrasonic Raw Phase Plot (JSON)
│   │       └── measurement_metadata.js
│   ├── FEEDER_2/
│   └── ...
└── TX/
    └── Transformer/ (or TX1/, TX2/)
        └── <TIMESTAMP>_Ultrasonic/
            ├── Ultrasonic.html
            ├── ultrasonic_phase_plot.js  <-- Transformer Ultrasonic Data
            └── measurement_metadata.js
```

---

## 2. Data Formats & Binary Decoding

### A. TEV Measurements (`eventData.js`)

#### Format
`eventData.js` defines a JavaScript variable containing a Base64-encoded, Gzip-compressed FlatBuffers binary buffer:
```javascript
var eventData="H4sIAAAAAAAEA0yddXwVydL3a5Jgi7tDEiC4Fw7nJLi72+LusOguHNydxXVxDSTEk3Pigrvb4r64Q55fd/V9P+/zx3Mv31tVU1NdXV3dZ2aSi4g6NapUORPlomyUidKTB/4/0dTYpOibB1vUTY//fi0d0QeLqO1cD6o524NKzfSgfDM8KP1fHvRlqgc9nexB1yZ6UPIEDwod50H7xnjQ+lEetGCEB00e5kFDhnhQ10Ee1HQA9PtBvw/0e0O/J/S7Qb8L9DtBvwP020G/DfRbQb8F9JtBv...";
```

#### Binary Layout (FlatBuffers Identifier `UE01`)
1. **Header & Decompression**:
   - Extract string matching `var eventData = "([^"]+)"`.
   - Decode Base64 and decompress via `gzip.decompress()`.
2. **Table Traversal**:
   - Root table offset: `struct.unpack_from("<I", raw_bytes, 0)[0]`
   - VTable offset: `root_offset - struct.unpack_from("<i", raw_bytes, root_offset)[0]`
   - Field 0 (vector offset): `struct.unpack_from("<H", raw_bytes, vtable_offset + 4)[0]`
   - Vector length: `struct.unpack_from("<I", raw_bytes, vector_pos)[0]`
3. **`SingleEvent` Struct (24 bytes per record)**:
   ```python
   # Little-endian struct unpack: "<fiHHHHff"
   peak, integral, phase, cycle, risetime, width, tf_t, tf_f = struct.unpack_from(
       "<fiHHHHff", raw_bytes, elem_pos
   )
   ```
   - `peak`: `float32` — Peak amplitude in **dB** (Y-axis metric for TEV).
   - `phase`: `uint16` — Phase angle in integer degrees ($0^\circ \le \theta < 360^\circ$).
   - `cycle`: `uint16` — Power cycle index.
   - `risetime`, `width`: `uint16` — Pulse characteristics.
   - `tf_t`, `tf_f`: `float32` — Time-frequency coordinates.

---

### B. Ultrasonic Measurements (`ultrasonic_phase_plot.js`)

#### Format
`ultrasonic_phase_plot.js` defines a JSON object with a 2D array of event tuples:
```javascript
var ultra_events = {"data":[[0.709871, 3, 17732], [-0.658168, 13, 17732], ...]};
```

#### Extraction & Scaling
1. Extract JSON via regex `var ultra_events = ({.*?});`.
2. Each event is a tuple `[peak, phase, cycle]`:
   - `peak`: Float amplitude in $\text{dB}\mu\text{V}$.
   - `phase`: Integer phase angle ($0^\circ \le \theta < 360^\circ$).
   - `cycle`: Power cycle index.
3. **Rounding Rule (UltraTEV Spec)**:
   - Round amplitude to the nearest $\frac{1}{3}\text{ dB}$:
     $$\text{amp}_{\text{rounded}} = \frac{\text{round}(\text{peak} \times 3.0)}{3.0}$$

---

## 3. Repetition Density Binning & Color Algorithm

To display pulse repetition frequency (how many partial discharge pulses occurred at the exact same phase angle and amplitude), UltraTEV groups coordinates into **4 distinct color tiers**:

1. Count occurrences of each discrete coordinate key $(\text{phase}, \text{amplitude})$:
   $$\text{count}(\text{phase}, \text{amp})$$
2. Determine maximum repetition count:
   $$\text{count}_{\max} = \max(\text{all counts})$$
3. Compute threshold boundaries:
   $$\text{thresh}_0 = 0.10 \times \text{count}_{\max}$$
   $$\text{thresh}_1 = 0.45 \times \text{count}_{\max}$$
   $$\text{thresh}_2 = 0.80 \times \text{count}_{\max}$$
4. Categorize points into 4 bins:

| Bin | Repetition Condition | Color Code | Hex Code | Legend Label | Layer Order (Z-Index) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | $\text{count} \le \text{thresh}_0$ | Bright Green | `#00FF00` | `< T0` | 1 (Bottom) |
| **Tier 2** | $\text{thresh}_0 < \text{count} \le \text{thresh}_1$ | Pure Blue | `#0000FF` | `T0 < T1` | 2 |
| **Tier 3** | $\text{thresh}_1 < \text{count} \le \text{thresh}_2$ | Bright Red | `#FF0000` | `T1 < T2` | 3 |
| **Tier 4** | $\text{count} > \text{thresh}_2$ | Dark Crimson Red | `#640000` | `T2 < T_max` | 4 (Top) |

> [!IMPORTANT]
> Always plot the scatter bins in ascending order (Tier 1 $\rightarrow$ Tier 2 $\rightarrow$ Tier 3 $\rightarrow$ Tier 4). This ensures high-density discharge clusters remain visible on top.

---

## 4. Axis Specifications & Visual Layout

| Technology | X-Axis Range | X-Axis Ticks & Label | Y-Axis Range | Y-Axis Ticks & Label |
| :--- | :--- | :--- | :--- | :--- |
| **TEV** | $0^\circ \text{ to } 360^\circ$ | `[0, 90, 180, 270, 360]`<br>`Degrees` | $0.0 \text{ to } 60.0$ | Step: `10`<br>`dB` |
| **Ultrasound** | $0^\circ \text{ to } 360^\circ$ | `[0, 90, 180, 270, 360]`<br>`Degrees` | $-10.0 \text{ to } 71.0$ | Step: `10`<br>`dBuV` |

- **Grid**: Light grey `#E2E2E2` solid lines.
- **Spines**: Solid black `#000000` box border around plotting area.
- **Background**: Solid white `#FFFFFF`.
- **Legend**: Top-left corner with white translucent background and thin `#D0D0D0` border.
- **Sine Wave**: Omitted by default for clean publication reports.

---

## 5. Option B — Production Native Python Generator (Locked)

Option B is the primary rendering engine for automated report generation. It runs 100% natively in Python without browser dependencies.

### Generator Script:
[`scripts/generate_prpd_option_b.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/scripts/generate_prpd_option_b.py)

### How to Run (With Dynamic Auto-Discovery):
```bash
# Auto-discover all feeders and transformers across any survey folder:
.venv\Scripts\python.exe scripts/generate_prpd_option_b.py --survey-dir "RAW DATA/US+TEV/<SURVEY_FOLDER>" --output-dir "docs/prpd_preview/option_b"
```

### Python API Reference:
```python
from pathlib import Path
from scripts.generate_prpd_option_b import generate_all_survey_prpd

# Dynamically discovers and renders all measurements across any survey:
results = generate_all_survey_prpd(
    survey_dir=r"RAW DATA/US+TEV/<SURVEY_FOLDER>",
    output_dir=r"docs/prpd_preview/option_b"
)
```

---

## 6. Option C — Composite Measurement Table + PRPD Graph (HTML Engine)

Option C combines the original UltraTEV Bootstrap Measurement Table (`.panel-info`) on the left ($320\text{ px}$) and the Flot PRPD graph on the right ($840\text{ px}$) into a single composite image ($1200 \times 380\text{ px}$).

### Technical Reference:
- Full architecture and UI troubleshooting documentation: [`docs/prpd_option_c_specification.md`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_option_c_specification.md)
- Generator Script: [`scripts/generate_prpd_option_c_html.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/scripts/generate_prpd_option_c_html.py)

### How to Regenerate Option C (With Dynamic Auto-Discovery):
```bash
# Auto-discover and render across any survey folder:
.venv\Scripts\python.exe scripts/generate_prpd_option_c_html.py --survey-dir "RAW DATA/US+TEV/<SURVEY_FOLDER>" --output-dir "docs/prpd_preview/option_c"
```

### Verified Option C Output Files:
- [`docs/prpd_preview/option_c/SWG_FEEDER_1_TEV.png`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_preview/option_c/SWG_FEEDER_1_TEV.png)
- [`docs/prpd_preview/option_c/SWG_FEEDER_1_US.png`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_preview/option_c/SWG_FEEDER_1_US.png)
- [`docs/prpd_preview/option_c/SWG_FEEDER_2_TEV.png`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_preview/option_c/SWG_FEEDER_2_TEV.png)
- [`docs/prpd_preview/option_c/SWG_FEEDER_2_US.png`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_preview/option_c/SWG_FEEDER_2_US.png)
- [`docs/prpd_preview/option_c/SWG_FEEDER_3_TEV.png`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_preview/option_c/SWG_FEEDER_3_TEV.png)
- [`docs/prpd_preview/option_c/SWG_FEEDER_3_US.png`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_preview/option_c/SWG_FEEDER_3_US.png)
- [`docs/prpd_preview/option_c/TX_TRANSFORMER_US.png`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_preview/option_c/TX_TRANSFORMER_US.png)
