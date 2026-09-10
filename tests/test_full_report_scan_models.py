"""Unit tests for Full Report scan models and compartment matrix (Ticket #26 / T2.3)."""

from __future__ import annotations

import pytest

from src.full_report.models import (
    BatteryBankScanSpec,
    FullReportScanPackage,
    LVDBFeederScanSpec,
    LVDBScanSpec,
    SwitchgearCategory,
    SwitchgearPanelScanSpec,
    SwitchgearScanSpec,
    TransformerScanSpec,
    TRANSFORMER_STANDARD_COMPONENTS,
    VCB_STANDARD_COMPARTMENTS,
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
        page_count=1,
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
    assert swg.category == SwitchgearCategory.OTHER_RMU
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


def test_lvdb_scan_spec_structure_and_feeders() -> None:
    """LVDBScanSpec captures equipment metadata and feeder ways."""
    feeder1 = LVDBFeederScanSpec(channel="IN1", cable_type="PVC 4C 300mm2", load_amp="250A")
    feeder2 = LVDBFeederScanSpec(channel="OT1", cable_type="XLPE 4C 185mm2", load_amp="45A")
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


# ==============================================================================
# Slice 2: Switchgear Classification & Compartment Matrix per D26
# ==============================================================================

def test_classify_switchgear_across_all_four_categories() -> None:
    """Verify classify_switchgear accurately categorizes equipment across the 4 canonical categories."""
    from src.full_report.models import classify_switchgear

    # 1. INDKOM
    assert classify_switchgear(switchgear_type="RMU SF6", manufacturer="INDKOM") == SwitchgearCategory.INDKOM
    assert classify_switchgear(switchgear_type="RMU", manufacturer="Indkom Engineering") == SwitchgearCategory.INDKOM

    # 2. TAMCO / LUCY (including SSE LUCY)
    assert classify_switchgear(switchgear_type="RMU SF6", manufacturer="TAMCO") == SwitchgearCategory.TAMCO_LUCY
    assert classify_switchgear(switchgear_type="RMU SF6", manufacturer="Tamco GR1") == SwitchgearCategory.TAMCO_LUCY
    assert classify_switchgear(switchgear_type="RMU SF6", manufacturer="LUCY") == SwitchgearCategory.TAMCO_LUCY
    assert classify_switchgear(switchgear_type="RMU SF6", manufacturer="SSE LUCY") == SwitchgearCategory.TAMCO_LUCY

    # 3. OTHER RMU (SIEMENS, ABB, generic RMU)
    assert classify_switchgear(switchgear_type="RMU SF6", manufacturer="SIEMENS 8DJH") == SwitchgearCategory.OTHER_RMU
    assert classify_switchgear(switchgear_type="RMU SF6", manufacturer="ABB SafeRing") == SwitchgearCategory.OTHER_RMU
    assert classify_switchgear(switchgear_type="RMU OIL", manufacturer="") == SwitchgearCategory.OTHER_RMU

    # 4. VCB (takes precedence even if manufacturer is TAMCO or other)
    assert classify_switchgear(switchgear_type="VCB", manufacturer="TAMCO") == SwitchgearCategory.VCB
    assert classify_switchgear(switchgear_type="12kV VCB", manufacturer="EPE") == SwitchgearCategory.VCB
    assert classify_switchgear(switchgear_type="VCB 11kV", manufacturer="") == SwitchgearCategory.VCB


def test_is_tx_feeder_detection() -> None:
    """Verify is_tx_feeder detects transformer feeders while excluding standard bays."""
    from src.full_report.models import is_tx_feeder

    # Positives
    assert is_tx_feeder(name="PANEL CKN01309 TX") is True
    assert is_tx_feeder(name="RMU SF6 PANEL CKN00051 TX 750") is True
    assert is_tx_feeder(name="TX 1") is True
    assert is_tx_feeder(name="TX B") is True
    assert is_tx_feeder(name="ALATUBAH") is True
    assert is_tx_feeder(panel_type="TEE-OFF") is True
    assert is_tx_feeder(name="TRANSFORMER 1") is True

    # Negatives
    assert is_tx_feeder(name="INCOMING 1") is False
    assert is_tx_feeder(name="BILIK SUIS PENGGUNA") is False
    assert is_tx_feeder(name="TMN CENDRAWASIH 3") is False
    assert is_tx_feeder(name="BUS COUPLER") is False
    assert is_tx_feeder(name="SPARE") is False
    assert is_tx_feeder(name="LA SG BILUT") is False


def test_switchgear_compartment_matrix_indkom() -> None:
    """INDKOM: TX feeder -> FUSE COMPARTMENT, others -> CABLE COMPARTMENT, overview TOP."""
    from src.full_report.models import (
        resolve_overview_compartments,
        resolve_switchgear_compartments,
    )

    incomer = SwitchgearPanelSpec(panel_no=1, name="INCOMING 1", panel_feeder_no="CKN01308")
    tx_feeder = SwitchgearPanelSpec(panel_no=4, name="PANEL CKN01309 TX", panel_feeder_no="CKN01309")

    # Overview
    assert resolve_overview_compartments(SwitchgearCategory.INDKOM) == ("OVERVIEW", "OVERVIEW TOP")

    # Panels
    assert resolve_switchgear_compartments(SwitchgearCategory.INDKOM, incomer) == ("CABLE COMPARTMENT",)
    assert resolve_switchgear_compartments(SwitchgearCategory.INDKOM, tx_feeder) == ("FUSE COMPARTMENT",)


def test_switchgear_compartment_matrix_tamco_lucy() -> None:
    """TAMCO/LUCY: OVERVIEW BOTTOM + CABLE COMPARTMENT + CABLE ENTRY per D26."""
    from src.full_report.models import (
        resolve_overview_compartments,
        resolve_switchgear_compartments,
    )

    incomer = SwitchgearPanelSpec(panel_no=1, name="PE KG ASLI BATU BALONG", panel_feeder_no="CRB00679")
    tx_feeder = SwitchgearPanelSpec(panel_no=2, name="TX B", panel_feeder_no="CRB00679")

    # Overview
    assert resolve_overview_compartments(SwitchgearCategory.TAMCO_LUCY) == ("OVERVIEW", "OVERVIEW BOTTOM")

    # Panels (both incomer and TX get CABLE COMPARTMENT and CABLE ENTRY)
    assert resolve_switchgear_compartments(SwitchgearCategory.TAMCO_LUCY, incomer) == (
        "CABLE COMPARTMENT",
        "CABLE ENTRY",
    )
    assert resolve_switchgear_compartments(SwitchgearCategory.TAMCO_LUCY, tx_feeder) == (
        "CABLE COMPARTMENT",
        "CABLE ENTRY",
    )


def test_switchgear_compartment_matrix_other_rmu() -> None:
    """Other RMUs: CABLE COMPARTMENT and OVERVIEW TOP."""
    from src.full_report.models import (
        resolve_overview_compartments,
        resolve_switchgear_compartments,
    )

    incomer = SwitchgearPanelSpec(panel_no=1, name="INCOMING 1")
    tx_feeder = SwitchgearPanelSpec(panel_no=3, name="TX 1")

    # Overview
    assert resolve_overview_compartments(SwitchgearCategory.OTHER_RMU) == ("OVERVIEW", "OVERVIEW TOP")

    # Panels
    assert resolve_switchgear_compartments(SwitchgearCategory.OTHER_RMU, incomer) == ("CABLE COMPARTMENT",)
    assert resolve_switchgear_compartments(SwitchgearCategory.OTHER_RMU, tx_feeder) == ("CABLE COMPARTMENT",)


def test_switchgear_compartment_matrix_vcb() -> None:
    """VCB: Evaluated per panel emitting its 7 standard compartments per D26."""
    from src.full_report.models import (
        resolve_overview_compartments,
        resolve_switchgear_compartments,
    )

    panel = SwitchgearPanelSpec(panel_no=1, name="SSU UITM VCB 5", panel_feeder_no="CRB00764")

    # Overview
    assert resolve_overview_compartments(SwitchgearCategory.VCB) == ("OVERVIEW", "OVERVIEW TOP")

    # Panel emits standard 7 compartments
    compartments = resolve_switchgear_compartments(SwitchgearCategory.VCB, panel)
    assert compartments == VCB_STANDARD_COMPARTMENTS
    assert len(compartments) == 7
    assert compartments == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "PT COMPARTMENT",
        "SECONDARY COMPARTMENT",
        "BACK COMPARTMENT",
        "FRONT COMPARTMENT",
    )


