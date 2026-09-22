Part of #48

# 050: SwitchgearPanelSpec Model Extension & Sub-Row Extraction

**What to build:**
Extend the testsheet domain model and Excel extraction pipeline to capture individual chamber photos across the 4-row panel sub-grid on `PCE Testsheet`:
1. Data Model Extension (`src/testsheet/models.py` & `src/full_report/models.py`):
   - Add explicit sub-row photo attributes to `SwitchgearPanelSpec` (`src/testsheet/models.py`) and `SwitchgearPanelScanSpec` (`src/full_report/models.py`):
     - `cable_photo: int | None = None` (Row `r` Col O)
     - `breaker_photo: int | None = None` (Row `r+1` Col O)
     - `secondary_photo: int | None = None` (Row `r+1` Col P)
     - `busbar_photo: int | None = None` (Row `r+2` Col O)
     - `pt_photo: int | None = None` (Row `r+3` Col O)
     - `has_pt_measurement: bool = False` (Row `r+3` Cols K..V)
   - Update `build_switchgear_panel_scan_spec()` in `src/full_report/models.py` to propagate all 6 attributes forward.
2. Photo Extraction Seams (`src/testsheet/extractor.py`):
   - **Overview Photo Extraction (`_extract_overview_photos`)**:
     - Update to extract rows 26, 27, and 28 from Col O:
       - Row 27 Col O (`BREAKER`): Front overview photo.
       - Row 26 Col O (`CABLE`): Rear overview photo (or primary RMU overview).
       - Row 28 Col O (`TOP PANEL`): Top overview photo (or bottom RMU overview).
   - **Panel Sub-Row Extraction (`_extract_panels`)**:
     - Update `_extract_panels` to inspect the 4-row block (`r`, `r+1`, `r+2`, `r+3`) for each panel slot (`r` $\in$ {10, 14, 18, 22}):
       - Parse cable photo from `O{r}`.
       - Parse breaker photo from `O{r+1}`.
       - Parse secondary panel photo from `P{r+1}` using regex `r"(?:S\.?\s*PANEL\s*IR|IR)\s*(\d+)"` with fallback to integer parsing on bare digits.
       - Parse busbar photo from `O{r+2}`.
       - Parse PT photo from `O{r+3}`.
       - Detect PT measurements across `K{r+3}..V{r+3}` (non-empty, non-sentinel values).
     - Ensure `photo_numbers` tuple is populated with all discovered distinct photo integers in order for general compatibility.
     - Refine slot exclusion guard to ensure valid panels with photos in sub-rows `r+1..r+3` are never prematurely dropped.
3. Unit & Integration Testing:
   - Add unit tests in `tests/test_testsheet_extractor.py` asserting sub-row extraction on benchmark workbooks (`157`, `082`, `156`).
   - Specifically verify on PE 157 Perpustakaan Awam:
     - Panel 1 `secondary_photo == 520` (parsed from `'S.PANEL IR 520'`), Panel 2 `521`, Panel 3 `522`, Panel 4 `523`.
     - Panel 4 `pt_photo == 526` and `has_pt_measurement=True`, while Panels 1, 2, 3 have `pt_photo=None` and `has_pt_measurement=False`.
     - Overview extraction captures Row 27 photo `485`, Row 26 photo `488`, Row 28 photo `491`.


## Branching & Release Policy
- **Feature Branch**: Implement all changes on `feature/switchgear-topology-engine` (branched from `main`). Never commit directly to `main`.
- **Merge Gate**: Merging to `main` requires 100% green automated test suite (`pytest`) AND explicit manual review and testing sign-off by the maintainer.

**Blocked by:** None (touches `src/testsheet/` and `src/full_report/models.py`; can be executed in parallel with #49)

<!-- status: closed -->
**Status:** closed

- [x] Add `cable_photo`, `breaker_photo`, `secondary_photo`, `busbar_photo`, `pt_photo`, and `has_pt_measurement` to `SwitchgearPanelSpec` in `src/testsheet/models.py` and `SwitchgearPanelScanSpec` in `src/full_report/models.py`.
- [x] Propagate all 6 sub-row attributes in `build_switchgear_panel_scan_spec()`.
- [x] Update `_extract_overview_photos` in `src/testsheet/extractor.py` to extract rows 26, 27, and 28.
- [x] Implement Col P secondary photo regex parsing (with bare digit support) in `src/testsheet/extractor.py`.
- [x] Update `_extract_panels` in `src/testsheet/extractor.py` to extract all 4 sub-rows (`r..r+3`) and Col P.
- [x] Update panel slot exclusion logic to check all sub-row photo attributes.
- [x] Add unit tests in `tests/test_testsheet_extractor.py` verifying sub-row and overview photo extraction against benchmark workbooks (`157` including `secondary_photo == 520`, `082`, `156`).

