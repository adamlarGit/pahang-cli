"""Tests for 33kV Power Transformer extraction, classification, and LVDB parsing."""

from __future__ import annotations

import logging
from pathlib import Path
import pytest

from src.testsheet.models import (
    LVDBSpec,
    PowerTransformerSpec,
    ThermalReadingSpec,
    TransformerSpec,
)
from src.testsheet.parsers.ppu import (
    PpuTestsheetParser,
    classify_transformer_rating,
)
from tests.fixtures.ppu_workbook_factory import create_ppu_testsheet_workbook


def test_power_transformer_spec_model_hierarchy() -> None:
    """Verify PowerTransformerSpec is a frozen dataclass subclass of TransformerSpec."""
    assert issubclass(PowerTransformerSpec, TransformerSpec)

    ptx = PowerTransformerSpec(
        tx_id="TX 1",
        rating_kva="10MVA",
        manufacturer="MTM",
        model="15-201",
        serial_no="SN-001",
        hv_ultrasound="0",
        lv_ultrasound="0",
        marshalling_kiosk_photo=550,
        conservator_photo=547,
        body_photo=555,
        cooling_fin_photo=546,
        hv_cable_photo=560,
        lv_cable_photo=554,
        marshalling_kiosk_temp=ThermalReadingSpec(tmin="35.8", tmax="36.0", delta_t="0.2", avg="35.9"),
        conservator_temp=ThermalReadingSpec(tmin="41.0", tmax="41.5", delta_t="0.5", avg="41.25"),
        body_temp=ThermalReadingSpec(tmin="43.0", tmax="43.9", delta_t="0.9", avg="43.45"),
        cooling_fin_temp=ThermalReadingSpec(tmin="43.3", tmax="43.7", delta_t="0.4", avg="43.5"),
        photo_numbers=(560, 554, 550, 547, 555, 546),
    )

    # 100% backward compatible: isinstance(TransformerSpec) is True
    assert isinstance(ptx, TransformerSpec)
    assert isinstance(ptx, PowerTransformerSpec)

    # Base TransformerSpec fields
    assert ptx.tx_id == "TX 1"
    assert ptx.rating_kva == "10MVA"
    assert ptx.manufacturer == "MTM"
    assert ptx.model == "15-201"
    assert ptx.serial_no == "SN-001"
    assert ptx.photo_numbers == (560, 554, 550, 547, 555, 546)

    # Body temp / body thermal synchronization
    assert ptx.body_thermal == ptx.body_temp
    assert ptx.body_temp.tmax == "43.9"

    # Ultrasound sync to us_reading
    assert ptx.us_reading == "0"
    assert ptx.hv_ultrasound == "0"
    assert ptx.lv_ultrasound == "0"

    # Auxiliary photos and temperatures
    assert ptx.marshalling_kiosk_photo == 550
    assert ptx.conservator_photo == 547
    assert ptx.body_photo == 555
    assert ptx.cooling_fin_photo == 546
    assert ptx.hv_cable_photo == 560
    assert ptx.lv_cable_photo == 554
    assert ptx.marshalling_kiosk_temp.tmax == "36.0"
    assert ptx.conservator_temp.tmax == "41.5"
    assert ptx.cooling_fin_temp.tmax == "43.7"

    # Frozen immutability
    with pytest.raises(AttributeError):
        ptx.rating_kva = "20MVA"  # type: ignore[misc]


