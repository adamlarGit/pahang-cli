"""Unit tests for Full Report scan models and compartment matrix (Ticket #26 / T2.3)."""

from __future__ import annotations

import pytest

from src.core.topology import (
    BayRole,
    SwitchgearArchetype,
    SwitchgearTopologyEngine,
    VoltageClass,
    classify_bay_role,
    resolve_switchgear_archetype,
)
from src.full_report.models import (
    BatteryBankScanSpec,
    FullReportScanPackage,
    LVDBFeederScanSpec,
    LVDBScanSpec,
    SwitchgearPanelScanSpec,
    SwitchgearScanSpec,
    TransformerScanSpec,
    TRANSFORMER_STANDARD_COMPONENTS,
    build_battery_bank_scan_spec,
    build_full_report_scan_package,
    build_lvdb_scan_spec,
    build_switchgear_panel_scan_spec,
    build_switchgear_scan_spec,
    build_transformer_scan_spec,
    has_battery_bank,
    has_hv_cable_split,
    is_transition_panel,
)
from src.testsheet.models import (
    BatteryBankSpec,
    LVDBFeederSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TransformerSpec,
)


# ==============================================================================
# Slice 1: Strongly-Typed Scan Models & Parameter DTOs
# ==============================================================================

def test_switchgear_panel_scan_spec_captures_all_operating_parameters() -> None:
    """DTO captures load current, heater current, breaker status, serial no, cable type, US, and TEV."""
    spec = SwitchgearPanelScanSpec(
        panel_no=1,
        panel_feeder_no="CKN00048",
        name="BILIK SUIS PENGGUNA",
        panel_type="VCB",
        serial_no="SN-998811",
        status="SERVICE/CLOSE",
        load_amp="120A",
        heater_amp="ON:0.6A/OFF:0.0A",
        cable_type="XLPE 3C 240mm2",
        us_reading="10",
        us_char="MV",
        tev_reading="31",
        tev_ppc="1.85",
        tev_char="INTERNAL PD",
        photo_numbers=(290, 291),
        compartments=("CABLE COMPARTMENT",),
    )

    assert spec.panel_no == 1
    assert spec.panel_feeder_no == "CKN00048"
    assert spec.name == "BILIK SUIS PENGGUNA"
    assert spec.panel_type == "VCB"
    assert spec.serial_no == "SN-998811"
    assert spec.status == "SERVICE/CLOSE"
    assert spec.load_amp == "120A"
    assert spec.heater_amp == "ON:0.6A/OFF:0.0A"
    assert spec.cable_type == "XLPE 3C 240mm2"
    assert spec.us_reading == "10"
    assert spec.us_char == "MV"
    assert spec.tev_reading == "31"
    assert spec.tev_ppc == "1.85"
    assert spec.tev_char == "INTERNAL PD"
    assert spec.photo_numbers == (290, 291)
    assert spec.compartments == ("CABLE COMPARTMENT",)
    assert spec.page_count == 1


def test_switchgear_scan_spec_defaults_and_immutability() -> None:
    """SwitchgearScanSpec initializes with safe defaults and frozen immutability."""
    swg = SwitchgearScanSpec()
    assert swg.switchgear_type == ""
    assert swg.manufacturer == ""
    assert swg.model == ""
    assert swg.manufactured_year == ""
    assert swg.rating == ""
    assert swg.serial_no == ""
    assert swg.archetype == SwitchgearArchetype.RMU_STANDARD
    assert swg.voltage_class == VoltageClass.KV_11
    assert swg.overview_compartments == ()
    assert swg.panels == ()
    assert swg.photo_numbers == ()
    assert swg.panel_count == 0
    assert swg.total_page_count == 0

    with pytest.raises(AttributeError):
        swg.rating = "12kV"  # type: ignore[misc]


