"""Unit tests for pure domain CBM Defect Analysis and Recommendation rule engine.

Tests all 15+ empirical AZZAD defect variations at the public interface of cbm_rules.py.
Adheres strictly to the repo standard: 'The interface is the test surface'.
Zero imports of private rendering functions.
"""

from __future__ import annotations

import pytest

from src.quick_report.cbm_rules import (
    CBM_PHRASE_REGISTRY,
    generate_cbm_analysis_and_recommendation,
)
from src.quick_report.defects import CbmDefectRecord


# ─── Parametric Test Suite: 15+ Empirical AZZAD Variations ───────────────────

VARIATION_CASES = [
    # 1. DIN FP (D): Standard connection defaults to FUSE COMPARTMENT
    (
        CbmDefectRecord(
            equipment="FP (D)",
            technology="IR",
            defect_area="FUSE COMPARTMENT",
            additional_remarks="RED PHASE",
        ),
        "fp_lvdb",
        "Thermal image above indicates hot spot detected at FUSE COMPARTMENT. The anomaly is due to loosen or bad contact at the connection point.",
        "To inspect, clean the contact surface and re-tighten the connection point. Replace defective parts if necessary.",
    ),
    # 2. DIN FP (D): Cable Lug triggers re-crimp
    (
        CbmDefectRecord(
            equipment="FP (D)",
            technology="IR",
            defect_area="CABLE LUG CONNECTION",
            additional_remarks="BLUE PHASE",
        ),
        "fp_lvdb",
        "Thermal image above indicates hot spot detected at BLUE PHASE CABLE LUG CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.",
        "To inspect, clean the contact surface, re-crimp and re-tighten the connection point. Replace defective parts if necessary.",
    ),
    # 3. LVDB / FP (J): Outgoing Fuse Connection
    (
        CbmDefectRecord(
            equipment="LVDB",
            technology="IR",
            equipment_id="LVDB TX1 - OUTGOING F5",
            defect_area="OUTGOING FUSE CONNECTION",
            additional_remarks="YELLOW PHASE",
        ),
        "fp_lvdb",
        "Thermal image above indicates hot spot detected at OUTGOING FUSE CONNECTION. The anomaly is due to loosen or bad contact at the connection point.",
        "To inspect, clean the contact surface and re-tighten the connection point. Replace defective parts if necessary.",
    ),
    # 4. LVDB / FP (J): Incoming Fuse Connection
    (
        CbmDefectRecord(
            equipment="FP (J)",
            technology="IR",
            equipment_id="FP TX1 - INCOMING 1",
            defect_area="FUSE CONNECTION",
            additional_remarks="RED PHASE",
        ),
        "fp_lvdb",
        "Thermal image above indicates hot spot detected at INCOMING FUSE CONNECTION. The anomaly is due to loosen or bad contact at the connection point.",
        "To inspect, clean the contact surface and re-tighten the connection point. Replace defective parts if necessary.",
    ),
    # 5. LVDB / FP (J): Outgoing Link Connection
    (
        CbmDefectRecord(
            equipment="LVDB",
            technology="IR",
            equipment_id="LVDB TX2 - OUTGOING F2",
            defect_area="LINK CONNECTION",
            additional_remarks="BLUE PHASE",
        ),
        "fp_lvdb",
        "Thermal image above indicates hot spot detected at OUTGOING LINK CONNECTION. The anomaly is due to loosen or bad contact at the connection point.",
        "To inspect, clean the contact surface and re-tighten the connection point. Replace defective parts if necessary.",
    ),
    # 6. Switchgear: PILC Cable Replacement
    (
        CbmDefectRecord(
            equipment="VCB 11kV",
            technology="IR",
            equipment_id="FEEDER 1",
            defect_area="CABLE SWG – CABLE PILC",
            additional_remarks="RED PHASE",
        ),
        "swg",
        "Thermal image above indicates hotspot detected at CABLE SWG – CABLE PILC.",
        "To inspect and replace PILC with XLPE cable.",
    ),
    # 7. Switchgear: XLPE Cable Termination
    (
        CbmDefectRecord(
            equipment="RMU SF6",
            technology="IR",
            equipment_id="TX 1",
            defect_area="CABLE TERMINATION/CABLE XLPE",
            additional_remarks="YELLOW PHASE",
        ),
        "swg",
        "Thermal image above indicates hotspot detected at CABLE TERMINATION/CABLE XLPE. The anomaly is due to void, insulation material deterioration or defective cable.",
        "To inspect and make a new termination or replace defective parts if necessary.",
    ),
    # 8. Switchgear: Secondary Compartment Wiring Tag
    (
        CbmDefectRecord(
            equipment="VCB 11kV",
            technology="IR",
            equipment_id="BUS COUPLER",
            defect_area="SECONDARY COMPARTMENT (CABLE TAG X11:7)",
            additional_remarks="",
        ),
        "swg",
        "Thermal image above indicates hotspot detected at SECONDARY COMPARTMENT – CABLE CONNECTION (CABLE TAG X11:7). The anomaly is due to loose or bad contact at the connection point.",
        "To inspect, clean the contact surface, re-tighten the connection points or replace defective parts if necessary.",
    ),
    # 9. Switchgear: Airborne Ultrasound Corona Discharge
    (
        CbmDefectRecord(
            equipment="RMU SF6",
            technology="US",
            defect_area="CABLE COMPARTMENT",
            us_char="CORONA DISCHARGE",
            us_reading="8",
        ),
        "swg",
        "Electrical corona partial discharge sound detected at CABLE COMPARTMENT.",
        "Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. If any parts are found to be in poor condition, replacement is necessary.",
    ),
    # 10. Switchgear: Airborne Ultrasound Tracking Discharge
    (
        CbmDefectRecord(
            equipment="RMU SF6",
            technology="US",
            defect_area="BUSBAR COMPARTMENT",
            us_char="TRACKING",
            us_reading="12",
        ),
        "swg",
        "Electrical tracking partial discharge sound detected at BUSBAR COMPARTMENT.",
        "Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. If any parts are found to be in poor condition, replacement is necessary.",
    ),
    # 11. Switchgear: Airborne Ultrasound Mechanical Vibration
    (
        CbmDefectRecord(
            equipment="VCB 11kV",
            technology="US",
            defect_area="PT COMPARTMENT",
            us_char="MECHANICAL VIBRATION",
            us_reading="5",
        ),
        "swg",
        "Audible mechanical vibration sound detected at PT COMPARTMENT.",
        "Inspect the condition of the bushing and cable termination connections for any signs of electrical discharge. If any parts are found to be in poor condition, replacement is necessary.",
    ),
    # 12. Switchgear: Transient Earth Voltage (TEV) Internal Discharge
    (
        CbmDefectRecord(
            equipment="VCB 11kV",
            technology="TEV",
            defect_area="CABLE COMPARTMENT",
            tev_reading="28",
        ),
        "swg",
        "High TEV reading detected at CABLE COMPARTMENT. Based on the phase-resolved partial discharge, graph indicates internal electrical partial discharge.",
        "To inspect the bushing, cable termination and cable for sign of internal electrical partial discharge. If parts in poor condition, parts replacement are necessary. Before any rectification work is being carried out, please conduct test using TEV locater or sequence switching to find the source of high TEV reading. It is recommended to plan shutdown with CBM team.",
    ),
    # 13. Transformer: HV Cable Termination
    (
        CbmDefectRecord(
            equipment="CABLE LTX/DTX",
            technology="IR",
            defect_area="HV CABLE TERMINATION",
            additional_remarks="YELLOW PHASE",
        ),
        "tx",
        "Thermal image above indicates hot spot detected at HV CABLE TERMINATION – YELLOW PHASE. The anomaly is due to void, insulation material deterioration or defective cable.",
        "To inspect and make a new termination or replace defective parts if necessary.",
    ),
    # 14. Transformer: LV Bushing Internal Rod Inspection
    (
        CbmDefectRecord(
            equipment="LTX/DTX",
            technology="IR",
            defect_area="LV BUSHING",
            additional_remarks="RED PHASE",
        ),
        "tx",
        "Thermal image above indicates hot spot detected at RED PHASE BUSHING CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.",
        "To inspect bushing condition especially at its internal rod, perform proper cleaning and re-tighten the connection point or replace defective parts if necessary.",
    ),
    # 15. Transformer: HV Bushing Inspection
    (
        CbmDefectRecord(
            equipment="LTX/DTX",
            technology="IR",
            defect_area="HV BUSHING",
            additional_remarks="BLUE PHASE",
        ),
        "tx",
        "Thermal image above indicates hot spot detected at BLUE PHASE HV BUSHING CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.",
        "To inspect bushing condition, perform proper cleaning and re-tighten the connection point or replace defective parts if necessary.",
    ),
    # 16. Transformer: LV Cable Lug Connection (Re-crimp)
    (
        CbmDefectRecord(
            equipment="LTX/DTX",
            technology="IR",
            defect_area="LV CABLE LUG CONNECTION",
            additional_remarks="RED PHASE",
        ),
        "tx",
        "Thermal image above indicates hot spot detected at RED PHASE CABLE LUG CONNECTION. The anomaly is due to bad contact or high resistive joint at the connection point.",
        "To inspect, perform proper cleaning, re-crimp and re-tighten the connection point or replace defective parts if necessary.",
    ),
    # 17. Transformer: Tank Body DGA + Winding Resistance Test
    (
        CbmDefectRecord(
            equipment="LTX/DTX",
            technology="IR",
            defect_area="TX BODY",
            additional_remarks="",
        ),
        "tx",
        "Thermal image above indicates hot spot detected at OVERVIEW TOP / TANK BODY.",
        "To inspect and perform dissolve gas analysis (DGA) testing and winding resistance test to pinpoint the exact cause of the thermal pattern and check for winding related heating issues. It is recommended to plan shutdown with CBM team to properly address the rectification work.",
    ),
]


