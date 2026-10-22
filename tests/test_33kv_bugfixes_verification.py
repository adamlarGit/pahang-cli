"""Targeted unit tests verifying Bug A and Bug B 33kV pipeline bugfixes.

Bug A: Switchgear Ultrasound and TEV Readings Wiring from Testsheet
Bug B: Cable Cellar Overview in Full Report Overview & Summary
"""

from __future__ import annotations

from pathlib import Path

from src.core.topology import (
    SwitchgearArchetype,
    VoltageClass,
    resolve_overview_compartments,
)
from src.full_report.scan_adapters import SwitchgearScanAdapter
from src.quick_report.substation_condition import (
    PpuSubstationConditionPairBuilderPolicy,
)
from src.testsheet.models import (
    SubstationEquipmentPackage,
    SubstationTestsheetPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
)
from src.testsheet.parsers.ppu import PpuTestsheetParser
from tests.fixtures.ppu_workbook_factory import create_ppu_testsheet_workbook


# ==============================================================================
# BUG A TESTS: Switchgear Ultrasound and TEV Readings Wiring from Testsheet
# ==============================================================================


def test_bug_a_readings_wiring_direct_row(tmp_path: Path) -> None:
    """Verify Col R (TEV), Col S (PPC), Col T (US), Col U (US char), Col V (TEV char)

    are correctly wired into SwitchgearPanelSpec from row r.
    """
    wb_path = tmp_path / "01. PPU READINGS DIRECT.xlsx"
    parser = PpuTestsheetParser()

    custom_panels = [
        {
            "feeder_no": "3P1",
            "name": "INCOMING 33kV",
            "status": "CLOSE",
            "tev_reading": "28.5",
            "tev_ppc": "15",
            "us_reading": "12.0",
            "tev_char": "NOISE PATTERN",
        }
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=custom_panels,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    assert len(swg.panels) == 1
    panel = swg.panels[0]

    assert panel.tev_reading == "28.5"
    assert panel.tev_ppc == "15"
    assert panel.us_reading == "12.0"
    assert panel.tev_char == "NOISE PATTERN"


def test_bug_a_readings_sub_row_fallback(tmp_path: Path) -> None:
    """Verify sub-row fallback across the 6-row stride (r to r+5)

    when row r has empty readings.
    """
    wb_path = tmp_path / "02. PPU READINGS FALLBACK.xlsx"
    parser = PpuTestsheetParser()

    custom_panels = [
        {
            "feeder_no": "3P1",
            "name": "BUS SECTION 33kV",
            "status": "CLOSE",
            # Row r values intentionally empty
            "tev_reading": "",
            "tev_ppc": "",
            "us_reading": "",
            # Place readings on sub-rows (e.g. Cable row r+1, Busbar row r+2)
            "sub_rows": {
                1: {"R": "32.0", "S": "40"},
                2: {"T": "16.5", "U": "CORONA DISCHARGE"},
            },
        }
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=custom_panels,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    panel = swg.panels[0]

    assert panel.tev_reading == "32.0"
    assert panel.tev_ppc == "40"
    assert panel.us_reading == "16.5"
    assert panel.us_char == "CORONA DISCHARGE"
    assert panel.tev_char == "CORONA DISCHARGE"


def test_bug_a_tev_char_ignores_sn_and_gas_pressure(tmp_path: Path) -> None:
    """Verify Column V beginning with 'SN:' or GIS gas pressure is not treated as TEV characteristic,

    and empty Column U correctly defaults tev_char to 'NORMAL'.
    """
    wb_path = tmp_path / "03. PPU SN PREFIX.xlsx"
    parser = PpuTestsheetParser()

    custom_panels = [
        {
            "feeder_no": "3P1",
            "name": "FEEDER 33kV 1",
            "status": "CLOSE",
            "breaker_serial": "SN: VCB-2026-9999",
            # Col V row r has "SN: VCB-2026-9999"
            # Sub-row 1 has GIS gas pressure remarks
            "sub_rows": {
                1: {"V": "B: 0.87 kgf/cm²g"},
            },
        }
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=custom_panels,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    panel = swg.panels[0]

    assert panel.serial_no == "VCB-2026-9999"
    # Column U is empty, so tev_char must default to 'NORMAL', never GIS gas pressure or serial from Column V
    assert panel.tev_char == "NORMAL"


def test_bug_a_factory_default_wiring(tmp_path: Path) -> None:
    """Verify default integer panels in factory populate Col R, S, T."""
    wb_path = tmp_path / "04. PPU FACTORY DEFAULT.xlsx"
    parser = PpuTestsheetParser()

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=2,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    assert len(swg.panels) == 2

    for p in swg.panels:
        assert p.tev_reading == "0"
        assert p.tev_ppc == "0"
        assert p.us_reading == "0"


# ==============================================================================
# BUG B TESTS: Cable Cellar Overview in Full Report Overview & Summary
# ==============================================================================


def test_bug_b_canonical_overview_compartments_include_cable_cellar() -> None:
    """Verify resolve_overview_compartments includes Cable Cellar LHS and RHS

    for 33kV VCB_CUBICLE and GIS_CUBICLE.
    """
    for arch in (SwitchgearArchetype.VCB_CUBICLE, SwitchgearArchetype.GIS_CUBICLE):
        comps = resolve_overview_compartments(arch, VoltageClass.KV_33)
        assert "OVERVIEW CABLE CELLAR (LHS)" in comps
        assert "OVERVIEW CABLE CELLAR (RHS)" in comps
        # Verify order: front, rear, top, cable cellar, main busbar, reserve busbar
        assert comps == (
            "OVERVIEW FRONT (LHS)",
            "OVERVIEW FRONT (RHS)",
            "OVERVIEW REAR (LHS)",
            "OVERVIEW REAR (RHS)",
            "OVERVIEW TOP (LHS)",
            "OVERVIEW TOP (RHS)",
            "OVERVIEW CABLE CELLAR (LHS)",
            "OVERVIEW CABLE CELLAR (RHS)",
            "OVERVIEW MAIN BUSBAR (LHS)",
            "OVERVIEW MAIN BUSBAR (RHS)",
            "OVERVIEW RESERVE BUSBAR (LHS)",
            "OVERVIEW RESERVE BUSBAR (RHS)",
        )

    # 11kV should NOT have LHS/RHS cable cellar by default
    comps_11 = resolve_overview_compartments(SwitchgearArchetype.VCB_CUBICLE, VoltageClass.KV_11)
    assert comps_11 == ("OVERVIEW FRONT", "OVERVIEW REAR", "OVERVIEW TOP")


def test_bug_b_scan_adapter_with_switchgear_spec(tmp_path: Path) -> None:
    """Verify SwitchgearScanAdapter properly retrieves overview_compartments

    when self.swg is a SwitchgearSpec (not SwitchgearScanSpec), preserving Cable Cellar.
    """
    swg_spec = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="VH3",
        rating="33kV",
        overview_compartments=(
            "OVERVIEW FRONT (LHS)",
            "OVERVIEW FRONT (RHS)",
            "OVERVIEW CABLE CELLAR (LHS)",
            "OVERVIEW CABLE CELLAR (RHS)",
        ),
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="3P1", name="FEEDER 1"),
        ),
    )

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    # Create dummy template file
    (templates_dir / "swg-overview.docx").write_text("dummy")
    (templates_dir / "swg-panel.docx").write_text("dummy")

    adapter = SwitchgearScanAdapter(
        swg=swg_spec,
        substation_info={"substation_name": "TEST", "voltage_type": "33kV"},
        is_33kv=True,
        templates_dir=templates_dir,
    )

    res = adapter.adapt()
    overview_names = [item.component_name for item in res.items if item.is_overview]

    assert "OVERVIEW FRONT (LHS)" in overview_names
    assert "OVERVIEW FRONT (RHS)" in overview_names
    assert "OVERVIEW CABLE CELLAR (LHS)" in overview_names
    assert "OVERVIEW CABLE CELLAR (RHS)" in overview_names