def test_transformer_scan_spec_provisions_7_standard_components() -> None:
    """TransformerScanSpec captures operating parameters and standard 7 components per D31 / ADR 0004."""
    tx = TransformerScanSpec(
        tx_id="Tx 1",
        rating_kva="1000",
        construction_year="2018",
        manufacturer="MTM",
        serial_no="TX-SN-1234",
        type="HERMETICALLY SEALED",
        us_reading="0",
        us_char="",
        hv_cable_type="XLPE 3C 240mm2",
        lv_cable_type="PVC 1C 500mm2",
        photo_numbers=(105, 106),
    )

    assert tx.tx_id == "Tx 1"
    assert tx.rating_kva == "1000"
    assert tx.manufacturer == "MTM"
    assert tx.components == TRANSFORMER_STANDARD_COMPONENTS
    assert tx.components == (
        "OVERVIEW",
        "OVERVIEW TOP",
        "HV BUSHING",
        "HV CABLE",
        "HV CABLE SPLIT",
        "LV BUSHING",
        "LV CABLE",
    )
    assert tx.page_count == 7


def test_transformer_has_hv_cable_split_predicate() -> None:
    """Predicate stub returns True per ADR 0004 unconditional policy."""
    assert has_hv_cable_split() is True
    tx = TransformerSpec(
        tx_id="Tx 1",
        rating_kva="1000",
        construction_year="2020",
        manufacturer="MTM",
        serial_no="SN-1",
        type="HERMETICALLY SEALED",
        us_reading="0",
        us_char="",
        hv_cable_type="XLPE 3C 240mm2",
        lv_cable_type="PVC 1C 500mm2",
        photo_numbers=(),
    )
    assert has_hv_cable_split(tx) is True


def test_lvdb_scan_spec_structure_and_feeders() -> None:
    """LVDBScanSpec captures equipment metadata and feeder ways."""
    assert LVDBFeederScanSpec is LVDBFeederSpec

    feeder1 = LVDBFeederScanSpec(channel="IN1", cable_type="PVC 4C 300mm2")
    feeder2 = LVDBFeederScanSpec(channel="OT1", cable_type="XLPE 4C 185mm2")
    lvdb = LVDBScanSpec(
        name="FP TX1",
        label="FP",
        source="TX1",
        manufacturer="Alaf Cekal",
        serial_no="FP-SN-001",
        rating="1600A",
        cable_type="PVC 4C 300mm2",
        feeders=(feeder1, feeder2),
        photo_numbers=(55,),
    )

    assert lvdb.name == "FP TX1"
    assert lvdb.label == "FP"
    assert lvdb.manufacturer == "Alaf Cekal"
    assert len(lvdb.feeders) == 2
    assert lvdb.feeders[0].channel == "IN1"
    assert lvdb.page_count == 1
    assert isinstance(lvdb, LVDBSpec)


def test_battery_bank_scan_spec_structure() -> None:
    """BatteryBankScanSpec captures manufacturer, model, serial_no, and photo numbers."""
    bb = BatteryBankScanSpec(
        name="BATTERY BANK 1",
        manufacturer="Sunpower",
        model="110V DC",
        serial_no="BB-0012",
        photo_numbers=(88,),
    )

    assert bb.name == "BATTERY BANK 1"
    assert bb.manufacturer == "Sunpower"
    assert bb.model == "110V DC"
    assert bb.serial_no == "BB-0012"
    assert bb.photo_numbers == (88,)
    assert bb.page_count == 1
    assert isinstance(bb, BatteryBankSpec)


# ==============================================================================
# Slice 2: Switchgear Classification & Compartment Matrix via SwitchgearTopologyEngine
# ==============================================================================

def test_classify_bay_role_transformer_detection() -> None:
    """Verify classify_bay_role and is_tx_feeder detect transformer feeders while excluding standard bays."""
    # Positives
    for pos in (
        "PANEL CKN01309 TX",
        "RMU SF6 PANEL CKN00051 TX 750",
        "TX 1",
        "TX B",
        "ALATUBAH",
        "TEE-OFF",
        "TRANSFORMER 1",
        "TX 300KVA",
        "300KVA",
        "1000KVA",
    ):
        assert classify_bay_role(name=pos) == BayRole.TRANSFORMER

    # Negatives
    for neg in (
        "INCOMING 1",
        "BILIK SUIS PENGGUNA",
        "TMN CENDRAWASIH 3",
        "BUS COUPLER",
        "SPARE",
        "LA SG BILUT",
    ):
        assert classify_bay_role(name=neg) != BayRole.TRANSFORMER

    # Panel objects
    tx_panel = SwitchgearPanelSpec(name="PANEL CKN01309 TX", panel_feeder_no="CKN01309")
    inc_panel = SwitchgearPanelSpec(name="INCOMING 1", panel_feeder_no="CKN01308")
    assert tx_panel.is_tx_feeder is True
    assert inc_panel.is_tx_feeder is False

    tx_scan_panel = SwitchgearPanelScanSpec(name="TX 1", panel_feeder_no="CKN01309")
    inc_scan_panel = SwitchgearPanelScanSpec(name="FEEDER 1", panel_feeder_no="CKN01308")
    assert tx_scan_panel.is_tx_feeder is True
    assert inc_scan_panel.is_tx_feeder is False