# ==============================================================================
# Slice 3: Manufacturer-Driven Scanning Page Count Rules per D29
# ==============================================================================

def test_resolve_panel_page_count_rules_per_d29() -> None:
    """Verify page count resolution follows D29 across all 4 categories."""
    from src.full_report.models import resolve_panel_page_count

    incomer = SwitchgearPanelSpec(panel_no=1, name="INCOMING 1")
    tx_feeder = SwitchgearPanelSpec(panel_no=4, name="TX 1")

    # 1. TAMCO / LUCY: 2 scanning pages per panel
    assert resolve_panel_page_count(SwitchgearCategory.TAMCO_LUCY, incomer) == 2
    assert resolve_panel_page_count(SwitchgearCategory.TAMCO_LUCY, tx_feeder) == 2

    # 2. INDKOM: 1 scanning page per panel
    assert resolve_panel_page_count(SwitchgearCategory.INDKOM, incomer) == 1
    assert resolve_panel_page_count(SwitchgearCategory.INDKOM, tx_feeder) == 1

    # 3. OTHER RMU: 1 scanning page per panel
    assert resolve_panel_page_count(SwitchgearCategory.OTHER_RMU, incomer) == 1
    assert resolve_panel_page_count(SwitchgearCategory.OTHER_RMU, tx_feeder) == 1

    # 4. VCB: 1 scanning page for each active compartment
    # Default without explicit active compartments emits 7
    assert resolve_panel_page_count(SwitchgearCategory.VCB, incomer) == 7
    # Custom active compartments (e.g. Cable, Breaker, PT)
    assert resolve_panel_page_count(
        SwitchgearCategory.VCB,
        incomer,
        active_compartments=["CABLE COMPARTMENT", "BREAKER COMPARTMENT", "PT COMPARTMENT"],
    ) == 3


