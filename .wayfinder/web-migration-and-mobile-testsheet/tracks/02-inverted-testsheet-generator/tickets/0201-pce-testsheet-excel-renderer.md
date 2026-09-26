<!-- status: open -->
Part of Track 2: .wayfinder/web-migration-and-mobile-testsheet/tracks/02-inverted-testsheet-generator/map.md

# 0201: feat(testsheet): pce testsheet excel renderer

**What to build:**
A template-based Excel renderer in `src/testsheet/renderer_pce.py` that takes an `InspectionRecord` from the database and renders a complete, valid `PCE Testsheet` Excel workbook matching the TNB client specification.

**Blocked by:** Track 1 (0102)

**Status:** Open

## Acceptance Criteria
- [ ] Implement `PceTestsheetRenderer` using `openpyxl`.
- [ ] Load base template workbook from `templates/` and populate header cells (Station, PE number, Substation name, Date, Voltage, Tester).
- [ ] Populate switchgear panel specifications, panel rows, and breaker serial numbers.
- [ ] Populate insulation resistance, contact resistance, and UltraTEV readings.
- [ ] Preserve existing cell styles, formulas, merged ranges, and print setup.
- [ ] Unit tests in `tests/testsheet/test_pce_renderer.py` comparing output against reference template.