@pytest.mark.parametrize("record, equip_type, expected_analysis, expected_rec", VARIATION_CASES)
def test_cbm_rules_parametric_variations(
    record: CbmDefectRecord,
    equip_type: str,
    expected_analysis: str,
    expected_rec: str,
) -> None:
    analysis, rec = generate_cbm_analysis_and_recommendation(record, equipment_type=equip_type)
    assert analysis == expected_analysis
    assert rec == expected_rec


def test_swg_normal_survey_background_us_noise_guard() -> None:
    """Ensure normal survey acoustic background noise does NOT emit false-positive discharge prose."""
    record = CbmDefectRecord(
        equipment="VCB 11kV",
        technology="IR",
        defect_area="CABLE TERMINATION/CABLE XLPE",
        additional_remarks="RED PHASE",
        us_reading="2",
        us_char="NORMAL",
    )
    analysis, rec = generate_cbm_analysis_and_recommendation(record, equipment_type="swg")
    assert "corona" not in analysis.lower()
    assert "partial discharge" not in analysis.lower()
    assert "CABLE TERMINATION/CABLE XLPE" in analysis
    assert "To inspect and make a new termination" in rec


def test_swg_compound_multi_technology_defect() -> None:
    """Test multi-paragraph formatting when a panel has both IR and US defects."""
    record = CbmDefectRecord(
        equipment="RMU SF6",
        technology="IR+US",
        defect_area="CABLE TERMINATION/CABLE XLPE",
        us_char="CORONA DISCHARGE",
        us_reading="10",
    )
    analysis, rec = generate_cbm_analysis_and_recommendation(record, equipment_type="swg")
    assert "Thermal image above indicates hotspot detected at CABLE TERMINATION/CABLE XLPE." in analysis
    assert "Electrical corona partial discharge sound detected at CABLE COMPARTMENT." in analysis
    assert "\n\n" in analysis
    assert "To inspect and make a new termination or replace defective parts if necessary." in rec
    assert "Inspect the condition of the bushing and cable termination connections" in rec
    assert "\n\n" in rec


