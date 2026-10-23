<!-- status: closed -->
# Ticket #120: fix(testsheet): exclude compartment label Column K from PT measurement detection in PpuTestsheetParser

## Parent
Part of #90

## Acceptance Criteria
- [x] Column K (the literal compartment label) is excluded from the PT measurement column loop in src/testsheet/parsers/ppu.py.
- [x] Measurement columns check includes ("L", "M", "N", "O", "R", "S", "T", "U", "V") (capturing all thermal readings, TEV, ultrasound, and remarks).
- [x] Test workbook factory in tests/fixtures/ppu_workbook_factory.py writes simulated PT measurements to Column L instead of Column K.
- [x] A regression unit test in tests/test_ppu_testsheet_parser.py validates that pre-printed "PT COMPARTMENT" text in Column K does not set has_pt_measurement = True when measurements are absent.
- [x] All unit and parser tests pass without regressions.

## Blocked by
- None (can start immediately).
