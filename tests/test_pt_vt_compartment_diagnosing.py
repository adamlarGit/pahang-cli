from pathlib import Path
import pytest
from src.core.contract import normalize_swg_compartment, is_swg_compartment_us_eligible, is_swg_compartment_tev_eligible
from src.quick_report.prpd import _matches_compartment, find_pregenerated_prpd_graph
from src.postprocessing.sound_embedder import CHAMBER_COMPONENT_KEYWORDS
from src.testsheet.models import SwitchgearPanelSpec
from src.full_report.scan_adapters import SwitchgearScanAdapter


def test_normalize_swg_compartment_pt_vt_precedence():
    """Ensure VT and PT Chamber variants normalize to PT COMPARTMENT, not BREAKER COMPARTMENT."""
    assert normalize_swg_compartment("VT Chamber") == "PT COMPARTMENT"
    assert normalize_swg_compartment("VT CHAMBER") == "PT COMPARTMENT"
    assert normalize_swg_compartment("VT_CHAMBER") == "PT COMPARTMENT"
    assert normalize_swg_compartment("PT Chamber") == "PT COMPARTMENT"
    assert normalize_swg_compartment("PT CHAMBER") == "PT COMPARTMENT"
    assert normalize_swg_compartment("PT_CHAMBER") == "PT COMPARTMENT"
    assert normalize_swg_compartment("VOLTAGE TRANSFORMER") == "PT COMPARTMENT"
    assert normalize_swg_compartment("VOLTAGE_TRANSFORMER") == "PT COMPARTMENT"
    assert normalize_swg_compartment("POTENTIAL TRANSFORMER") == "PT COMPARTMENT"
    assert normalize_swg_compartment("POTENTIAL_TRANSFORMER") == "PT COMPARTMENT"
    # Ensure breaker and chamber variants that are NOT PT/VT remain BREAKER COMPARTMENT
    assert normalize_swg_compartment("BREAKER") == "BREAKER COMPARTMENT"
    assert normalize_swg_compartment("VCB") == "BREAKER COMPARTMENT"
    assert normalize_swg_compartment("CB") == "BREAKER COMPARTMENT"
    assert normalize_swg_compartment("CHAMBER") == "BREAKER COMPARTMENT"
    assert normalize_swg_compartment("FRONT") == "FRONT COMPARTMENT"


def test_is_swg_compartment_eligibility():
    """Ensure VT Chamber and PT Chamber are recognized as TEV and US eligible."""
    assert is_swg_compartment_tev_eligible("VT Chamber") is True
    assert is_swg_compartment_tev_eligible("VT_CHAMBER") is True
    assert is_swg_compartment_us_eligible("VT Chamber") is True
    assert is_swg_compartment_us_eligible("VT_CHAMBER") is True


def test_matches_compartment_pt_vt_isolation():
    """Ensure PT COMPARTMENT matches VT Chamber tokens and does not collide with Breaker."""
    assert _matches_compartment("PT COMPARTMENT", "VT_CHAMBER") is True
    assert _matches_compartment("PT COMPARTMENT", "VT Chamber") is True
    assert _matches_compartment("PT COMPARTMENT", "CIRCUIT_BREAKER") is False
    assert _matches_compartment("BREAKER COMPARTMENT", "VT_CHAMBER") is False
    assert _matches_compartment("BREAKER COMPARTMENT", "VT Chamber") is False

    # Non-PT tokens containing substring "PT" must NOT falsely match PT COMPARTMENT
    assert _matches_compartment("PT COMPARTMENT", "EMPTY") is False
    assert _matches_compartment("PT COMPARTMENT", "ADAPTER") is False
    assert _matches_compartment("PT COMPARTMENT", "OPTICAL") is False
    assert _matches_compartment("BREAKER COMPARTMENT", "EMPTY") is False
    assert _matches_compartment("CABLE COMPARTMENT", "EMPTY") is False
    assert _matches_compartment("BUSBAR COMPARTMENT", "EMPTY") is False


def test_sound_embedder_pt_chamber_keywords():
    """Ensure sound embedder keywords cover spaced and underscore variants of VT and PT."""
    pt_keywords = CHAMBER_COMPONENT_KEYWORDS["PT"]
    upper_keywords = tuple(k.upper() for k in pt_keywords)
    assert any(k in "VT CHAMBER" for k in upper_keywords)
    assert any(k in "VT_CHAMBER" for k in upper_keywords)
    assert any(k in "VOLTAGE TRANSFORMER" for k in upper_keywords)
    assert any(k in "VOLTAGE_TRANSFORMER" for k in upper_keywords)
    assert any(k in "POTENTIAL TRANSFORMER" for k in upper_keywords)
    assert any(k in "POTENTIAL_TRANSFORMER" for k in upper_keywords)


def test_scan_adapter_no_leakage_for_unmeasured_pt_compartment():
    """When a panel does not have a PT measurement, ScanAdapter returns empty string for PRPD."""
    from src.testsheet.models import SwitchgearSpec

    panel = SwitchgearPanelSpec(
        panel_no=1,
        panel_feeder_no="1S0",
        name="BUS SECTION",
        us_reading="5",
        tev_reading="5",
        has_pt_measurement=False,
    )
    swg = SwitchgearSpec(panels=[panel], switchgear_type="GIS", rating="36kV")

    adapter = SwitchgearScanAdapter(
        swg=swg,
        is_33kv=True,
        prpd_catalog={
            "swg": {
                1: {
                    "compartments": {
                        "CIRCUIT_BREAKER": {"us": "path/to/cb_us.png", "tev": "path/to/cb_tev.png"}
                    }
                }
            }
        },
    )

    us_p, tev_p = adapter._resolve_prpd(
        panel_no=1,
        feeder_no="1S0",
        compartment="PT COMPARTMENT",
    )
    assert us_p == ""
    assert tev_p == ""