def test_classify_transformer_rating(caplog: pytest.LogCaptureFixture) -> None:
    """Verify classification logic handles >= 5 MVA, 100-1000 kVA, LOCAL TX, and logs warnings."""
    # >= 5 MVA -> PowerTransformerSpec (True)
    assert classify_transformer_rating("5MVA") is True
    assert classify_transformer_rating("10MVA") is True
    assert classify_transformer_rating("15MVA") is True
    assert classify_transformer_rating("30MVA") is True
    assert classify_transformer_rating("15/20 MVA") is True
    assert classify_transformer_rating("7.5 MVA") is True
    assert classify_transformer_rating("5000kVA") is True
    assert classify_transformer_rating("10", unit_hint="MVA") is True

    # 100 - 1000 kVA -> standard TransformerSpec (False)
    assert classify_transformer_rating("100kVA") is False
    assert classify_transformer_rating("300kVA") is False
    assert classify_transformer_rating("500 kVA") is False
    assert classify_transformer_rating("1000kVA") is False
    assert classify_transformer_rating("300", unit_hint="KVA") is False

    # Labeled LOCAL TX -> always standard TransformerSpec (False)
    assert classify_transformer_rating("10MVA", tx_id="LOCAL TX") is False
    assert classify_transformer_rating("300kVA", tx_id="Local TX") is False

    # Out-of-range or ambiguous ratings -> warning logged and defaults to False
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        # < 5 MVA in MVA
        assert classify_transformer_rating("2MVA", tx_id="TX 1") is False
        assert "Out-of-range" in caplog.text or "rating '2MVA'" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        # Out-of-range in kVA (50 kVA < 100 kVA)
        assert classify_transformer_rating("50kVA", tx_id="TX 2") is False
        assert "Out-of-range" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        # Out-of-range in kVA (2500 kVA between 1000 kVA and 5 MVA)
        assert classify_transformer_rating("2500kVA", tx_id="TX 3") is False
        assert "Out-of-range" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        # Unrecognized / empty rating
        assert classify_transformer_rating("", tx_id="TX 4") is False
        assert classify_transformer_rating("UNKNOWN", tx_id="TX 4") is False