def test_bug_b_scan_adapter_fallback_to_canonical_with_cable_cellar(tmp_path: Path) -> None:
    """Verify SwitchgearScanAdapter falls back to canonical 33kV overviews including Cable Cellar

    when overview_compartments is empty.
    """
    swg_spec = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="VH3",
        rating="33kV",
        overview_compartments=(),  # empty -> fallback
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="3P1", name="FEEDER 1"),
        ),
    )

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "swg-overview.docx").write_text("dummy")
    (templates_dir / "swg-panel.docx").write_text("dummy")

    adapter = SwitchgearScanAdapter(
        swg=swg_spec,
        substation_info={"substation_name": "TEST", "voltage_type": "33kV"},
        is_33kv=True,
        templates_dir=templates_dir,
    )

    res = adapter.adapt()
    overview_names = [item.component_name for item in res.items if item.is_overview]

    assert "OVERVIEW CABLE CELLAR (LHS)" in overview_names
    assert "OVERVIEW CABLE CELLAR (RHS)" in overview_names
    assert len(overview_names) == 12


def test_bug_b_ppu_parser_computes_has_cable_cellar(tmp_path: Path) -> None:
    """Verify extract_testsheet_data computes has_cable_cellar=True on SubstationEquipmentPackage

    when switchgear has CELLAR in overview_compartments.
    """
    wb_path = tmp_path / "05. SSU KPC GEBENG 33kV (VI).xlsx"
    parser = PpuTestsheetParser()

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=2,
        # Photos on rows 63..68 (RHS) and 69..74 (LHS)
        # Row 66 is Cable Cellar RHS (photo 56), Row 72 is Cable Cellar LHS (photo 57)
        overview_rhs_photos_33kv=[51, 52, 53, 56, 54, 55],
        overview_lhs_photos_33kv=[61, 62, 63, 57, 64, 65],
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]

    assert "OVERVIEW CABLE CELLAR (LHS)" in swg.overview_compartments
    assert "OVERVIEW CABLE CELLAR (RHS)" in swg.overview_compartments
    # Equipment package must have has_cable_cellar=True
    assert data.equipment.has_cable_cellar is True


