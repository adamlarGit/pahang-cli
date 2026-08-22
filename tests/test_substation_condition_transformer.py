"""Unit tests for dynamic substation condition pairs transformer (Stage 4)."""

from pathlib import Path

from src.quick_report.substation_condition import build_substation_condition_pairs
from src.quick_report.transformer import QuickReportTransformer
from src.testsheet.models import (
    BatteryBankSpec,
    FireExtinguisherSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SubstationTestsheetPackage,
    SwitchgearSpec,
    TestsheetData,
    TransformerSpec,
)


def _make_package(
    *,
    substation_type: str = "PCE",
    building_type: str | None = "INDOOR",
    equipment: SubstationEquipmentPackage | None = None,
) -> SubstationTestsheetPackage:
    data = TestsheetData(
        substation_number=1,
        substation_name_erms="PE TEST",
        station_name="TEST STATION",
        date_str="12-08-2026",
        substation_type=substation_type,
        building_type=building_type,
        equipment=equipment or SubstationEquipmentPackage(),
    )
    return SubstationTestsheetPackage(
        testsheet_path=Path("dummy.xlsx"),
        unsorted_raw_data_dir=Path("dummy_raw"),
        station="TEST",
        month="08. AUGUST",
        date_str="12-08-2026",
        substation_number=1,
        data=data,
    )


def test_build_substation_condition_pairs_none_or_missing_data():
    """Verify fallback pair when package or data is None."""
    assert build_substation_condition_pairs(None) == [
        ("SUBSTATION OVERVIEW", "SIGNBOARD")
    ]

    pkg_no_data = SubstationTestsheetPackage(
        testsheet_path=Path("dummy.xlsx"),
        unsorted_raw_data_dir=Path("dummy_raw"),
        station="TEST",
        month="08. AUGUST",
        date_str="12-08-2026",
        substation_number=1,
        data=None,
    )
    assert build_substation_condition_pairs(pkg_no_data) == [
        ("SUBSTATION OVERVIEW", "SIGNBOARD")
    ]


def test_transformer_delegates_to_build_substation_condition_pairs():
    """Verify QuickReportTransformer._build_substation_condition_pairs delegates to build_substation_condition_pairs."""
    transformer = QuickReportTransformer()
    pkg = _make_package(
        building_type="INDOOR",
        equipment=SubstationEquipmentPackage(
            switchgears=(SwitchgearSpec(switchgear_type="AIS"),),
            transformers=(TransformerSpec(tx_id="Tx 1"),),
        ),
    )
    assert transformer._build_substation_condition_pairs(pkg) == build_substation_condition_pairs(pkg)
    assert transformer._build_substation_condition_pairs(None) == [
        ("SUBSTATION OVERVIEW", "SIGNBOARD")
    ]