def test_is_transition_panel_detection() -> None:
    """Verify is_transition_panel identifies transition panels while excluding standard bays."""
    standard_panel = SwitchgearPanelSpec(panel_no=1, name="SSU UITM VCB 5", panel_feeder_no="CRB00764")
    transition_panel = SwitchgearPanelSpec(panel_no=2, name="TRANSITION PANEL", panel_feeder_no="CRB00765")

    assert is_transition_panel(transition_panel) is True
    assert transition_panel.is_transition_panel is True
    assert is_transition_panel("TRANSITION") is True
    assert is_transition_panel("TRANSITION PANEL") is True
    assert is_transition_panel("PANEL PERALIHAN") is True
    assert is_transition_panel("TRANSISYEN") is True
    assert is_transition_panel("TOOLS") is True
    assert is_transition_panel("TOOL COMPARTMENT") is True
    assert is_transition_panel({"name": "TRANSITION BAY"}) is True
    assert is_transition_panel({"panel_type": "TRANSITION"}) is True
    assert is_transition_panel(None) is False
    assert is_transition_panel(standard_panel) is False
    assert standard_panel.is_transition_panel is False
    assert is_transition_panel("INCOMING 1") is False

    trans_spec = build_switchgear_panel_scan_spec(transition_panel, SwitchgearArchetype.VCB_CUBICLE)
    assert trans_spec.is_transition_panel is True
    assert trans_spec.compartments == (
        "FRONT COMPARTMENT",
        "REAR COMPARTMENT",
        "BUSBAR COMPARTMENT",
    )
    assert trans_spec.page_count == 3

    std_spec = build_switchgear_panel_scan_spec(standard_panel, SwitchgearArchetype.VCB_CUBICLE)
    assert std_spec.is_transition_panel is False
    assert std_spec.compartments == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )
    assert std_spec.page_count == 4


def test_switchgear_topology_engine_compartment_resolution() -> None:
    """Verify SwitchgearTopologyEngine resolves correct compartments across archetypes."""
    incomer = SwitchgearPanelSpec(panel_no=1, name="INCOMING 1", panel_feeder_no="CKN01308")
    tx_feeder = SwitchgearPanelSpec(panel_no=4, name="PANEL CKN01309 TX", panel_feeder_no="CKN01309")

    # 1. RMU_FUSE_CANISTER (Indkom INS24)
    assert SwitchgearTopologyEngine.resolve_overview_compartments(SwitchgearArchetype.RMU_FUSE_CANISTER) == (
        "OVERVIEW",
        "OVERVIEW TOP",
    )
    assert SwitchgearTopologyEngine.resolve_panel_compartments(SwitchgearArchetype.RMU_FUSE_CANISTER, incomer) == (
        "CABLE COMPARTMENT",
    )
    assert SwitchgearTopologyEngine.resolve_panel_compartments(SwitchgearArchetype.RMU_FUSE_CANISTER, tx_feeder) == (
        "FUSE COMPARTMENT",
    )

    # 2. RMU_DUAL_CABLE_ENTRY (Tamco GR1 / Lucy)
    assert SwitchgearTopologyEngine.resolve_overview_compartments(SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY) == (
        "OVERVIEW",
        "OVERVIEW BOTTOM",
    )
    assert SwitchgearTopologyEngine.resolve_panel_compartments(SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY, incomer) == (
        "CABLE COMPARTMENT",
        "CABLE ENTRY",
    )
    assert SwitchgearTopologyEngine.resolve_panel_compartments(SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY, tx_feeder) == (
        "CABLE COMPARTMENT",
        "CABLE ENTRY",
    )

    # 3. RMU_STANDARD
    assert SwitchgearTopologyEngine.resolve_overview_compartments(SwitchgearArchetype.RMU_STANDARD) == (
        "OVERVIEW",
    )
    assert SwitchgearTopologyEngine.resolve_panel_compartments(SwitchgearArchetype.RMU_STANDARD, incomer) == (
        "CABLE COMPARTMENT",
    )

    # 4. VCB_CUBICLE
    assert SwitchgearTopologyEngine.resolve_overview_compartments(SwitchgearArchetype.VCB_CUBICLE) == (
        "OVERVIEW FRONT",
        "OVERVIEW REAR",
        "OVERVIEW TOP",
    )
    assert SwitchgearTopologyEngine.resolve_panel_compartments(SwitchgearArchetype.VCB_CUBICLE, incomer) == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )


