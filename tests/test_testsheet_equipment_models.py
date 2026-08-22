"""Tests for substation equipment package domain models."""

from dataclasses import FrozenInstanceError
import pytest

from src.testsheet.models import (
    BatteryBankSpec,
    FireExtinguisherSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
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


def test_transformer_spec_defaults_and_immutability():
    """Verify TransformerSpec default values and frozen immutability."""
    tx = TransformerSpec()
    assert tx.tx_id == "Tx 1"
    assert tx.rating_kva == ""
    assert tx.construction_year == ""
    assert tx.manufacturer == ""
    assert tx.serial_no == ""
    assert tx.type == ""

    with pytest.raises(FrozenInstanceError):
        tx.rating_kva = "1000kVA"  # type: ignore[misc]

    custom_tx = TransformerSpec(
        tx_id="Tx 2",
        rating_kva="1000kVA",
        construction_year="2018",
        manufacturer="MALONEY",
        serial_no="TX9988",
        type="HERMETICALLY SEALED",
    )
    assert custom_tx.tx_id == "Tx 2"
    assert custom_tx.rating_kva == "1000kVA"
    assert custom_tx.construction_year == "2018"
    assert custom_tx.manufacturer == "MALONEY"
    assert custom_tx.serial_no == "TX9988"
    assert custom_tx.type == "HERMETICALLY SEALED"


def test_lvdb_spec_defaults_and_immutability():
    """Verify LVDBSpec default values and frozen immutability."""
    lvdb = LVDBSpec()
    assert lvdb.name == "LVDB 1"
    assert lvdb.label == "LVDB"
    assert lvdb.source == "TX1"
    assert lvdb.manufacturer == ""
    assert lvdb.serial_no == ""
    assert lvdb.rating == ""

    with pytest.raises(FrozenInstanceError):
        lvdb.name = "LVDB 2"  # type: ignore[misc]

    custom_lvdb = LVDBSpec(
        name="FEEDER PILLAR 1",
        label="FP",
        source="TX2",
        manufacturer="TAMCO",
        serial_no="LV5544",
        rating="1600A",
    )
    assert custom_lvdb.name == "FEEDER PILLAR 1"
    assert custom_lvdb.label == "FP"
    assert custom_lvdb.source == "TX2"
    assert custom_lvdb.manufacturer == "TAMCO"
    assert custom_lvdb.serial_no == "LV5544"
    assert custom_lvdb.rating == "1600A"


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