def test_overview_table_status_generation() -> None:
    """Test overview row generation for defective vs non-defective records."""
    defective_rec = CbmDefectRecord(
        equipment="FP (D)",
        technology="IR",
        defect_area="FUSE COMPARTMENT",
    )
    normal_rec = CbmDefectRecord(
        equipment="FP (D)",
        defect_area="",
        additional_remarks="TIADA DEFECT",
    )

    d_analysis, d_rec = generate_cbm_analysis_and_recommendation(
        defective_rec, equipment_type="fp_lvdb", is_overview=True
    )
    assert d_analysis == "Please refer to the following page for details defect."
    assert d_rec == "Please refer to the following page for details defect."

    n_analysis, n_rec = generate_cbm_analysis_and_recommendation(
        normal_rec, equipment_type="fp_lvdb", is_overview=True
    )
    assert n_analysis == "No Anomaly."
    assert n_rec == "-"


def test_general_fallback_for_unclassified_component() -> None:
    """Test safe general connection fallback for rare / unclassified defect areas."""
    record = CbmDefectRecord(
        equipment="UNKNOWN",
        technology="IR",
        defect_area="SOLENOID VALVE",
    )
    analysis, rec = generate_cbm_analysis_and_recommendation(record, equipment_type="unknown")
    assert "SOLENOID VALVE" in analysis
    assert "due to loosen or bad contact at the connection point" in analysis
    assert "To inspect, clean the contact surface and re-tighten the connection point" in rec


# ─── Regression: Defect Area Token Priority over Feeder Circuit Label ─────────