def test_build_switchgear_panel_scan_spec_active_compartments_lockstep() -> None:
    """Verify build_switchgear_panel_scan_spec ensures compartments and page_count are in lockstep."""
    panel = SwitchgearPanelSpec(panel_no=1, name="VCB 1")
    active = ("CABLE COMPARTMENT", "BREAKER COMPARTMENT", "PT COMPARTMENT")
    spec = build_switchgear_panel_scan_spec(panel, SwitchgearArchetype.VCB_CUBICLE, active_compartments=active)

    assert spec.compartments == active
    assert spec.page_count == 3
    assert len(spec.compartments) == spec.page_count


def test_build_switchgear_scan_spec_integrates_matrix_and_page_counts() -> None:
    """Verify build_switchgear_scan_spec constructs complete spec with matrix and page counts."""
    # 1. TAMCO 4-panel switchgear (Talapia topology)
    tamco_swg = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        model="GR1",
        rating="12kV",
        serial_no="SN-TAMCO-01",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="PE KG ASLI", load_amp="100A"),
            SwitchgearPanelSpec(panel_no=2, name="TX B", load_amp="80A"),
            SwitchgearPanelSpec(panel_no=3, name="TX A", load_amp="80A"),
            SwitchgearPanelSpec(panel_no=4, name="CS LDG BILUT", load_amp="100A"),
        ),
        photo_numbers=(201, 202),
    )
    tamco_spec = build_switchgear_scan_spec(tamco_swg)

    assert tamco_spec.archetype == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert tamco_spec.overview_compartments == ("OVERVIEW", "OVERVIEW BOTTOM")
    assert tamco_spec.panel_count == 4
    # 2 overview pages + 4 panels * 2 pages = 10 pages total
    assert tamco_spec.total_page_count == 10
    for p in tamco_spec.panels:
        assert p.compartments == ("CABLE COMPARTMENT", "CABLE ENTRY")
        assert p.page_count == 2

    # 2. INDKOM 4-panel switchgear (Cenderawasih topology)
    indkom_swg = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="INDKOM",
        model="INS24",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="SPARE"),
            SwitchgearPanelSpec(panel_no=2, name="TMN CENDRAWASIH 3"),
            SwitchgearPanelSpec(panel_no=3, name="TAJ 33A"),
            SwitchgearPanelSpec(panel_no=4, name="PANEL CKN01309 TX"),
        ),
    )
    indkom_spec = build_switchgear_scan_spec(indkom_swg)

    assert indkom_spec.archetype == SwitchgearArchetype.RMU_FUSE_CANISTER
    assert indkom_spec.overview_compartments == ("OVERVIEW", "OVERVIEW TOP")
    # 2 overview pages + 4 panels * 1 page = 6 pages total
    assert indkom_spec.total_page_count == 6
    assert indkom_spec.panels[0].compartments == ("CABLE COMPARTMENT",)
    assert indkom_spec.panels[1].compartments == ("CABLE COMPARTMENT",)
    assert indkom_spec.panels[2].compartments == ("CABLE COMPARTMENT",)
    assert indkom_spec.panels[3].compartments == ("FUSE COMPARTMENT",)
    for p in indkom_spec.panels:
        assert p.page_count == 1


def test_page_count_properties_are_derived_and_immutable() -> None:
    """Verify page_count properties on panel and transformer are dynamically derived from items."""
    panel = SwitchgearPanelScanSpec(compartments=("CABLE COMPARTMENT", "CABLE ENTRY"))
    assert panel.page_count == 2

    empty_panel = SwitchgearPanelScanSpec()
    assert empty_panel.page_count == 0

    tx = TransformerScanSpec(components=("OVERVIEW", "HV BUSHING"))
    assert tx.page_count == 2