def test_switchgear_scan_adapter_pt_reading_empty_no_breaker_leakage():
    """When panel.pt_us_reading == '', SwitchgearScanAdapter yields empty/dashed reading and not the breaker reading for PT COMPARTMENT."""
    from src.testsheet.models import SwitchgearSpec

    panel = SwitchgearPanelSpec(
        panel_no=1,
        panel_feeder_no="1S0",
        name="BUS SECTION",
        us_reading="12",
        tev_reading="18",
        pt_us_reading="",
        pt_tev_reading="",
        pt_tev_ppc="",
        has_pt_measurement=False,
    )
    swg = SwitchgearSpec(panels=[panel], switchgear_type="GIS", rating="36kV")
    adapter = SwitchgearScanAdapter(swg=swg, is_33kv=True)
    res = adapter.adapt()
    pt_item = next((it for it in res.items if it.context.get("panel", {}).get("area") == "PT COMPARTMENT"), None)
    assert pt_item is not None
    panel_ctx = pt_item.context["panel"]
    # Must NOT leak breaker reading "12" or "18"
    assert panel_ctx["us"]["reading"] != "12"
    assert panel_ctx["tev"]["reading"] != "18"
    assert panel_ctx["us"]["reading"] in ("", "-")
    assert panel_ctx["tev"]["reading"] in ("", "-")
    assert panel_ctx["tev"]["ppc"] in ("", "-")


def test_lynas_reference_vt_chamber_prpd_resolution():
    """Verify reference Lynas survey data resolves Panel 3 and Panel 7 PT COMPARTMENT to VT Chamber graphs."""
    raw_us_dir = Path(
        r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\RAW MATERIAL\GEBENG\01. OCTOBER\07-10-2026\03. SSU LYNAS 33kV (VI)\RAW DATA\US"
    )
    if not raw_us_dir.exists():
        pytest.skip("Lynas raw survey data not found on disk")

    g3 = find_pregenerated_prpd_graph(
        survey_root=raw_us_dir,
        panel_no=3,
        feeder_no="1S5",
        panel_name="CONSUMER 1",
        compartment="PT COMPARTMENT",
        tech="US",
    )
    assert g3 is not None
    assert g3.name == "GIS_33KV_1S5_CONSUMER_1_VT_CHAMBER_US.png"

    g7 = find_pregenerated_prpd_graph(
        survey_root=raw_us_dir,
        panel_no=7,
        feeder_no="2S5",
        panel_name="CONSUMER 2",
        compartment="PT COMPARTMENT",
        tech="US",
    )
    assert g7 is not None
    assert g7.name == "GIS_33KV_2S5_CONSUMER_2_VT_CHAMBER_US.png"


def test_ppu_parser_pt_readings_extraction():
    """Ensure 33kV testsheet parser extracts PT readings from row r+3 into SwitchgearPanelSpec."""
    from src.testsheet.parsers.ppu import PpuTestsheetParser

    ts_path = Path(
        r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\TESTSHEET\GEBENG\01. OCTOBER\07-10-2026\03. SSU LYNAS 33kV (VI).xlsx"
    )
    if not ts_path.exists():
        pytest.skip("Lynas testsheet not found on disk")

    data = PpuTestsheetParser().extract_testsheet_data(ts_path)
    swg = data.equipment.switchgears[0]
    # Panel 7 (2S5 CONSUMER 2) has PT measurements at row 54: Col R=5.0, Col T=0.0
    panel_7 = next((p for p in swg.panels if p.panel_feeder_no == "2S5"), None)
    assert panel_7 is not None
    assert getattr(panel_7, "pt_us_reading", None) in ("0", "0.0"), f"Expected '0' or '0.0', got {panel_7.pt_us_reading!r}"
    assert getattr(panel_7, "pt_tev_reading", None) in ("5", "5.0"), f"Expected '5' or '5.0', got {panel_7.pt_tev_reading!r}"


def test_switchgear_scan_adapter_pt_context_binding():
    """Ensure SwitchgearScanAdapter binds dedicated PT readings when generating PT COMPARTMENT context."""
    from src.testsheet.models import SwitchgearSpec

    panel = SwitchgearPanelSpec(
        panel_no=3,
        panel_feeder_no="1S5",
        name="CONSUMER 1",
        us_reading="12",
        tev_reading="18",
        pt_us_reading="2",
        pt_tev_reading="6",
        has_pt_measurement=True,
    )
    swg = SwitchgearSpec(panels=[panel], switchgear_type="GIS", rating="36kV")

    adapter = SwitchgearScanAdapter(
        swg=swg,
        is_33kv=True,
        prpd_catalog={
            "swg": {
                3: {
                    "compartments": {
                        "VT_CHAMBER": {"us": "path/to/vt_us.png", "tev": "path/to/vt_tev.png"}
                    }
                }
            }
        },
    )

    res = adapter.adapt()
    pt_item = next((it for it in res.items if it.context.get("panel", {}).get("area") == "PT COMPARTMENT"), None)
    assert pt_item is not None, "Expected PT COMPARTMENT scan item in adapter results"
    panel_ctx = pt_item.context["panel"]
    assert panel_ctx["us"]["reading"] == "2", f"Expected '2', got {panel_ctx['us']['reading']!r}"
    assert panel_ctx["tev"]["reading"] == "6", f"Expected '6', got {panel_ctx['tev']['reading']!r}"
    assert panel_ctx["us"]["prpd"] == "path/to/vt_us.png"
    assert panel_ctx["tev"]["prpd"] == "path/to/vt_tev.png"
