"""Tests for substation equipment package domain models."""

from dataclasses import FrozenInstanceError
import pytest

from src.testsheet.models import (
    BatteryBankSpec,
    FireExtinguisherSpec,
    LVDBFeederSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
    ThermalReadingSpec,
    TransformerSpec,
)


def test_switchgear_panel_spec_defaults_and_immutability():
    """Verify SwitchgearPanelSpec default values and frozen immutability."""
    panel = SwitchgearPanelSpec()
    assert panel.panel_no == 1
    assert panel.panel_feeder_no == ""
    assert panel.name == ""
    assert panel.panel_type == ""
    assert panel.serial_no == ""
    assert panel.status == ""
    assert panel.load_amp == ""
    assert panel.cable_type == ""
    assert panel.heater_amp == ""

    with pytest.raises(FrozenInstanceError):
        panel.panel_no = 2  # type: ignore[misc]

    custom_panel = SwitchgearPanelSpec(
        panel_no=3,
        panel_feeder_no="F03",
        name="INCOMING 1",
        panel_type="VCB",
        serial_no="SN12345",
        status="CLOSE",
        load_amp="120A",
        cable_type="XLPE 3C 240mm2",
        heater_amp="0.5A",
    )
    assert custom_panel.panel_no == 3
    assert custom_panel.panel_feeder_no == "F03"
    assert custom_panel.name == "INCOMING 1"
    assert custom_panel.panel_type == "VCB"
    assert custom_panel.serial_no == "SN12345"
    assert custom_panel.status == "CLOSE"
    assert custom_panel.load_amp == "120A"
    assert custom_panel.cable_type == "XLPE 3C 240mm2"
    assert custom_panel.heater_amp == "0.5A"


def test_switchgear_spec_defaults_and_immutability():
    """Verify SwitchgearSpec default values and frozen immutability."""
    sg = SwitchgearSpec()
    assert sg.switchgear_type == ""
    assert sg.manufacturer == ""
    assert sg.model == ""
    assert sg.manufactured_year == ""
    assert sg.rating == ""
    assert sg.serial_no == ""
    assert sg.panels == ()

    with pytest.raises(FrozenInstanceError):
        sg.manufacturer = "TAMCO"  # type: ignore[misc]

    p1 = SwitchgearPanelSpec(panel_no=1, name="INC")
    p2 = SwitchgearPanelSpec(panel_no=2, name="TX1")
    custom_sg = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="GV3",
        manufactured_year="2020",
        rating="12kV 630A",
        serial_no="SG1001",
        panels=(p1, p2),
    )
    assert custom_sg.switchgear_type == "VCB"
    assert custom_sg.manufacturer == "TAMCO"
    assert custom_sg.model == "GV3"
    assert custom_sg.manufactured_year == "2020"
    assert custom_sg.rating == "12kV 630A"
    assert custom_sg.serial_no == "SG1001"
    assert custom_sg.panels == (p1, p2)


def test_lvdb_feeder_spec_defaults_and_immutability():
    """Verify LVDBFeederSpec default values and frozen immutability."""
    feeder = LVDBFeederSpec()
    assert feeder.channel == ""
    assert feeder.cable_type == ""

    with pytest.raises(FrozenInstanceError):
        feeder.channel = "IN1"  # type: ignore[misc]

    custom = LVDBFeederSpec(channel="OT1", cable_type="XLPE")
    assert custom.channel == "OT1"
    assert custom.cable_type == "XLPE"


def test_thermal_reading_spec_defaults_and_immutability():
    """Verify ThermalReadingSpec default values and frozen immutability."""
    th = ThermalReadingSpec()
    assert th.tmin == ""
    assert th.tmax == ""
    assert th.delta_t == ""
    assert th.avg == ""

    with pytest.raises(FrozenInstanceError):
        th.tmax = "45.0"  # type: ignore[misc]

    custom = ThermalReadingSpec(tmin="30.0", tmax="35.5", delta_t="5.5", avg="32.75")
    assert custom.tmin == "30.0"
    assert custom.tmax == "35.5"
    assert custom.delta_t == "5.5"
    assert custom.avg == "32.75"