def test_build_lvdb_scan_spec_structure() -> None:
    """Verify build_lvdb_scan_spec constructs clean scan spec and maps feeders."""
    feeder = LVDBFeederSpec(channel="IN1", cable_type="PVC 4C")
    lvdb = LVDBSpec(name="FP 1", feeders=(feeder,))
    spec = build_lvdb_scan_spec(lvdb)
    assert len(spec.feeders) == 1
    assert spec.feeders[0].channel == "IN1"
    assert spec.feeders[0].cable_type == "PVC 4C"
    assert spec.page_count == 1


# ==============================================================================
# Slice 4: Battery Bank Presence (D49) & Scan Package Builder
# ==============================================================================

def test_has_battery_bank_strictly_checks_length_per_d49() -> None:
    """Verify battery bank presence is evaluated strictly via len(equipment.battery_banks) > 0 per D49."""
    # 1. Zero battery banks
    eq_empty = SubstationEquipmentPackage(battery_banks=())
    assert has_battery_bank(eq_empty) is False

    # 2. Present battery bank
    eq_with_bb = SubstationEquipmentPackage(
        battery_banks=(BatteryBankSpec(name="BATTERY BANK 1", manufacturer="Sunpower"),)
    )
    assert has_battery_bank(eq_with_bb) is True

    # 3. Multiple battery banks
    eq_multi = SubstationEquipmentPackage(
        battery_banks=(
            BatteryBankSpec(name="BATTERY 1"),
            BatteryBankSpec(name="BATTERY 2"),
        )
    )
    assert has_battery_bank(eq_multi) is True


def test_build_full_report_scan_package_with_and_without_battery() -> None:
    """Verify build_full_report_scan_package respects D49 and correctly aggregates page counts."""
    swg = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="INDKOM",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="INC"),
            SwitchgearPanelSpec(panel_no=2, name="TX 1"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", rating_kva="1000", manufacturer="MTM")
    lvdb = LVDBSpec(
        name="LVDB TX1",
        manufacturer="Tamco",
        feeders=(LVDBFeederSpec(channel="IN1"), LVDBFeederSpec(channel="OT1")),
    )

    # Substation without battery bank
    eq_no_bb = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(lvdb,),
        battery_banks=(),
    )
    pkg_no_bb = build_full_report_scan_package(eq_no_bb, substation_number=179, station_name="CENDERAWASIH NO.1")

    assert pkg_no_bb.substation_number == 179
    assert pkg_no_bb.station_name == "CENDERAWASIH NO.1"
    assert pkg_no_bb.has_switchgear is True
    assert pkg_no_bb.transformer_count == 1
    assert pkg_no_bb.lvdb_count == 1
    assert len(pkg_no_bb.lvdb_specs) == 1
    assert pkg_no_bb.has_battery_bank is False
    assert pkg_no_bb.battery_banks == ()
    # SWG: 1 overview + 2 panels * 1 = 3 pages
    # TX: 7 pages
    # LVDB: 1 page
    # Total: 3 + 7 + 1 = 11 pages
    assert pkg_no_bb.total_page_count == 11

    # Substation with battery bank
    bb = BatteryBankSpec(name="BATTERY BANK 1", manufacturer="Sunpower", photo_numbers=(88,))
    eq_with_bb = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(lvdb,),
        battery_banks=(bb,),
    )
    pkg_with_bb = build_full_report_scan_package(eq_with_bb, substation_number=5, station_name="TALAPIA")

    assert pkg_with_bb.has_battery_bank is True
    assert len(pkg_with_bb.battery_banks) == 1
    assert pkg_with_bb.battery_banks[0].name == "BATTERY BANK 1"
    assert pkg_with_bb.battery_banks[0].photo_numbers == (88,)
    # Total: 11 + 1 battery page = 12 pages
    assert pkg_with_bb.total_page_count == 12


# ==============================================================================
# Slice 5: Canonical Benchmark Topologies & Full Package Verification
# ==============================================================================