def test_extract_tx_sheet_power_and_local_transformers(tmp_path: Path) -> None:
    """Verify parsing a TX worksheet with 2 Power Transformers, 1 Local TX, and Station Service LVDB."""
    wb_path = tmp_path / "01. PPU APMM 33-11kV (VI).xlsx"

    tx_specs = [
        {
            "tx_id": "TX 1",
            "model": "15-201",
            "manufacturer": "MTM",
            "rating": "10MVA",
            "serial_no": "P/791/07/15024",
            "load_amp": "151",
            "cable_type": "XLPE",
            "hv_ultrasound": "0",
            "lv_ultrasound": "0",
            "hv_photo": 560,
            "lv_photo": 554,
            "mk_photo": 550,
            "ct_photo": 547,
            "body_photo": 555,
            "cf_photo": "546/548",
            "hv_cable_thermal": {"tmin": "36.4", "tmax": "37.2", "delta_t": "0.8", "avg": "36.8"},
            "lv_cable_thermal": {"tmin": "36.0", "tmax": "36.1", "delta_t": "0.1", "avg": "36.05"},
            "marshalling_kiosk_temp": {"tmin": "35.8", "tmax": "36.0", "delta_t": "0.2", "avg": "35.9"},
            "conservator_temp": {"tmin": "41.0", "tmax": "41.5", "delta_t": "0.5", "avg": "41.25"},
            "body_temp": {"tmin": "43.0", "tmax": "43.9", "delta_t": "0.9", "avg": "43.45"},
            "cooling_fin_temp": {"tmin": "43.3", "tmax": "43.7", "delta_t": "0.4", "avg": "43.5"},
        },
        {
            "tx_id": "TX 2",
            "model": "15-201",
            "manufacturer": "MTM",
            "rating": "10MVA",
            "serial_no": "P/791/07/15022",
            "load_amp": "94",
            "cable_type": "XLPE",
            "hv_ultrasound": "0",
            "lv_ultrasound": "0",
            "hv_photo": 577,
            "lv_photo": 573,
            "mk_photo": 567,
            "ct_photo": 565,
            "body_photo": 568,
            "cf_photo": "562/564",
            "hv_cable_thermal": {"tmin": "34.9", "tmax": "35.4", "delta_t": "0.5", "avg": "35.15"},
            "lv_cable_thermal": {"tmin": "36.2", "tmax": "36.4", "delta_t": "0.2", "avg": "36.3"},
            "marshalling_kiosk_temp": {"tmin": "36.1", "tmax": "36.2", "delta_t": "0.1", "avg": "36.15"},
            "conservator_temp": {"tmin": "38.2", "tmax": "38.7", "delta_t": "0.5", "avg": "38.45"},
            "body_temp": {"tmin": "43.8", "tmax": "45.1", "delta_t": "1.3", "avg": "44.45"},
            "cooling_fin_temp": {"tmin": "42.7", "tmax": "42.9", "delta_t": "0.2", "avg": "42.8"},
        },
    ]

    local_tx_spec = {
        "tx_id": "LOCAL TX",
        "model": "H/S",
        "manufacturer": "MTM",
        "rating": "300kVA",
        "serial_no": "T1/579/07/3584",
        "load_amp": "1",
        "cable_type": "XLPE",
        "hv_ultrasound": "0",
        "hv_photo": 585,
        "lv_photo": 588,
        "body_photo": 582,
        "hv_cable_thermal": {"tmin": "36.0", "tmax": "36.3", "delta_t": "0.3", "avg": "36.15"},
        "lv_cable_thermal": {"tmin": "33.8", "tmax": "33.9", "delta_t": "0.1", "avg": "33.85"},
        "body_temp": {"tmin": "39.3", "tmax": "40.5", "delta_t": "1.2", "avg": "39.9"},
    }

    lvdb_details = {
        "rating": "800A",
        "photo": 544,
        "serial_no": "OFP AL 11",
        "model": "J-SLOTTED",
        "manufacturer": "TOPRANK",
    }

    create_ppu_testsheet_workbook(
        path=wb_path,
        transformers=tx_specs,
        local_tx=local_tx_spec,
        lvdb_details=lvdb_details,
    )

    parser = PpuTestsheetParser()
    data = parser.extract_testsheet_data(wb_path)
    pkg = data.equipment

    # Total transformers = 3 (TX 1, TX 2, Local TX)
    assert len(pkg.transformers) == 3
    assert pkg.transformer_count == 3

    # TX 1: PowerTransformerSpec
    tx1 = pkg.transformers[0]
    assert isinstance(tx1, PowerTransformerSpec)
    assert tx1.tx_id == "TX 1"
    assert tx1.rating_kva == "10MVA"
    assert tx1.model == "15-201"
    assert tx1.manufacturer == "MTM"
    assert tx1.serial_no == "P/791/07/15024"
    assert tx1.load_amp == "151"
    assert tx1.hv_cable_type == "XLPE"
    assert tx1.lv_cable_type == "XLPE"
    assert tx1.hv_ultrasound == "0"
    assert tx1.lv_ultrasound == "0"
    assert tx1.hv_cable_photo == 560
    assert tx1.lv_cable_photo == 554
    assert tx1.marshalling_kiosk_photo == 550
    assert tx1.conservator_photo == 547
    assert tx1.body_photo == 555
    assert tx1.cooling_fin_photo == 546
    assert tx1.marshalling_kiosk_temp.tmax == "36.0"
    assert tx1.conservator_temp.tmax == "41.5"
    assert tx1.body_temp.tmax == "43.9"
    assert tx1.body_thermal.tmax == "43.9"
    assert tx1.cooling_fin_temp.tmax == "43.7"
    assert 560 in tx1.photo_numbers
    assert 554 in tx1.photo_numbers
    assert 550 in tx1.photo_numbers
    assert 547 in tx1.photo_numbers
    assert 555 in tx1.photo_numbers
    assert 546 in tx1.photo_numbers
    assert 548 in tx1.photo_numbers

    # TX 2: PowerTransformerSpec
    tx2 = pkg.transformers[1]
    assert isinstance(tx2, PowerTransformerSpec)
    assert tx2.tx_id == "TX 2"
    assert tx2.rating_kva == "10MVA"
    assert tx2.model == "15-201"
    assert tx2.manufacturer == "MTM"
    assert tx2.serial_no == "P/791/07/15022"
    assert tx2.load_amp == "94"
    assert tx2.hv_cable_type == "XLPE"
    assert tx2.lv_cable_type == "XLPE"
    assert tx2.hv_cable_photo == 577
    assert tx2.lv_cable_photo == 573
    assert tx2.body_temp.tmax == "45.1"

    # Local TX: standard TransformerSpec (NOT PowerTransformerSpec)
    local_tx = pkg.transformers[2]
    assert type(local_tx) is TransformerSpec
    assert not isinstance(local_tx, PowerTransformerSpec)
    assert local_tx.tx_id == "LOCAL TX"
    assert local_tx.rating_kva == "300kVA"
    assert local_tx.model == "H/S"
    assert local_tx.manufacturer == "MTM"
    assert local_tx.serial_no == "T1/579/07/3584"
    assert local_tx.load_amp == "1"
    assert local_tx.hv_cable_type == "XLPE"
    assert local_tx.lv_cable_type == "XLPE"
    assert local_tx.body_thermal.tmax == "40.5"
    assert 585 in local_tx.photo_numbers
    assert 588 in local_tx.photo_numbers
    assert 582 in local_tx.photo_numbers

    # Station Service LVDB
    assert len(pkg.lvdb_specs) == 1
    assert pkg.lvdb_count == 1
    lvdb = pkg.lvdb_specs[0]
    assert isinstance(lvdb, LVDBSpec)
    assert lvdb.name == "LVDB 1"
    assert lvdb.rating == "800A"
    assert lvdb.photo_numbers == (544,)
    assert lvdb.serial_no == "OFP AL 11"
    assert lvdb.model == "J-SLOTTED"
    assert lvdb.manufacturer == "TOPRANK"