def test_build_switchgear_scan_spec_integrates_matrix_and_page_counts() -> None:
    """Verify build_switchgear_scan_spec constructs complete spec with matrix and page counts."""
    from src.full_report.models import build_switchgear_scan_spec

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

    assert tamco_spec.category == SwitchgearCategory.TAMCO_LUCY
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

    assert indkom_spec.category == SwitchgearCategory.INDKOM
    assert indkom_spec.overview_compartments == ("OVERVIEW", "OVERVIEW TOP")
    # 2 overview pages + 4 panels * 1 page = 6 pages total
    assert indkom_spec.total_page_count == 6
    assert indkom_spec.panels[0].compartments == ("CABLE COMPARTMENT",)
    assert indkom_spec.panels[1].compartments == ("CABLE COMPARTMENT",)
    assert indkom_spec.panels[2].compartments == ("CABLE COMPARTMENT",)
    assert indkom_spec.panels[3].compartments == ("FUSE COMPARTMENT",)
    for p in indkom_spec.panels:
        assert p.page_count == 1


# ==============================================================================
# Slice 4: Battery Bank Presence (D49) & Scan Package Builder
# ==============================================================================

def test_has_battery_bank_strictly_checks_length_per_d49() -> None:
    """Verify battery bank presence is evaluated strictly via len(equipment.battery_banks) > 0 per D49."""
    from src.full_report.models import has_battery_bank

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
    from src.full_report.models import build_full_report_scan_package

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
    assert pkg_no_bb.has_battery_bank is False
    assert pkg_no_bb.battery_banks == ()
    # SWG: 2 overview + 2 panels * 1 = 4 pages
    # TX: 7 pages
    # LVDB: 1 page
    # Total: 4 + 7 + 1 = 12 pages
    assert pkg_no_bb.total_scan_pages == 12

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
    # Total: 12 + 1 battery page = 13 pages
    assert pkg_with_bb.total_scan_pages == 13


# ==============================================================================
# Slice 5: Canonical Benchmark Topologies & Full Package Verification
# ==============================================================================

def test_canonical_benchmark_talapia() -> None:
    """Benchmark TALAPIA: TAMCO RMU (4 panels, 2 pages/panel), 1 TX (7 pages), 1 FP (1 page), 1 Battery (1 page) = 19 pages."""
    from src.full_report import build_full_report_scan_package

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
    assert pkg.switchgear.category == SwitchgearCategory.TAMCO_LUCY
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
    assert pkg.lvdbs[0].page_count == 1
    assert pkg.has_battery_bank is True
    assert pkg.battery_banks[0].page_count == 1

    # Total: 10 + 7 + 1 + 1 = 19
    assert pkg.total_scan_pages == 19


def test_canonical_benchmark_cenderawasih() -> None:
    """Benchmark CENDERAWASIH NO.1: INDKOM RMU (3 cable, 1 fuse), 1 TX (7 pages), 1 FP, 0 Battery = 14 pages."""
    from src.full_report import build_full_report_scan_package

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

    assert pkg.switchgear.category == SwitchgearCategory.INDKOM
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
    assert pkg.total_scan_pages == 14


def test_canonical_benchmark_telekom_tanah_putih() -> None:
    """Benchmark TELEKOM TANAH PUTIH: INDKOM RMU (3 cable, 1 fuse), 1 TX, 1 LVDB, 1 Battery = 15 pages."""
    from src.full_report import build_full_report_scan_package

    swg = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="INDKOM",
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

    assert pkg.switchgear.category == SwitchgearCategory.INDKOM
    assert pkg.switchgear.panels[0].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[1].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[2].compartments == ("CABLE COMPARTMENT",)
    assert pkg.switchgear.panels[3].compartments == ("FUSE COMPARTMENT",)

    assert pkg.has_battery_bank is True
    # Total: 6 (swg) + 7 (tx) + 1 (lvdb) + 1 (battery) = 15 pages
    assert pkg.total_scan_pages == 15


def test_vcb_substation_sk_raub_indah() -> None:
    """VCB Station SK RAUB INDAH: VCB (4 panels, 7 compartments/panel), 0 TX, 1 FP, 1 Battery = 32 pages."""
    from src.full_report import build_full_report_scan_package

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

    assert pkg.switchgear.category == SwitchgearCategory.VCB
    assert pkg.switchgear.overview_compartments == ("OVERVIEW", "OVERVIEW TOP")
    assert pkg.switchgear.panel_count == 4
    for p in pkg.switchgear.panels:
        assert p.compartments == VCB_STANDARD_COMPARTMENTS
        assert p.page_count == 7

    # 2 overview + 4 * 7 = 30 swg pages
    assert pkg.switchgear.total_page_count == 30
    assert pkg.transformer_count == 0
    assert pkg.lvdb_count == 1
    assert pkg.has_battery_bank is True

    # Total: 30 (swg) + 0 (tx) + 1 (fp) + 1 (battery) = 32 pages
    assert pkg.total_scan_pages == 32




