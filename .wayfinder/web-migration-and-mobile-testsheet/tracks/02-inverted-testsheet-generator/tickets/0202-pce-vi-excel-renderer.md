<!-- status: open -->
Part of Track 2: .wayfinder/web-migration-and-mobile-testsheet/tracks/02-inverted-testsheet-generator/map.md

# 0202: feat(testsheet): pce vi excel renderer

**What to build:**
A template-based Excel renderer in `src/testsheet/renderer_vi.py` that populates the standard `PCE VI` visual inspection checklist workbook from database `InspectionRecord` entities.

**Blocked by:** Track 1 (0102)

**Status:** Open

## Acceptance Criteria
- [ ] Implement `PceViRenderer` using `openpyxl`.
- [ ] Populate header metadata (Substation name, station, date, PO).
- [ ] Populate all visual inspection checklist line items, checking Pass/Fail/NA and adding remarks.
- [ ] Populate kejanggalan summary table for recorded visual defects.
- [ ] Preserve template cell formatting, borders, and print layout.
- [ ] Add unit tests in `tests/testsheet/test_vi_renderer.py`.
