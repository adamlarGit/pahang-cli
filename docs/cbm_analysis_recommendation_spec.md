# Specification: Programmatic CBM Defect Analysis & Recommendation Generation

**Status:** Approved & Locked  
**Author:** Antigravity / Pair Programming  
**Authoritative Corpus:** `PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD`  
**Reference Research:** [`docs/research/cbm_defect_analysis_recommendations.md`](../docs/research/cbm_defect_analysis_recommendations.md)  
**Wayfinder Map:** [#12](https://github.com/adamlarGit/pahang-cli/issues/12) | **Grilling Ticket:** [#14](https://github.com/adamlarGit/pahang-cli/issues/14) | **Task Ticket:** [#16](https://github.com/adamlarGit/pahang-cli/issues/16)

---

## 1. Objective & Scope

The objective is to eliminate manual drafting of **"Analysis"** and **"Recommendation"** entries in Quick Report CBM defect detail and overview pages by programmatically generating authoritative, professional engineering prose with:
- **100% accuracy** for LVDB and Feeder Pillar defect pages (`fp-individual-defect.docx`).
- **>90% accuracy** for Switchgear Panel defect pages (`swg-panel.docx`) and Transformer defect pages (`tx-hv-sides.docx`, `tx-lv-sides.docx`).
- Standardized overview table status formatting across `swg-overview.docx`, `tx-overview.docx`, and `fp-overview.docx`.
- Robust ancillary support for `battery-overview.docx` and `blackbox-overview.docx`.

All generated phrasing strictly adheres to the empirical standards of **`PO 42360565 - AZZAD`** to eliminate inter-author variation and ensure uniform deliverable quality across all inspection cycles.

---

## 2. Architecture & Seams

### 2.1 Pure Domain Rule Engine (`src/quick_report/cbm_rules.py`)
A standalone deep module providing pure deterministic functions with zero external I/O, docx, or COM dependencies:
```python
def generate_cbm_analysis_and_recommendation(
    record: CbmDefectRecord,
    *,
    equipment_type: str,
    equipment_pkg: SubstationEquipmentPackage | None = None,
    panel_spec: SwitchgearPanelSpec | None = None,
    is_overview: bool = False,
) -> tuple[str, str]:
    """Return (analysis_text, recommendation_text) for a CBM defect record."""
```

### 2.2 Structured Phrase Registry (`CBM_PHRASE_REGISTRY`)
Phrases are structured into an extensible domain model rather than loose global constants, preparing the codebase for dynamic, per-station or per-technology phrase configuration in future cycles:
```python
@dataclass(frozen=True)
class CbmPhraseTemplate:
    analysis: str
    recommendation: str

    def format(self, **kwargs: Any) -> tuple[str, str]:
        return (
            self.analysis.format(**kwargs),
            self.recommendation.format(**kwargs),
        )
```

### 2.3 Reuse of Existing Infrastructure
- **Feeder Way & Incomer/Outgoing Detection:** Leverages `src/testsheet/feeder_thermal.py` (`resolve_feeder_channel`) to determine incoming vs. outgoing feeder channels (`IN1..IN3` vs. `OT1..OT10`) without duplicate parsing logic.
- **US Characteristic Normalization:** Reuses `src/core/normalizers.py` (`normalize_us_characteristic`).
- **Defect Record & Column K:** Reuses `CbmDefectRecord` from `src/quick_report/defects.py` populated from `QR03 CBA.xlsx`, extracting Column K (`HV/LV`) as `record.hv_lv`.

### 2.4 Presentation Seam (`src/quick_report/cbm_render.py`)
- OpenXML cell shading post-processing (`_post_process_overview_cell`) lives strictly in `cbm_render.py`, keeping `cbm_rules.py` 100% pure domain logic.
- Injects `"analysis"` and `"recommendation"` at both root context and equipment-specific namespaces (`fp.analysis`, `panel.analysis`, `tx.analysis`, `batt.analysis`, `bbox.analysis`).

---

## 3. Closed-Loop Generation Rules

### 3.1 LVDB & Feeder Pillar (`fp_lvdb`) — Target: 100% Accuracy

#### Rule 3.1.1: DIN Type Feeder Pillar (`FP (D)`)
- **Detection:** `record.equipment` or `model` matches `FP (D)` or DIN type.
- **Lug Hotspot:** If `record.defect_area` or `record.additional_remarks` contains `LUG`:
  - **Analysis:** `Thermal image above indicates hot spot detected at {PHASE} CABLE LUG CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.`
  - **Recommendation:** `To inspect, clean the contact surface, re-crimp and re-tighten the connection point. Replace defective parts if necessary.`
- **Fuse Compartment Hotspot (Default for DIN):**
  - **Analysis:** `Thermal image above indicates hot spot detected at FUSE COMPARTMENT. The anomaly is due to loosen or bad contact at the connection point.`
  - **Recommendation:** `To inspect, clean the contact surface and re-tighten the connection point. Replace defective parts if necessary.`

#### Rule 3.1.2: LVDB & J-Slotted Feeder Pillar (`LVDB`, `FP (J)`)
- **Direction Resolution:**
  - Check `resolve_feeder_channel(record.equipment_id)`. If channel starts with `IN` or identifier mentions `INCOMING`/`INC` $\to$ `INCOMING`.
  - If channel starts with `OT` or identifier mentions `OUTGOING`/`F1..F10` $\to$ `OUTGOING` (default if unspecified).
- **Component Sub-type:**
  - If `LINK` in `record.defect_area` $\to$ `{DIRECTION} LINK CONNECTION`
  - If `LUG` in `record.defect_area` $\to$ `{PHASE} CABLE LUG CONNECTION`
  - Otherwise (default) $\to$ `{DIRECTION} FUSE CONNECTION`
- **Analysis:**
  - For lugs: `Thermal image above indicates hot spot detected at {PHASE} CABLE LUG CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.`
  - For fuses/links: `Thermal image above indicates hot spot detected at {DIRECTION} {FUSE/LINK} CONNECTION. The anomaly is due to loosen or bad contact at the connection point.`
- **Recommendation:**
  - For lugs: `To inspect, clean the contact surface, re-crimp and re-tighten the connection point. Replace defective parts if necessary.`
  - For fuses/links: `To inspect, clean the contact surface and re-tighten the connection point. Replace defective parts if necessary.`

---

### 3.2 Switchgear Panels (`swg`) — Target: >90% Accuracy

#### Rule 3.2.1: PILC Cable (Paper-Insulated Lead-Covered)
- **Trigger:** Either `record.defect_area`, `record.equipment_id`, or `panel_spec.cable_type` contains `"PILC"`.
- **Analysis:** `Thermal image above indicates hotspot detected at CABLE SWG – CABLE PILC.`
- **Recommendation:** `To inspect and replace PILC with XLPE cable.`

#### Rule 3.2.2: XLPE Cable Termination
- **Trigger:** `record.technology == "IR"` and defect area matches `TERMINATION` or `XLPE` (or standard cable compartment IR rise without PILC).
- **Analysis:** `Thermal image above indicates hotspot detected at CABLE TERMINATION/CABLE XLPE. The anomaly is due to void, insulation material deterioration or defective cable.`
- **Recommendation:** `To inspect and make a new termination or replace defective parts if necessary.`

#### Rule 3.2.3: Secondary Compartment / Cable Tag
- **Trigger:** `record.defect_area` contains `SECONDARY` or `TAG`.
- **Analysis:** `Thermal image above indicates hotspot detected at SECONDARY COMPARTMENT – CABLE CONNECTION (CABLE TAG {TAG}). The anomaly is due to loose or bad contact at the connection point.`
- **Recommendation:** `To inspect, clean the contact surface, re-tighten the connection points or replace defective parts if necessary.`

#### Rule 3.2.4: Airborne Ultrasound (US) Discharge (Strict Defect Gated)
- **Trigger:** `record.technology == "US"` OR `record.us_char` matches an active defect code (`CORONA`, `TRACKING`, `ARCING`, `MECHANICAL VIBRATION`, `C`, `T`, `A`, `MV`).
- **Normal Background Noise Guard:** If `us_char` is `NORMAL`, `"-"`, empty, or background noise without defect technology, partial discharge text is **never** generated.
- **Compartment:** Derived from `record.defect_area` (default: `CABLE COMPARTMENT`).
- **Analysis:**
  - For PD (`corona`/`tracking`/`arcing`): `Electrical {char} partial discharge sound detected at {COMPARTMENT}.`
  - For vibration: `Audible mechanical vibration sound detected at {COMPARTMENT}.`
- **Recommendation:** `Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. If any parts are found to be in poor condition, replacement is necessary.`

#### Rule 3.2.5: Transient Earth Voltage (TEV) Internal Discharge
- **Trigger:** `record.technology == "TEV"` (or `tev_reading` > 0).
- **Compartment:** Derived from `record.defect_area` (default: `CABLE COMPARTMENT`).
- **Analysis:** `High TEV reading detected at {COMPARTMENT}. Based on the phase-resolved partial discharge, graph indicates internal electrical partial discharge.`
- **Recommendation:** `To inspect the bushing, cable termination and cable for sign of internal electrical partial discharge. If parts in poor condition, parts replacement are necessary. Before any rectification work is being carried out, please conduct test using TEV locater or sequence switching to find the source of high TEV reading. It is recommended to plan shutdown with CBM team.`

#### Rule 3.2.6: Compound Multi-Technology Defects (IR + US + TEV)
- When a switchgear panel exhibits both thermal (IR) and acoustic/TEV discharge anomalies:
  - Both findings are formatted in chronological sequence separated by a line break in the single `{{ analysis }}` and `{{ recommendation }}` placeholders.

---

### 3.3 Transformers (`tx`) — Target: >90% Accuracy

Mapped directly against the official `QR03` master dropdown options:

#### Rule 3.3.1: HV Cable Termination
- **Trigger:** `record.defect_area` matches `HV CABLE TERMINATION`, `HV CABLE XLPE`, `HV CABLE PILC`, or `HV CABLE BOX`.
- **Analysis:** `Thermal image above indicates hot spot detected at HV CABLE TERMINATION – {PHASE}. The anomaly is due to void, insulation material deterioration or defective cable.`
- **Recommendation:** `To inspect and make a new termination or replace defective parts if necessary.`

#### Rule 3.3.2: Bushing Connections (LV vs. HV)
- **LV Bushing:**
  - **Analysis:** `Thermal image above indicates hot spot detected at {PHASE} BUSHING CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.`
  - **Recommendation:** `To inspect bushing condition especially at its internal rod, perform proper cleaning and re-tighten the connection point or replace defective parts if necessary.`
- **HV Bushing:**
  - **Analysis:** `Thermal image above indicates hot spot detected at {PHASE} HV BUSHING CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.`
  - **Recommendation:** `To inspect bushing condition, perform proper cleaning and re-tighten the connection point or replace defective parts if necessary.`

#### Rule 3.3.3: LV Cable Lug Connection
- **Trigger:** `record.defect_area` matches `LV CABLE LUG CONNECTION`, `LV CABLE LUG`, or contains `LUG`.
- **Analysis:** `Thermal image above indicates hot spot detected at {PHASE} CABLE LUG CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.`
- **Recommendation:** `To inspect, perform proper cleaning, re-crimp and re-tighten the connection point or replace defective parts if necessary.`

#### Rule 3.3.4: Tank Body / Radiator / Conservator
- **Trigger:** `record.defect_area` matches `TX BODY`, `TX RADIATOR/FIN`, `CONSERVATOR TANK`, or general body.
- **Analysis:** `Thermal image above indicates hot spot detected at OVERVIEW TOP / TANK BODY.`
- **Recommendation:** `To inspect and perform dissolve gas analysis (DGA) testing and winding resistance test to pinpoint the exact cause of the thermal pattern and check for winding related heating issues. It is recommended to plan shutdown with CBM team to properly address the rectification work.`

#### Rule 3.3.5: Transformer Ultrasound (US) Discharge
- **Trigger:** `record.technology == "US"` on bushing/termination with active abnormal characteristic.
- **Analysis:** `Electrical {char} partial discharge sound detected at {COMPARTMENT}.`
- **Recommendation:** `Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. If any parts are found to be in poor condition, replacement is necessary.`
- *(Note: TEV is strictly metal-clad switchgear only; transformers do not have TEV rules).*

---

### 3.4 Ancillary Equipment (Battery Bank & Black Box)
- **Battery Bank:**
  - Analysis: `Thermal image above indicates hot spot detected at BATTERY CONNECTION. The anomaly is due to bad contact, oxidation or high resistive joint at the connection point.`
  - Recommendation: `To inspect, clean the contact surface, apply anti-corrosion grease and re-tighten the connection point. Replace defective battery cells if necessary.`
- **Black Box:**
  - Analysis: `Thermal image above indicates hot spot detected at CONTROL / JUNCTION BOX TERMINAL CONNECTION. The anomaly is due to loose or bad contact at the connection point.`
  - Recommendation: `To inspect, clean the contact surface and re-tighten the connection point. Replace defective parts if necessary.`

---

### 3.5 Overview Pages (`swg-overview`, `tx-overview`, `fp-overview`)

| Condition | Analysis Text | Recommendation Text | Cell Shading |
| :--- | :--- | :--- | :--- |
| **Defective Equipment Row** | `Please refer to the following page for details defect.` | `Please refer to the following page for details defect.` | Red (`EE0000`) |
| **Non-Defective Equipment Row** | `No Anomaly.` | `-` | Green (`00B050`) |

---

### 3.6 General Fallback Rule (Rare / Unclassified Defect Areas)
If an unknown or freeform defect area is encountered (e.g. `CT`, `EARTHING`, `FUSE CLIP`, `CONTACT FINGER`):
- **Analysis:** `Thermal image above indicates hot spot detected at {DEFECT_AREA}. The anomaly is due to loosen or bad contact at the connection point.`
- **Recommendation:** `To inspect, clean the contact surface and re-tighten the connection point. Replace defective parts if necessary.`
- Telemetry warning is logged for diagnostic awareness.