def test_canonical_benchmark_talapia() -> None:
    """Benchmark TALAPIA: TAMCO RMU (4 panels, 2 pages/panel), 1 TX (7 pages), 1 FP (1 page), 1 Battery (1 page) = 19 pages."""
    swg = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        model="GR1",
        rating="12kV, 630A",
        serial_no="SN-TAMCO-TALAPIA",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CRB00679", name="PE KG ASLI BATU BALONG", load_amp="100A", cable_type="XLPE 3C 240mm2", photo_numbers=(1,)),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CRB00679", name="TX B", load_amp="80A", cable_type="XLPE 3C 240mm2", photo_numbers=(2,)),
            SwitchgearPanelSpec(panel_no=3, panel_feeder_no="CRB00678", name="TX A", load_amp="80A", cable_type="XLPE 3C 240mm2", photo_numbers=(3,)),
            SwitchgearPanelSpec(panel_no=4, panel_feeder_no="CRB00677", name="CS LDG BILUT", load_amp="100A", cable_type="XLPE 3C 240mm2", photo_numbers=(4,)),
        ),
        photo_numbers=(100, 101),
    )
    tx = TransformerSpec(
        tx_id="Tx 1",
        rating_kva="1000",
        manufacturer="MTM",
        serial_no="SN-TX-TALAPIA",
        photo_numbers=(105,),
    )
    fp = LVDBSpec(
        name="FP TX1",
        label="FP",
        source="TX1",
        manufacturer="Alaf Cekal",
        feeders=tuple(LVDBFeederSpec(channel=f"OT{i}") for i in range(1, 11)),
        photo_numbers=(110,),
    )
    bb = BatteryBankSpec(name="BATTERY 1", manufacturer="Sunpower", photo_numbers=(120,))

    eq = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(fp,),
        battery_banks=(bb,),
    )

    pkg = build_full_report_scan_package(eq, substation_number=5, station_name="TALAPIA")

    assert pkg.substation_number == 5
    assert pkg.station_name == "TALAPIA"
    assert pkg.has_switchgear is True
    assert pkg.switchgear.archetype == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert pkg.switchgear.overview_compartments == ("OVERVIEW", "OVERVIEW BOTTOM")
    assert pkg.switchgear.panel_count == 4
    # 2 overview + 4 * 2 = 10 swg pages
    assert pkg.switchgear.total_page_count == 10
    for p in pkg.switchgear.panels:
        assert p.compartments == ("CABLE COMPARTMENT", "CABLE ENTRY")
        assert p.page_count == 2

    assert pkg.transformer_count == 1
    assert pkg.transformers[0].page_count == 7
    assert pkg.lvdb_count == 1
    assert pkg.lvdb_specs[0].page_count == 1
    assert pkg.has_battery_bank is True
    assert pkg.battery_banks[0].page_count == 1

    # Total: 10 + 7 + 1 + 1 = 19
    assert pkg.total_page_count == 19


def test_canonical_benchmark_cenderawasih() -> None:
    """Benchmark CENDERAWASIH NO.1: INDKOM RMU (3 cable, 1 fuse), 1 TX (7 pages), 1 FP, 0 Battery = 14 pages (6 SWG)."""
    swg = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="INDKOM",
        model="INS24",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CKN01308", name="SPARE", load_amp="0A"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CKN01310", name="TMN CENDRAWASIH 3", load_amp="120A"),
            SwitchgearPanelSpec(panel_no=3, panel_feeder_no="CKN01311", name="TAJ 33A LOT 11520", load_amp="95A"),
            SwitchgearPanelSpec(panel_no=4, panel_feeder_no="CKN01309", name="PANEL CKN01309 TX", load_amp="80A"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", rating_kva="1000", manufacturer="EWT")
    fp = LVDBSpec(name="FP TX1", label="FP", source="TX1")

    eq = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(fp,),
        battery_banks=(),
    )

    pkg = build_full_report_scan_package(eq, substation_number=179, station_name="CENDERAWASIH NO.1")

    assert pkg.switchgear.overview_compartments == ("OVERVIEW", "OVERVIEW TOP")
    assert pkg.switchgear.panels[0].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[1].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[2].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[3].compartments == ("FUSE COMPARTMENT",)
    # 2 overview + 4 * 1 = 6 swg pages
    assert pkg.switchgear.total_page_count == 6

    assert pkg.has_battery_bank is False
    assert pkg.battery_banks == ()
    # Total: 6 (swg) + 7 (tx) + 1 (fp) = 14 pages
    assert pkg.total_page_count == 14