def test_bug_b_substation_condition_pairs_from_overview_compartments() -> None:
    """Verify PpuSubstationConditionPairBuilderPolicy includes 33kV CABLE CELLAR

    when has_cable_cellar is False on package, but switchgear has CELLAR in overview_compartments.
    """
    swg_33 = SwitchgearSpec(
        switchgear_type="VCB",
        rating="33kV",
        overview_compartments=("OVERVIEW FRONT (LHS)", "OVERVIEW CABLE CELLAR (RHS)"),
        panels=(SwitchgearPanelSpec(panel_no=1, name="FEEDER 1"),),
    )

    eq = SubstationEquipmentPackage(
        switchgears=(swg_33,),
        has_cable_cellar=False,  # Unset/False explicitly
    )

    data = TestsheetData(
        substation_number=1,
        substation_name_erms="TEST SSU",
        station_name="TEST SSU",
        date_str="2026-10-07",
        equipment=eq,
    )

    pkg = SubstationTestsheetPackage(
        testsheet_path=Path("dummy.xlsx"),
        unsorted_raw_data_dir=Path("."),
        station="TEST SSU",
        month="10",
        date_str="2026-10-07",
        substation_number=1,
        data=data,
    )

    pairs = PpuSubstationConditionPairBuilderPolicy.build(pkg)
    pair_labels = [p[0] for p in pairs]

    assert "33kV CABLE CELLAR" in pair_labels
