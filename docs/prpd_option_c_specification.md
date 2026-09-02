# UltraTEV Option C Specification & Technical Context

## 1. Executive Summary & Objective

In our CBM defect report generation workflow, we are enhancing the switchgear panel and transformer defect detail pages (`templates/QUICK REPORT/DEFECT IR US TEV/swg-panel.docx` and `tx-hv-sides.docx`) to automatically embed visual Partial Discharge (PD) analysis into `{{ us.prpd }}` and `{{ tev.prpd }}`.

**Option C** generates a **composite image ($1200 \times 380\text{ px}$)** containing:
1. **Left Side ($320\text{ px}$)**: The original UltraTEV Bootstrap Measurement Table (`.panel-info`) showing exact sensor readings, accessory type, classifications, noise levels, and phase reference lock details.
2. **Right Side ($840\text{ px}$)**: The Phase-Resolved Partial Discharge (PRPD) scatter graph rendered by UltraTEV's native Flot engine ($0^\circ–360^\circ$ phase angle, 4-tier repetition density colors, no reference sine wave).

This document serves as the complete technical handoff for any engineer or agent maintaining or extending the Option C UI engine.

---

## 2. Directory Layout & Raw Data Structure

Raw UltraTEV survey material is located under:
```text
RAW MATERIAL/<STATION>/<MONTH>/<DATE>/<PE_FOLDER>/RAW DATA/US+TEV/<SURVEY_FOLDER>/
├── index.html
├── survey_metadata.js
├── resources/
│   ├── scripts/bootstrap-3.3.6-dist/ (Bootstrap CSS/JS)
│   ├── scripts/jquery-1.11.3/ (jQuery & jQuery Flot)
│   └── graphs/ (prpd.js, utp2_event.js, etc.)
├── SWG/
│   ├── FEEDER_1/
│   │   ├── 20260825T103449_TEV/
│   │   │   ├── TEV.html                  <-- Target HTML Web App
│   │   │   ├── eventData.js              <-- Binary FlatBuffers (UE01)
│   │   │   └── measurement_metadata.js   <-- Measurement Table JSON
│   │   └── 20260825T103610_Ultrasonic/
│   │       ├── Ultrasonic.html           <-- Target HTML Web App
│   │       ├── ultrasonic_phase_plot.js  <-- Acoustic Events JSON
│   │       └── measurement_metadata.js
│   ├── FEEDER_2/
│   └── FEEDER_3/
└── TX/
    └── Transformer/ (or TX1, TX2)
        └── 20260825T103723_Ultrasonic/
            └── Ultrasonic.html
```

---

## 3. The UI Challenge & Root Cause Analysis

### What Went Wrong Previously (The "Overlap" Bug)
When attempting to render the measurement table side-by-side with the PRPD graph:
1. In `TEV.html` and `Ultrasonic.html`, the sidebar `<div class="survey col-md-3">` contains an inner `<div class="tab-content">`, and the graph container on the right is also a `<div class="tab-content col-md-9">`.
2. Simple CSS rules targeting `.tab-content` inadvertently expanded the left sidebar's inner tab container to 840px, causing the table to stretch across the whole viewport and overlay in front of the graph.
3. Bootstrap 3 grid classes (`.col-md-3`, `.col-md-9`) and inline styles (`style="width:70%;height:80%;float:left;"`) caused float collisions.

### The Solution (Robust DOM Flexbox Injection)
To guarantee strict side-by-side rendering with zero overlap:
1. Wrap the layout in a top-level Flexbox container on `document.body` (`display: flex; flex-direction: row;`).
2. Remove Bootstrap grid column classes and fix `.survey` at exactly `width: 320px; flex: 0 0 320px;`.
3. Hide Panels 1 and 2 (Metadata and Component Details) so only Panel 3 (`$GROUP_MEASURES` / Measurement Table) is visible.
4. Target the outer graph `.tab-content` and expand it across the remaining space (`width: 840px; flex: 1 1 840px;`).
5. Set `prpd.sinewave_mode = 0` and trigger `prpd.Plot()` on window load.