def test_transformer_spec_defaults_and_immutability():
    """Verify TransformerSpec default values and frozen immutability."""
    tx = TransformerSpec()
    assert tx.tx_id == "Tx 1"
    assert tx.rating_kva == ""
    assert tx.construction_year == ""
    assert tx.manufacturer == ""
    assert tx.serial_no == ""
    assert tx.type == ""
    assert tx.hv_cable_type == ""
    assert tx.lv_cable_type == ""
    assert tx.hv_cable_thermal == ThermalReadingSpec()
    assert tx.hv_bushing_thermal == ThermalReadingSpec()
    assert tx.lv_cable_thermal == ThermalReadingSpec()
    assert tx.lv_bushing_thermal == ThermalReadingSpec()
    assert tx.body_thermal == ThermalReadingSpec()

    with pytest.raises(FrozenInstanceError):
        tx.rating_kva = "1000kVA"  # type: ignore[misc]

    th1 = ThermalReadingSpec(tmin="40.0", tmax="41.0", delta_t="1.0", avg="40.5")
    custom_tx = TransformerSpec(
        tx_id="Tx 2",
        rating_kva="1000kVA",
        construction_year="2018",
        manufacturer="MALONEY",
        serial_no="TX9988",
        type="HERMETICALLY SEALED",
        hv_cable_type="XLPE",
        lv_cable_type="PILC",
        hv_cable_thermal=th1,
    )
    assert custom_tx.tx_id == "Tx 2"
    assert custom_tx.rating_kva == "1000kVA"
    assert custom_tx.construction_year == "2018"
    assert custom_tx.manufacturer == "MALONEY"
    assert custom_tx.serial_no == "TX9988"
    assert custom_tx.type == "HERMETICALLY SEALED"
    assert custom_tx.hv_cable_type == "XLPE"
    assert custom_tx.lv_cable_type == "PILC"
    assert custom_tx.hv_cable_thermal == th1


def test_lvdb_spec_defaults_and_immutability():
    """Verify LVDBSpec default values, cable resolution helper, and frozen immutability."""
    lvdb = LVDBSpec()
    assert lvdb.name == "LVDB 1"
    assert lvdb.label == "LVDB"
    assert lvdb.source == "TX1"
    assert lvdb.manufacturer == ""
    assert lvdb.serial_no == ""
    assert lvdb.rating == ""
    assert lvdb.cable_type == ""
    assert lvdb.feeders == ()

    with pytest.raises(FrozenInstanceError):
        lvdb.name = "LVDB 2"  # type: ignore[misc]

    f1 = LVDBFeederSpec(channel="IN1", cable_type="XLPE")
    f2 = LVDBFeederSpec(channel="OT1", cable_type="PILC")
    f3 = LVDBFeederSpec(channel="OT2", cable_type="XLPE")
    f10 = LVDBFeederSpec(channel="OT10", cable_type="PVC")

    custom_lvdb = LVDBSpec(
        name="FEEDER PILLAR 1",
        label="FP",
        source="TX2",
        manufacturer="TAMCO",
        serial_no="LV5544",
        rating="1600A",
        cable_type="XLPE",
        feeders=(f1, f2, f3, f10),
    )
    assert custom_lvdb.name == "FEEDER PILLAR 1"
    assert custom_lvdb.label == "FP"
    assert custom_lvdb.source == "TX2"
    assert custom_lvdb.manufacturer == "TAMCO"
    assert custom_lvdb.serial_no == "LV5544"
    assert custom_lvdb.rating == "1600A"
    assert custom_lvdb.cable_type == "XLPE"
    assert len(custom_lvdb.feeders) == 4

    # get_feeder_cable resolution tests
    assert custom_lvdb.get_feeder_cable("IN1") == "XLPE"
    assert custom_lvdb.get_feeder_cable("in1") == "XLPE"
    assert custom_lvdb.get_feeder_cable("OT1") == "PILC"
    assert custom_lvdb.get_feeder_cable("OUTGOING F1") == "PILC"
    assert custom_lvdb.get_feeder_cable("FP TX1 - OUTGOING F1") == "PILC"
    assert custom_lvdb.get_feeder_cable("TH_FPOT1_MAX_PE13V") == "PILC"
    assert custom_lvdb.get_feeder_cable("OT2") == "XLPE"
    # Discriminate OT10 vs OT1
    assert custom_lvdb.get_feeder_cable("OT10") == "PVC"
    assert custom_lvdb.get_feeder_cable("OUTGOING F10") == "PVC"
    # Unmatched or missing falls back to board cable_type
    assert custom_lvdb.get_feeder_cable("OT9") == "XLPE"
    assert custom_lvdb.get_feeder_cable("") == "XLPE"
    assert custom_lvdb.get_feeder_cable("-") == "XLPE"
    assert custom_lvdb.get_feeder_cable("--") == "XLPE"


