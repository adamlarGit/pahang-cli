"""Reproduction script for battery bank extraction and presentation bug."""

import sys
from pathlib import Path

# Ensure worktree root is first in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.testsheet.extractor import TestsheetExtractor
from src.full_report.scan_adapters import BatteryBankScanAdapter
from src.full_report.models import build_battery_bank_scan_spec

def main():
    testsheet_path = Path(
        r"C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\TESTSHEET\KUANTAN\01. AUGUST\25-08-2026\157. PERPUSTAKAAN AWAM(VCB).xlsx"
    )
    if not testsheet_path.exists():
        print(f"Error: testsheet file not found at {testsheet_path}")
        sys.exit(2)

    extractor = TestsheetExtractor()
    data = extractor.extract_testsheet_data(testsheet_path)

    battery_banks = data.equipment.battery_banks
    print(f"Extracted battery banks count: {len(battery_banks)}")

    for i, bb in enumerate(battery_banks, 1):
        print(f"\n--- Extracted Battery {i} ---")
        print(f"  name: {bb.name}")
        print(f"  manufacturer: {bb.manufacturer}")
        print(f"  model: {bb.model}")
        print(f"  serial_no: {bb.serial_no}")

        scan_spec = build_battery_bank_scan_spec(bb)
        adapter = BatteryBankScanAdapter(scan_spec)
        res = adapter.adapt()
        item = res.items[0]
        ctx = item.context.get("batt", {})
        print(f"  Adapter context:")
        print(f"    batt['number']: {ctx.get('number')}")
        print(f"    batt['manufacturer']: {ctx.get('manufacturer')}")
        print(f"    batt['model']: {ctx.get('model')}")
        print(f"    batt['serialnumber']: {ctx.get('serialnumber')}")

    # Assertions for Battery 1
    assert len(battery_banks) >= 2, f"Expected at least 2 battery banks, got {len(battery_banks)}"
    bb1 = battery_banks[0]
    bb2 = battery_banks[1]

    ad1 = BatteryBankScanAdapter(build_battery_bank_scan_spec(bb1)).adapt().items[0].context.get("batt", {})
    ad2 = BatteryBankScanAdapter(build_battery_bank_scan_spec(bb2)).adapt().items[0].context.get("batt", {})

    errors = []
    # Check Battery 1
    if bb1.manufacturer != "BERKAT INSAF":
        errors.append(f"Battery 1 manufacturer: expected 'BERKAT INSAF', got '{bb1.manufacturer}'")
    if bb1.model != "SEB100-30-10UL":
        errors.append(f"Battery 1 model: expected 'SEB100-30-10UL', got '{bb1.model}'")
    if bb1.serial_no != "B3619":
        errors.append(f"Battery 1 serial_no: expected 'B3619', got '{bb1.serial_no}'")
    if ad1.get("number") != "1":
        errors.append(f"Battery 1 adapter number: expected '1', got '{ad1.get('number')}'")

    # Check Battery 2
    if bb2.manufacturer != "BERKAT INSAF":
        errors.append(f"Battery 2 manufacturer: expected 'BERKAT INSAF', got '{bb2.manufacturer}'")
    if bb2.model != "SEB100-30-10UL":
        errors.append(f"Battery 2 model: expected 'SEB100-30-10UL', got '{bb2.model}'")
    if bb2.serial_no not in ("", "-"):
        errors.append(f"Battery 2 serial_no: expected '-' or '', got '{bb2.serial_no}'")
    if ad2.get("number") != "2":
        errors.append(f"Battery 2 adapter number: expected '2', got '{ad2.get('number')}'")

    if errors:
        print("\nFAILURE: Reproduction caught the bug with the following mismatches:")
        for err in errors:
            print("  -", err)
        sys.exit(1)
    else:
        print("\nSUCCESS: All battery bank fields extracted and adapted correctly!")
        sys.exit(0)

if __name__ == "__main__":
    main()