def test_extract_tx_sheet_ssu_tolerance_missing_tx_sheet(tmp_path: Path) -> None:
    """Verify SSU stations without a TX sheet produce empty transformers and lvdb_specs."""
    wb_path = tmp_path / "03. SSU LYNAS 33kV (VI).xlsx"
    create_ppu_testsheet_workbook(
        path=wb_path,
        substation_name="SSU LYNAS 33kV",
        include_tx_sheet=False,
    )

    parser = PpuTestsheetParser()
    data = parser.extract_testsheet_data(wb_path)
    assert data.equipment.transformers == ()
    assert data.equipment.transformer_count == 0
    assert data.equipment.lvdb_specs == ()
    assert data.equipment.lvdb_count == 0


def test_extract_tx_sheet_ssu_tolerance_empty_tx_sheet(tmp_path: Path) -> None:
    """Verify SSU stations with an empty/unpopulated TX sheet produce empty transformers."""
    wb_path = tmp_path / "04. SSU EMPTY TX.xlsx"
    create_ppu_testsheet_workbook(
        path=wb_path,
        substation_name="SSU EMPTY TX",
        include_tx_sheet=True,
        transformers=[],
        local_tx=None,
        lvdb_details=None,
    )

    parser = PpuTestsheetParser()
    data = parser.extract_testsheet_data(wb_path)
    assert data.equipment.transformers == ()
    assert data.equipment.transformer_count == 0
    assert data.equipment.lvdb_specs == ()