```javascript
window.addEventListener('load', function() {
    document.body.style.cssText = 'display: flex !important; flex-direction: row !important; align-items: stretch !important; justify-content: flex-start !important; width: 1200px !important; height: 380px !important; margin: 0 !important; padding: 10px !important; box-sizing: border-box !important; background: white !important; overflow: hidden !important;';

    var surveyEl = document.querySelector('.survey');
    if (surveyEl) {
        surveyEl.className = 'survey';
        surveyEl.style.cssText = 'width: 320px !important; min-width: 320px !important; max-width: 320px !important; flex: 0 0 320px !important; margin: 0 15px 0 0 !important; padding: 0 !important; float: none !important;';
        var surveyTab = surveyEl.querySelector('.tab-content');
        if (surveyTab) surveyTab.style.cssText = 'width: 100% !important; padding: 0 !important; margin: 0 !important;';
    }

    var allTabContents = document.querySelectorAll('.tab-content');
    var graphTabContent = allTabContents[allTabContents.length - 1];
    if (graphTabContent) {
        graphTabContent.style.cssText = 'flex: 1 1 840px !important; width: 840px !important; height: 360px !important; margin: 0 !important; padding: 0 !important; float: none !important; overflow: hidden !important;';
    }

    var phaseTab = document.getElementById('phase_tab');
    if (phaseTab) {
        phaseTab.style.cssText = 'width: 100% !important; height: 100% !important; margin: 0 !important; padding: 0 !important; float: none !important; display: block !important;';
    }

    var prpdSection = document.getElementById('prpd_section');
    if (prpdSection) {
        prpdSection.style.cssText = 'width: 100% !important; height: 100% !important; margin: 0 !important; padding: 0 !important; float: none !important; position: relative !important;';
    }

    var prpdGraph = document.getElementById('prpd_graph');
    if (prpdGraph) {
        prpdGraph.style.cssText = 'width: 100% !important; height: 100% !important;';
    }

    setTimeout(function() {
        if (typeof prpd !== 'undefined') {
            prpd.sinewave_mode = 0;
            prpd.Plot();
        }
    }, 150);
});
```

---

## 4. Measurement Fields Rendered in the Table

### TEV Measurements (`$GROUP_MEASURES`)
- **Measurement (dB)**: Peak discharge level (e.g. `5`)
- **Measurement (PPC)**: Pulses per cycle (e.g. `0.00`)
- **Noise Level (dB)**: Baseline acoustic/electrical noise (e.g. `0`)
- **TEV Interpretation**: Translated enum (e.g. `No Concern`)
- **TEV Classification**: Translated enum (e.g. `Noise`)
- **TEV Classification PD (%)**: Probability/confidence (e.g. `0`)
- **Phase Reference Locked**: Boolean (`True` / `False`)
- **Phase Reference Source**: Source (`Manual` / `E-Field`)
- **Phase Reference Strength (%)**: Synchronicity strength (`100%`)

### Ultrasonic Measurements (`$GROUP_MEASURES`)
- **Measurement (dBμV)**: Acoustic amplitude level (e.g. `-5`)
- **Ultrasonic Accessory**: Probe type (e.g. `Internal Microphone` / `Contact Probe`)
- **Ultrasonic Classification**: Classification (e.g. `Noise` / `PD`)
- **Classification Certainty (%)**: Certainty confidence (`100%`)
- **Phase Reference Locked**: Boolean (`True` / `False`)
- **Phase Reference Source**: Source (`Manual`)
- **Phase Reference Strength (%)**: Synchronicity strength (`100%`)

---

## 5. Generator Script & How to Reproduce

- **Standalone Script**: [`scripts/generate_prpd_option_c_html.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/scripts/generate_prpd_option_c_html.py)
- **Output Directory**: [`docs/prpd_preview/option_c/`](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/prpd_preview/option_c/)

### Execution Command:
```bash
.venv\Scripts\python.exe scripts/generate_prpd_option_c_html.py
```

### Verified Output Files:
1. `SWG_FEEDER_1_TEV.png` ($1200 \times 380\text{ px}$, 46.6 KB)
2. `SWG_FEEDER_1_US.png` ($1200 \times 380\text{ px}$, 75.2 KB)
3. `SWG_FEEDER_2_TEV.png` ($1200 \times 380\text{ px}$, 55.0 KB)
4. `SWG_FEEDER_2_US.png` ($1200 \times 380\text{ px}$, 76.2 KB)
5. `SWG_FEEDER_3_TEV.png` ($1200 \times 380\text{ px}$, 53.4 KB)
6. `SWG_FEEDER_3_US.png` ($1200 \times 380\text{ px}$, 74.8 KB)
7. `TX_TRANSFORMER_US.png` ($1200 \times 380\text{ px}$, 76.0 KB)