def test_battery_bank_spec_defaults_and_immutability():
    """Verify BatteryBankSpec default values and frozen immutability."""
    bb = BatteryBankSpec()
    assert bb.name == "BATTERY BANK 1"
    assert bb.manufacturer == ""
    assert bb.model == ""
    assert bb.serial_no == ""

    with pytest.raises(FrozenInstanceError):
        bb.manufacturer = "CHLORIDE"  # type: ignore[misc]

    custom_bb = BatteryBankSpec(
        name="BATTERY BANK 2",
        manufacturer="SAFT",
        model="NIFE",
        serial_no="BB7788",
    )
    assert custom_bb.name == "BATTERY BANK 2"
    assert custom_bb.manufacturer == "SAFT"
    assert custom_bb.model == "NIFE"
    assert custom_bb.serial_no == "BB7788"


def test_fire_extinguisher_spec_defaults_and_immutability():
    """Verify FireExtinguisherSpec default values and frozen immutability."""
    fe = FireExtinguisherSpec()
    assert fe.has_fire_extinguisher is False
    assert fe.expiry_date == ""
    assert fe.status == ""

    with pytest.raises(FrozenInstanceError):
        fe.has_fire_extinguisher = True  # type: ignore[misc]

    custom_fe = FireExtinguisherSpec(
        has_fire_extinguisher=True,
        expiry_date="2026-12-31",
        status="VALID",
    )
    assert custom_fe.has_fire_extinguisher is True
    assert custom_fe.expiry_date == "2026-12-31"
    assert custom_fe.status == "VALID"


def test_substation_equipment_package_defaults_and_immutability():
    """Verify SubstationEquipmentPackage defaults and frozen immutability."""
    package = SubstationEquipmentPackage()
    assert package.switchgears == ()
    assert package.transformers == ()
    assert package.lvdb_specs == ()
    assert package.battery_banks == ()
    assert package.fire_extinguisher == FireExtinguisherSpec()
    assert package.has_battery_charger is False
    assert package.has_rtu is False
    assert package.has_sf6 is False
    assert package.has_efi is False

    with pytest.raises(FrozenInstanceError):
        package.has_rtu = True  # type: ignore[misc]


def test_substation_equipment_package_computed_properties():
    """Verify computed properties on empty and populated equipment packages."""
    empty_package = SubstationEquipmentPackage()
    assert empty_package.switchgear == SwitchgearSpec()
    assert empty_package.has_switchgear is False
    assert empty_package.transformer_count == 0
    assert empty_package.lvdb_count == 0

    sg1 = SwitchgearSpec(switchgear_type="VCB", manufacturer="TAMCO", serial_no="SG001")
    sg2 = SwitchgearSpec(switchgear_type="RMU", manufacturer="ABB", serial_no="SG002")
    tx1 = TransformerSpec(tx_id="Tx 1", rating_kva="1000kVA")
    tx2 = TransformerSpec(tx_id="Tx 2", rating_kva="750kVA")
    tx3 = TransformerSpec(tx_id="Tx 3", rating_kva="500kVA")
    lvdb1 = LVDBSpec(name="LVDB 1", source="TX1")
    lvdb2 = LVDBSpec(name="LVDB 2", source="TX2")

    populated_package = SubstationEquipmentPackage(
        switchgears=(sg1, sg2),
        transformers=(tx1, tx2, tx3),
        lvdb_specs=(lvdb1, lvdb2),
    )

    assert populated_package.switchgear == sg1
    assert populated_package.has_switchgear is True
    assert populated_package.transformer_count == 3
    assert populated_package.lvdb_count == 2


def test_testsheet_data_equipment_field_compatibility():
    """Verify TestsheetData integrates equipment default and preserves backwards compatibility."""
    data = TestsheetData(
        substation_number=1,
        substation_name_erms="PE TEST",
    )
    assert data.equipment == SubstationEquipmentPackage()
    assert isinstance(data.equipment, SubstationEquipmentPackage)
    assert data.equipment.switchgear == SwitchgearSpec()
    assert data.equipment.transformer_count == 0

    custom_package = SubstationEquipmentPackage(
        has_battery_charger=True,
        has_rtu=True,
        has_sf6=True,
        has_efi=True,
    )
    data_with_eq = TestsheetData(
        substation_number=2,
        substation_name_erms="PE CUSTOM",
        equipment=custom_package,
    )
    assert data_with_eq.equipment.has_battery_charger is True
    assert data_with_eq.equipment.has_rtu is True
    assert data_with_eq.equipment.has_sf6 is True
    assert data_with_eq.equipment.has_efi is True