def test_canonical_benchmark_telekom_tanah_putih() -> None:
    """Benchmark TELEKOM TANAH PUTIH: INDKOM RMU (3 cable, 1 fuse), 1 TX, 1 LVDB, 1 Battery = 15 pages base (6 SWG)."""
    swg = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="INDKOM",
        model="INS24",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CKN00048", name="BILIK SUIS PENGGUNA", tev_reading="31"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CKN00049", name="RADIO PENGGUNA", tev_reading="31"),
            SwitchgearPanelSpec(panel_no=3, panel_feeder_no="CKN00050", name="PENCAWANG DARAT MAKBAR", tev_reading="29"),
            SwitchgearPanelSpec(panel_no=4, panel_feeder_no="CKN00051", name="TX 750", tev_reading="28"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", rating_kva="750", manufacturer="MTM")
    lvdb = LVDBSpec(name="LVDB TX1", label="LVDB", manufacturer="Tamco")
    bb = BatteryBankSpec(name="BATTERY 1", manufacturer="Sunpower")

    eq = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(lvdb,),
        battery_banks=(bb,),
    )

    pkg = build_full_report_scan_package(eq, substation_number=144, station_name="TELEKOM TANAH PUTIH")

    assert pkg.switchgear.overview_compartments == ("OVERVIEW", "OVERVIEW TOP")
    assert pkg.switchgear.panels[0].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[1].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[2].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[3].compartments == ("FUSE COMPARTMENT",)
    # 2 overview + 4 * 1 = 6 swg pages
    assert pkg.switchgear.total_page_count == 6

    assert pkg.has_battery_bank is True
    # Base Total: 6 (swg) + 7 (tx) + 1 (lvdb) + 1 (battery) = 15 pages
    assert pkg.total_page_count == 15


def test_vcb_substation_sk_raub_indah() -> None:
    """VCB Station SK RAUB INDAH: VCB (4 standard panels, 4 compartments/panel), 0 TX, 1 FP, 1 Battery = 21 pages (19 SWG)."""
    swg = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="HV12",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CRB00764", name="SSU UITM VCB 5", load_amp="101A", us_reading="10"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CRB00722", name="LA SG BILUT", load_amp="65A"),
            SwitchgearPanelSpec(panel_no=3, panel_feeder_no="CRB00724", name="TAMAN WAWASAN", load_amp="33A"),
            SwitchgearPanelSpec(panel_no=4, panel_feeder_no="CRB00723", name="ALATUBAH", load_amp="0A"),
        ),
    )
    fp = LVDBSpec(name="FP TX1", label="FP")
    bb = BatteryBankSpec(name="BATTERY 1")

    eq = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(),
        lvdb_specs=(fp,),
        battery_banks=(bb,),
    )

    pkg = build_full_report_scan_package(eq, substation_number=9, station_name="VCB STATION SK RAUB INDAH")

    assert pkg.switchgear.overview_compartments == ("OVERVIEW FRONT", "OVERVIEW REAR", "OVERVIEW TOP")
    assert pkg.switchgear.panel_count == 4
    for p in pkg.switchgear.panels:
        assert p.compartments == (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )
        assert p.page_count == 4

    # 3 overview + 4 * 4 = 19 swg pages
    assert pkg.switchgear.total_page_count == 19
    assert pkg.transformer_count == 0
    assert pkg.lvdb_count == 1
    assert pkg.has_battery_bank is True

    # Total: 19 (swg) + 0 (tx) + 1 (fp) + 1 (battery) = 21 pages
    assert pkg.total_page_count == 21


def test_vcb_substation_with_transition_panel() -> None:
    """VCB lineup containing both standard panels and a transition panel."""
    swg = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="CKN03901", name="INCOMING 1"),
            SwitchgearPanelSpec(panel_no=2, panel_feeder_no="CKN03902", name="TRANSITION PANEL"),
            SwitchgearPanelSpec(panel_no=3, panel_feeder_no="CKN03903", name="TX 1"),
        ),
    )
    eq = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(),
        lvdb_specs=(),
        battery_banks=(),
    )
    pkg = build_full_report_scan_package(eq, substation_number=157, station_name="PERPUSTAKAAN AWAM")

    assert pkg.switchgear.panel_count == 3
    # Panel 1: standard (4 compartments)
    assert pkg.switchgear.panels[0].compartments == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )
    assert pkg.switchgear.panels[0].is_transition_panel is False
    # Panel 2: transition (3 compartments: FRONT, REAR, BUSBAR)
    assert pkg.switchgear.panels[1].compartments == (
        "FRONT COMPARTMENT",
        "REAR COMPARTMENT",
        "BUSBAR COMPARTMENT",
    )
    assert pkg.switchgear.panels[1].is_transition_panel is True
    # Panel 3: standard (4 compartments)
    assert pkg.switchgear.panels[2].compartments == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )
    assert pkg.switchgear.panels[2].is_transition_panel is False

    # 3 overviews + 4 + 3 + 4 = 14 swg pages
    assert pkg.switchgear.total_page_count == 14