def test_extract_tx_sheet_out_of_range_handling(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Verify out-of-range transformer ratings log warnings and fallback to standard TransformerSpec."""
    wb_path = tmp_path / "05. PPU OUT OF RANGE.xlsx"
    tx_specs = [
        {
            "tx_id": "TX 1",
            "rating": "2MVA",  # < 5 MVA
            "serial_no": "SN-001",
        },
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        transformers=tx_specs,
    )

    parser = PpuTestsheetParser()
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        data = parser.extract_testsheet_data(wb_path)

    assert len(data.equipment.transformers) == 1
    # Fallback to standard TransformerSpec
    assert type(data.equipment.transformers[0]) is TransformerSpec
    assert not isinstance(data.equipment.transformers[0], PowerTransformerSpec)
    assert "Out-of-range" in caplog.text


def test_extract_tx_sheet_four_power_transformers(tmp_path: Path) -> None:
    """Verify extracting a substation with 4 Power Transformers and a Local TX."""
    wb_path = tmp_path / "06. PPU 4TX.xlsx"
    tx_specs = [
        {"tx_id": f"TX {i}", "rating": "30MVA", "serial_no": f"SN-{i}", "model": f"MD-{i}"}
        for i in range(1, 5)
    ]
    local_tx_spec = {"tx_id": "LOCAL TX", "rating": "500kVA", "serial_no": "SN-LOCAL"}

    create_ppu_testsheet_workbook(
        path=wb_path,
        transformers=tx_specs,
        local_tx=local_tx_spec,
    )

    parser = PpuTestsheetParser()
    data = parser.extract_testsheet_data(wb_path)
    assert len(data.equipment.transformers) == 5

    for i in range(4):
        tx = data.equipment.transformers[i]
        assert isinstance(tx, PowerTransformerSpec)
        assert tx.tx_id == f"TX {i + 1}"
        assert tx.rating_kva == "30MVA"

    local_tx = data.equipment.transformers[4]
    assert type(local_tx) is TransformerSpec
    assert local_tx.tx_id == "LOCAL TX"
    assert local_tx.rating_kva == "500kVA"


def test_extract_tx_sheet_real_field_workbook() -> None:
    """Verify parsing against the real field testsheet if present in environment."""
    real_path = Path(
        r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\TESTSHEET\GEBENG\01. OCTOBER\07-10-2026\01. PPU APMM 33-11kV (VI).xlsx"
    )
    if not real_path.exists():
        pytest.skip("Real field testsheet not available on filesystem")

    parser = PpuTestsheetParser()
    data = parser.extract_testsheet_data(real_path)

    # 3 transformers: TX 1, TX 2, Local TX
    assert len(data.equipment.transformers) == 3
    tx1, tx2, ltx = data.equipment.transformers

    assert isinstance(tx1, PowerTransformerSpec)
    assert tx1.tx_id == "TX 1"
    assert tx1.rating_kva == "10MVA"
    assert tx1.model == "15-201"
    assert tx1.manufacturer == "MTM"
    assert tx1.serial_no == "P/791/07/15024"
    assert tx1.hv_cable_photo == 560
    assert tx1.lv_cable_photo == 554
    assert tx1.marshalling_kiosk_photo == 550
    assert tx1.conservator_photo == 547
    assert tx1.body_photo == 555
    assert tx1.cooling_fin_photo == 546
    assert 548 in tx1.photo_numbers

    assert isinstance(tx2, PowerTransformerSpec)
    assert tx2.tx_id == "TX 2"
    assert tx2.rating_kva == "10MVA"
    assert tx2.serial_no == "P/791/07/15022"

    assert type(ltx) is TransformerSpec
    assert ltx.tx_id in ("LOCAL TX", "Local TX")
    assert ltx.rating_kva == "300kVA"
    assert ltx.model == "H/S"
    assert ltx.manufacturer == "MTM"
    assert ltx.serial_no == "T1/579/07/3584"

    # LVDB
    assert len(data.equipment.lvdb_specs) == 1
    lvdb = data.equipment.lvdb_specs[0]
    assert lvdb.rating == "800A"
    assert lvdb.photo_numbers == (544,)
    assert lvdb.serial_no == "OFP AL 11"
    assert lvdb.model == "J-SLOTTED"
    assert lvdb.manufacturer == "TOPRANK"
