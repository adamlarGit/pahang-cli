<!-- status: closed -->
# 62: fix(battery): extract composite battery details from PCE testsheet and normalize battery number

**What to build:**
Parse composite battery charger/bank details from Column J in `PCE Testsheet` rows 59-65 into clean manufacturer, model, and serial number fields, and normalize battery number to an integer index so Full Report `battery-overview.docx` renders correct metadata instead of dumping raw composite tokens.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] `parse_battery_details` correctly parses tagged, untagged, sentinel, and messy inspector strings into `(manufacturer, model, serial_no)`.
- [x] `TestsheetExtractor._extract_battery_banks()` populates unpacked `manufacturer`, `model`, and `serial_no` on `BatteryBankSpec`.
- [x] `BatteryBankScanAdapter` emits numeric `batt["number"]`, e.g. `"1"`, `"2"`.
- [x] `repro_battery_bug.py` passes cleanly on `157. PERPUSTAKAAN AWAM(VCB).xlsx`.
- [x] `CONTEXT.md` updated with `BatteryExtractionPolicy`.
- [x] Full test suite passes without regressions.