def test_stesen_bas_dan_teksi_outgoing_link_connection():
    """Bug regression 1: 043. STESEN BAS DAN TEKSI.
    Equipment ID has 'INCOMING 1' but defect_area is 'OUTGOING LINK CONNECTION'.
    Defect area token must dictate OUTGOING LINK CONNECTION in analysis.
    """
    rec_yellow = CbmDefectRecord(
        equipment="LVDB",
        equipment_id="LVDB TX2 - INCOMING 1",
        defect_area="OUTGOING LINK CONNECTION",
        additional_remarks="YELLOW PHASE",
        technology="IR",
        ir_reading="60.7",
        raw_measurement="60.7",
    )
    analysis_y, _ = generate_cbm_analysis_and_recommendation(rec_yellow, equipment_type="lvdb")
    assert "OUTGOING LINK CONNECTION" in analysis_y

    rec_blue = CbmDefectRecord(
        equipment="LVDB",
        equipment_id="LVDB TX2 - INCOMING 1",
        defect_area="OUTGOING LINK CONNECTION",
        additional_remarks="BLUE PHASE",
        technology="IR",
        ir_reading="73.3",
        raw_measurement="73.3",
    )
    analysis_b, _ = generate_cbm_analysis_and_recommendation(rec_blue, equipment_type="lvdb")
    assert "OUTGOING LINK CONNECTION" in analysis_b


def test_pe_kuantan_perdana_incoming_fuse_connection():
    """Bug regression 2: 049. PE KUANTAN PERDANA.
    Equipment ID has 'OUTGOING F1' but defect_area is 'INCOMING FUSE CONNECTION'.
    Defect area token must dictate INCOMING FUSE CONNECTION in analysis.
    """
    rec = CbmDefectRecord(
        equipment="LVDB",
        equipment_id="LVDB TX1 - OUTGOING F1",
        defect_area="INCOMING FUSE CONNECTION",
        additional_remarks="YELLOW PHASE",
        technology="IR",
        ir_reading="62.1",
        raw_measurement="62.1",
    )
    analysis, _ = generate_cbm_analysis_and_recommendation(rec, equipment_type="lvdb")
    assert "INCOMING FUSE CONNECTION" in analysis


def test_sri_dagangan_2_lvdb_tx2_incoming_fuse_connection():
    """Bug regression 3: 052. SRI DAGANGAN 2.
    Defect area token dictates direction regardless of equipment_id feeder number.
    """
    rec_tx1_in = CbmDefectRecord(
        equipment="LVDB",
        equipment_id="LVDB TX1 - INCOMING 2",
        defect_area="INCOMING LINK CONNECTION",
        additional_remarks="NEUTRAL",
        technology="IR",
        ir_reading="57",
        raw_measurement="57",
    )
    analysis_1, _ = generate_cbm_analysis_and_recommendation(rec_tx1_in, equipment_type="lvdb")
    assert "INCOMING LINK CONNECTION" in analysis_1

    rec_tx1_out = CbmDefectRecord(
        equipment="LVDB",
        equipment_id="LVDB TX1 - OUTGOING F5",
        defect_area="OUTGOING FUSE CONNECTION",
        additional_remarks="YELLOW PHASE",
        technology="IR",
        ir_reading="57.7",
        raw_measurement="57.7",
    )
    analysis_2, _ = generate_cbm_analysis_and_recommendation(rec_tx1_out, equipment_type="lvdb")
    assert "OUTGOING FUSE CONNECTION" in analysis_2

    rec_tx2 = CbmDefectRecord(
        equipment="LVDB",
        equipment_id="LVDB TX2 - OUTGOING F1",
        defect_area="INCOMING FUSE CONNECTION",
        additional_remarks="YELLOW PHASE",
        technology="IR",
        ir_reading="64.3",
        raw_measurement="64.3",
    )
    analysis_3, _ = generate_cbm_analysis_and_recommendation(rec_tx2, equipment_type="lvdb")
    assert "INCOMING FUSE CONNECTION" in analysis_3


def test_lvdb_droplist_tokens_contact_finger_and_busbar():
    """Test droplist tokens: CONTACT FINGER (INCOMING / OUTGOING) and BUSBAR CONNECTION."""
    rec_cf_in = CbmDefectRecord(
        equipment="LVDB",
        equipment_id="LVDB TX1 - INCOMING 1",
        defect_area="INCOMING CONTACT FINGER",
        additional_remarks="RED PHASE",
    )
    analysis, rec = generate_cbm_analysis_and_recommendation(rec_cf_in, equipment_type="lvdb")
    assert "INCOMING CONTACT FINGER" in analysis

    rec_cf_out = CbmDefectRecord(
        equipment="FP (J)",
        equipment_id="OUTGOING F6",
        defect_area="OUTGOING CONTACT FINGER",
        additional_remarks="RED PHASE",
    )
    analysis, rec = generate_cbm_analysis_and_recommendation(rec_cf_out, equipment_type="fp_lvdb")
    assert "OUTGOING CONTACT FINGER" in analysis

    rec_busbar = CbmDefectRecord(
        equipment="LVDB",
        equipment_id="LVDB TX1 - INCOMING 1",
        defect_area="BUSBAR CONNECTION",
        additional_remarks="NEUTRAL",
    )
    analysis, rec = generate_cbm_analysis_and_recommendation(rec_busbar, equipment_type="lvdb")
    assert "BUSBAR CONNECTION" in analysis

