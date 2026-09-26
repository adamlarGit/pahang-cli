<!-- status: open -->
Part of Track 2: .wayfinder/web-migration-and-mobile-testsheet/tracks/02-inverted-testsheet-generator/map.md

# 0203: feat(testsheet): com pdf compilation & signature integration

**What to build:**
End-to-end integration combining rendered `PCE Testsheet` and `PCE VI` workbooks, applying testsheet signatures (or placeholder cleanup via `SignatureReplacementWorkflow`), and compiling the final client-deliverable PDF using the Windows COM converter.

**Blocked by:** 0201, 0202

**Status:** Open

## Acceptance Criteria
- [ ] Connect `PceTestsheetRenderer` and `PceViRenderer` into a unified `ClientTestsheetWorkflow`.
- [ ] Apply signature replacement rules (insert signature image or clean placeholder `{{signvendor}}` / `{{signtnb}}`).
- [ ] Execute conversion to `.pdf` via `BatchComSession` virtual PDF printer.
- [ ] Save output files to canonical destination: `TESTSHEET/<STATION>/<MONTH>/<DATE>/`.
- [ ] Verify generated PDFs match client page size, scaling, and orientation.
