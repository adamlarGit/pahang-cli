import pytest
from pathlib import Path
from src.testsheet.parsers.ppu import PpuTestsheetParser
from src.core.normalizers import format_heater_amp

LEPAR_UTARA_PATH = Path(
    r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\TESTSHEET\JENGKA\01. OCTOBER\23-10-2026\35. MINI PPU LEPAR UTARA 33-11kV (VI).xlsx"
)
TAMAN_IBOL_JAYA_PATH = Path(
    r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\TESTSHEET\JENGKA\01. OCTOBER\23-10-2026\36. MINI PPU TAMAN IBOL JAYA 33-11kV (VI).xlsx"
)


def test_lepar_utara_panel_details_wiring():
    """Verify panel details extraction matches 33kV/11kV testsheet column wiring:
    - Col C: Panel Feeder No
    - Col D: Feeder Name
    - Col E: Cable Type
    - Col F: CB Position (e.g. SERVICE)
    - Col G: Breaker Status (e.g. CLOSE) -> status = 'SERVICE/CLOSE'
    - Col H: Busbar Position (e.g. MAIN)
    - Col I: Load (A)
    - Col J: Heater (A)
    - Dummy bays 6..8 without feeder names must be excluded.
    """
    if not LEPAR_UTARA_PATH.exists():
        pytest.skip("Testsheet not found")

    parser = PpuTestsheetParser()
    data = parser.extract_testsheet_data(LEPAR_UTARA_PATH)
    swg = data.equipment.switchgears[0]

    # Only populated panels 1..5 should be present, not unpopulated bays 6..8
    assert len(swg.panels) == 5, f"Expected 5 populated panels, got {len(swg.panels)}"

    p1 = swg.panels[0]
    assert p1.name == "TX 33/11kV 5MVA", f"Expected 'TX 33/11kV 5MVA', got {p1.name!r}"
    assert p1.panel_feeder_no == "32", f"Expected '32', got {p1.panel_feeder_no!r}"
    assert p1.cable_type == "NOT ACCESSIBLE", f"Expected 'NOT ACCESSIBLE', got {p1.cable_type!r}"
    assert p1.status == "SERVICE/CLOSE", f"Expected 'SERVICE/CLOSE', got {p1.status!r}"
    assert getattr(p1, "busbar_position", "") == "MAIN", f"Expected busbar 'MAIN', got {getattr(p1, 'busbar_position', '')!r}"
    assert "0.63" in p1.heater_amp or format_heater_amp(p1.heater_amp, is_vcb=True) == "ON:0.63A/OFF:0.0A"

    p2 = swg.panels[1]
    assert p2.name == "SG RENGAI", f"Expected 'SG RENGAI', got {p2.name!r}"
    assert p2.panel_feeder_no == "2", f"Expected '2', got {p2.panel_feeder_no!r}"
    assert p2.status == "SERVICE/CLOSE", f"Expected 'SERVICE/CLOSE', got {p2.status!r}"
    assert getattr(p2, "busbar_position", "") == "MAIN"


def test_taman_ibol_jaya_panel_details_wiring():
    """Verify panel details wiring for Taman Ibol Jaya."""
    if not TAMAN_IBOL_JAYA_PATH.exists():
        pytest.skip("Testsheet not found")

    parser = PpuTestsheetParser()
    data = parser.extract_testsheet_data(TAMAN_IBOL_JAYA_PATH)
    swg = data.equipment.switchgears[0]

    assert len(swg.panels) == 6, f"Expected 6 populated panels, got {len(swg.panels)}"

    p1 = swg.panels[0]
    assert p1.name == "SULTANATE LAND", f"Expected 'SULTANATE LAND', got {p1.name!r}"
    assert p1.panel_feeder_no == "1", f"Expected '1', got {p1.panel_feeder_no!r}"
    assert p1.cable_type == "NOT ACCESSIBLE", f"Expected 'NOT ACCESSIBLE', got {p1.cable_type!r}"
    assert p1.status == "SERVICE/CLOSE", f"Expected 'SERVICE/CLOSE', got {p1.status!r}"
    assert getattr(p1, "busbar_position", "") == "MAIN"

    p2 = swg.panels[1]
    assert p2.name == "SG. BANGKONG", f"Expected 'SG. BANGKONG', got {p2.name!r}"
    assert p2.status == "SERVICE/TRIP", f"Expected 'SERVICE/TRIP', got {p2.status!r}"

    p6 = swg.panels[5]
    assert p6.name == "TX MVA 33/11 KV", f"Expected 'TX MVA 33/11 KV', got {p6.name!r}"
    assert p6.panel_feeder_no == "21", f"Expected '21', got {p6.panel_feeder_no!r}"