def test_variant_a_1tx_indoor_pce():
    """Variant A (1 TX Indoor PCE): 1 SWG, 1 TX, 1 FP, Indoor Fire Extinguishers (SWG & TX rooms), EFI, SF6 -> 8 pairs (3 + 3 + 2)."""
    eq = SubstationEquipmentPackage(
        switchgears=(SwitchgearSpec(switchgear_type="AIS"),),
        transformers=(TransformerSpec(tx_id="Tx 1"),),
        lvdb_specs=(LVDBSpec(name="FP 1", label="FP", source="TX1"),),
        battery_banks=(),
        fire_extinguisher=FireExtinguisherSpec(has_fire_extinguisher=True, expiry_date="12/2026"),
        has_battery_charger=False,
        has_rtu=False,
        has_sf6=True,
        has_efi=True,
    )
    pkg = _make_package(substation_type="PCE", building_type="INDOOR", equipment=eq)

    pairs = build_substation_condition_pairs(pkg)
    expected = [
        ("SUBSTATION OVERVIEW", "SIGNBOARD"),
        ("SWITCHGEAR", "SWITCHGEAR NAMEPLATE"),
        ("TRANSFORMER", "TRANSFORMER NAMEPLATE"),
        ("FEEDER PILLAR", "FEEDER PILLAR NAMEPLATE"),
        ("EFI", "SF6 INDICATOR"),
        ("FIRE EXTINGUISHER\n(SWITCHGEAR ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
        ("FIRE EXTINGUISHER\n(TX ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
        ("TRANSFORMER OIL LEVEL INDICATOR", ""),
    ]
    assert pairs == expected
    assert len(pairs) == 8


def test_variant_b_2tx_attach_pce():
    """Variant B (2 TX Attach PCE): 1 SWG, 2 TX, 2 FP (TX1 & TX2), Attach Fire Extinguishers (SWG, TX1, TX2 rooms), EFI, SF6 -> 11 pairs."""
    eq = SubstationEquipmentPackage(
        switchgears=(SwitchgearSpec(switchgear_type="GIS"),),
        transformers=(
            TransformerSpec(tx_id="Tx 1"),
            TransformerSpec(tx_id="Tx 2"),
        ),
        lvdb_specs=(
            LVDBSpec(name="FP 1", label="FP", source="TX1"),
            LVDBSpec(name="FP 2", label="FP", source="TX2"),
        ),
        battery_banks=(),
        fire_extinguisher=FireExtinguisherSpec(has_fire_extinguisher=True, expiry_date="05/2027"),
        has_battery_charger=False,
        has_rtu=False,
        has_sf6=True,
        has_efi=True,
    )
    pkg = _make_package(substation_type="PCE", building_type="ATTACH", equipment=eq)

    pairs = build_substation_condition_pairs(pkg)
    expected = [
        ("SUBSTATION OVERVIEW", "SIGNBOARD"),
        ("SWITCHGEAR", "SWITCHGEAR NAMEPLATE"),
        ("TRANSFORMER 1", "TRANSFORMER 1 NAMEPLATE"),
        ("TRANSFORMER 2", "TRANSFORMER 2 NAMEPLATE"),
        ("FEEDER PILLAR TX1", "FEEDER PILLAR TX1 NAMEPLATE"),
        ("FEEDER PILLAR TX2", "FEEDER PILLAR TX2 NAMEPLATE"),
        ("EFI", "SF6 INDICATOR"),
        ("FIRE EXTINGUISHER\n(SWITCHGEAR ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
        ("FIRE EXTINGUISHER\n(TX1 ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
        ("FIRE EXTINGUISHER\n(TX2 ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
        ("TRANSFORMER 1 OIL LEVEL INDICATOR", "TRANSFORMER 2 OIL LEVEL INDICATOR"),
    ]
    assert pairs == expected
    assert len(pairs) == 11


def test_variant_c_ssu_switching_station_0tx():
    """Variant C (SSU Switching Station — 0 TX): 1 SWG, 0 TX, 0 FP, 2 Battery Chargers, RTU, Attach Fire Extinguisher (SWG room) -> 6 pairs."""
    eq = SubstationEquipmentPackage(
        switchgears=(SwitchgearSpec(switchgear_type="AIS"),),
        transformers=(),
        lvdb_specs=(),
        battery_banks=(
            BatteryBankSpec(name="BATTERY BANK 1"),
            BatteryBankSpec(name="BATTERY BANK 2"),
        ),
        fire_extinguisher=FireExtinguisherSpec(has_fire_extinguisher=True, expiry_date="01/2027"),
        has_battery_charger=True,
        has_rtu=True,
        has_sf6=False,
        has_efi=False,
    )
    pkg = _make_package(substation_type="SSU", building_type="ATTACH", equipment=eq)

    pairs = build_substation_condition_pairs(pkg)
    expected = [
        ("SUBSTATION OVERVIEW", "SIGNBOARD"),
        ("SWITCHGEAR", "SWITCHGEAR NAMEPLATE"),
        ("BATTERY CHARGER 1", "BATTERY CHARGER 1 NAMEPLATE"),
        ("BATTERY CHARGER 2", "BATTERY CHARGER 2 NAMEPLATE"),
        ("RTU", "RTU NAMEPLATE"),
        ("FIRE EXTINGUISHER\n(SWITCHGEAR ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
    ]
    assert pairs == expected
    assert len(pairs) == 6


def test_variant_d_cs_compact_substation_outdoor():
    """Variant D (CS Compact Substation — Outdoor/Compact): 1 SWG, 1 TX, 1 FP, Fire Extinguisher omitted -> 6 pairs (3 + 3)."""
    eq = SubstationEquipmentPackage(
        switchgears=(SwitchgearSpec(switchgear_type="COMPACT"),),
        transformers=(TransformerSpec(tx_id="Tx 1"),),
        lvdb_specs=(LVDBSpec(name="FP 1", label="FP", source="TX1"),),
        battery_banks=(),
        fire_extinguisher=FireExtinguisherSpec(has_fire_extinguisher=True),  # has one, but outdoor/CS suppresses it
        has_battery_charger=False,
        has_rtu=False,
        has_sf6=True,
        has_efi=True,
    )
    pkg = _make_package(substation_type="CS", building_type="OUTDOOR", equipment=eq)

    pairs = build_substation_condition_pairs(pkg)
    expected = [
        ("SUBSTATION OVERVIEW", "SIGNBOARD"),
        ("SWITCHGEAR", "SWITCHGEAR NAMEPLATE"),
        ("TRANSFORMER", "TRANSFORMER NAMEPLATE"),
        ("FEEDER PILLAR", "FEEDER PILLAR NAMEPLATE"),
        ("EFI", "SF6 INDICATOR"),
        ("TRANSFORMER OIL LEVEL INDICATOR", ""),
    ]
    assert pairs == expected
    assert len(pairs) == 6


def test_variant_e_dual_switchgear_station():
    """Variant E (Dual Switchgear Station): 2 SWG, 1 TX, 1 LVDB, Fire Extinguishers (SWG1, SWG2, TX rooms), Dual SF6 -> 10 pairs."""
    eq = SubstationEquipmentPackage(
        switchgears=(
            SwitchgearSpec(switchgear_type="AIS", model="MFR A"),
            SwitchgearSpec(switchgear_type="GIS", model="MFR B"),
        ),
        transformers=(TransformerSpec(tx_id="Tx 1"),),
        lvdb_specs=(LVDBSpec(name="LVDB 1", label="LVDB"),),
        battery_banks=(),
        fire_extinguisher=FireExtinguisherSpec(has_fire_extinguisher=True),
        has_battery_charger=False,
        has_rtu=False,
        has_sf6=True,
        has_efi=False,
    )
    pkg = _make_package(substation_type="PCE", building_type="INDOOR", equipment=eq)

    pairs = build_substation_condition_pairs(pkg)
    expected = [
        ("SUBSTATION OVERVIEW", "SIGNBOARD"),
        ("SWITCHGEAR 1", "SWITCHGEAR 1 NAMEPLATE"),
        ("SWITCHGEAR 2", "SWITCHGEAR 2 NAMEPLATE"),
        ("TRANSFORMER", "TRANSFORMER NAMEPLATE"),
        ("LVDB", "LVDB NAMEPLATE"),
        ("SF6 INDICATOR 1", "SF6 INDICATOR 2"),
        ("FIRE EXTINGUISHER\n(SWITCHGEAR 1 ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
        ("FIRE EXTINGUISHER\n(SWITCHGEAR 2 ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
        ("FIRE EXTINGUISHER\n(TX ROOM)", "FIRE EXTINGUISHER EXPIRY DATE"),
        ("TRANSFORMER OIL LEVEL INDICATOR", ""),
    ]
    assert pairs == expected
    assert len(pairs) == 10


def test_single_battery_charger_and_fallback_sources():
    """Verify single battery charger and LVDB source fallbacks."""
    eq = SubstationEquipmentPackage(
        switchgears=(),
        transformers=(),
        lvdb_specs=(
            LVDBSpec(name="LVDB 1", label="LVDB", source=""),
            LVDBSpec(name="LVDB 2", label="LVDB", source="   "),
        ),
        battery_banks=(),
        has_battery_charger=True,
        has_rtu=False,
    )
    pkg = _make_package(substation_type="INDOOR", building_type="INDOOR", equipment=eq)

    pairs = build_substation_condition_pairs(pkg)
    expected = [
        ("SUBSTATION OVERVIEW", "SIGNBOARD"),
        ("LVDB TX1", "LVDB TX1 NAMEPLATE"),
        ("LVDB TX2", "LVDB TX2 NAMEPLATE"),
        ("BATTERY CHARGER", "BATTERY CHARGER NAMEPLATE"),
    ]
    assert pairs == expected