def test_canonical_benchmark_perpustakaan_awam() -> None:
    """Benchmark PE 157 Perpustakaan Awam: VCB (5 panels, bay 4 has PT), 1 TX, 1 FP, 2 Battery = 34 total pages (24 SWG)."""
    swg = SwitchgearSpec(
        switchgear_type="VCB 11kV",
        manufacturer="TAMCO",
        photo_numbers=(485, 488, 491),
        panels=(
            SwitchgearPanelSpec(
                panel_no=1,
                panel_feeder_no="CKN03900",
                name="SSU IBU PEJABAT MPK CB5",
                cable_photo=498,
                breaker_photo=493,
                secondary_photo=520,
                busbar_photo=503,
            ),
            SwitchgearPanelSpec(
                panel_no=2,
                panel_feeder_no="CKN03901",
                name="SSU IBU PEJABAT MPK CB8",
                cable_photo=499,
                breaker_photo=494,
                secondary_photo=521,
                busbar_photo=504,
            ),
            SwitchgearPanelSpec(
                panel_no=3,
                panel_feeder_no="CKN03902",
                name="CS PADANG KEMUNTING",
                cable_photo=500,
                breaker_photo=495,
                secondary_photo=522,
                busbar_photo=505,
            ),
            SwitchgearPanelSpec(
                panel_no=4,
                panel_feeder_no="CKN03903",
                name="MSB",
                cable_photo=501,
                breaker_photo=496,
                secondary_photo=523,
                busbar_photo=506,
                pt_photo=526,
                has_pt_measurement=True,
            ),
            SwitchgearPanelSpec(
                panel_no=5,
                panel_feeder_no="CKN03904",
                name="TX 300KVA",
                cable_photo=502,
                breaker_photo=497,
                secondary_photo=524,
                busbar_photo=507,
            ),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", rating_kva="1000", manufacturer="EWT")
    fp = LVDBSpec(name="FP 1", label="FP", source="TX1")
    bb1 = BatteryBankSpec(name="BATTERY 1")
    bb2 = BatteryBankSpec(name="BATTERY 2")

    eq = SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(fp,),
        battery_banks=(bb1, bb2),
    )

    pkg = build_full_report_scan_package(eq, substation_number=157, station_name="PERPUSTAKAAN AWAM")

    # 3 VCB overviews: FRONT, REAR, TOP
    assert pkg.switchgear.overview_compartments == ("OVERVIEW FRONT", "OVERVIEW REAR", "OVERVIEW TOP")
    assert pkg.switchgear.panel_count == 5

    # Panels 1, 2, 3, 5: exactly 4 compartments each (no phantom PT)
    for idx in (0, 1, 2, 4):
        p = pkg.switchgear.panels[idx]
        assert p.compartments == (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )
        assert p.page_count == 4

    # Panel 4: exactly 5 compartments (includes PT)
    p4 = pkg.switchgear.panels[3]
    assert p4.compartments == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "PT COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )
    assert p4.page_count == 5

    # Total SWG: 3 overviews + 4*4 + 1*5 = 24 SWG pages
    assert pkg.switchgear.total_page_count == 24

    # Total Substation: 24 SWG + 7 TX + 1 FP + 2 Battery = 34 total scanning pages
    assert pkg.transformer_count == 1
    assert pkg.transformers[0].page_count == 7
    assert pkg.lvdb_count == 1
    assert pkg.lvdb_specs[0].page_count == 1
    assert pkg.has_battery_bank is True
    assert len(pkg.battery_banks) == 2
    assert pkg.total_page_count == 34




