Part of #48

Blocked by: #49, #50

# 051: Scan Adapters & Executive Summary Census Integration

**What to build:**
Integrate the switchgear topology engine directly into Full Report scan adapters and the Executive Summary Census builder:
1. Scan Spec Models (`src/full_report/models.py`):
   - Update `build_switchgear_scan_spec` and `build_switchgear_panel_scan_spec` to store `archetype: SwitchgearArchetype`, `voltage_class: VoltageClass`, and resolved `compartments: tuple[str, ...]`.
   - Overview compartments in `SwitchgearScanSpec` resolved via `engine.resolve_overview_compartments(...)`.
2. Scan Adapter 1-to-1 Photo Assignment & Strict Zero-Fallback (`src/full_report/scan_adapters.py`):
   - In `SwitchgearScanAdapter`, map each resolved compartment directly to its explicit sub-row photo attribute:
     - `"BREAKER COMPARTMENT"` $\to$ `panel.breaker_photo`
     - `"FRONT COMPARTMENT"` $\to$ `panel.breaker_photo`
     - `"CABLE COMPARTMENT"` $\to$ `panel.cable_photo`
     - `"REAR COMPARTMENT"` $\to$ `panel.cable_photo`
     - `"BUSBAR COMPARTMENT"` $\to$ `panel.busbar_photo`
     - `"PT COMPARTMENT"` $\to$ `panel.pt_photo`
     - `"SECONDARY COMPARTMENT"` $\to$ `panel.secondary_photo`
     - RMU compartments mapped to available sub-row photo or `None`.
   - **Overview Photo Mapping**:
     - VCB / GIS: map `OVERVIEW FRONT` (Row 27 photo), `OVERVIEW REAR` (Row 26 photo), `OVERVIEW TOP` (Row 28 photo).
     - RMU: map `OVERVIEW` (Row 26 photo), `OVERVIEW TOP` or `OVERVIEW BOTTOM` (Row 28 photo).
   - **Serial Number Policy**:
     - `SwitchgearScanAdapter` passes `panel.serial_no` directly into render context for panel scanning pages (pre-populated by `TestsheetExtractor`: board serial for RMU SF6, individual panel/breaker serial for VCB and RMU Oil).
   - **Strict Zero-Fallback**:
     - Explicitly eliminate the legacy fallback line (`ir_num = panel.photo_numbers[0]` at line ~590 in `src/full_report/scan_adapters.py`). If a photo attribute is `None`, set `ir_img = ""` and `vis_img = ""`. Under no circumstances will a missing photo fall back to `panel.photo_numbers[0]` or duplicate another chamber's photo.
   - Migrate `resolve_switchgear_compartments()` callsite at line ~580 in `scan_adapters.py` to `SwitchgearTopologyEngine`.
3. Dynamic Executive Summary Census Rows (`src/full_report/census.py`):
   - In `ExecutiveSummaryCensusBuilder`, resolve switchgear overview and panel rows using `SwitchgearTopologyEngine`.
   - Emit only physically present compartments. Omitted compartments (such as absent PTs) generate zero rows in Table 2.
   - Retain standard TNB presentation: healthy components display `"-"` metrics with solid Green shading (`#00B050`); defective components populate numerical readings from passed `CbmDefectRecord` objects (in `defects` parameter) with solid Red shading (`#EE0000`).
4. Unit Tests:
   - Update `tests/test_full_report_scan_adapters.py` to assert zero-fallback behavior (missing breaker photo does NOT copy cable photo, and `photo_numbers[0]` fallback is removed).
   - Update `tests/test_full_report_census_builder.py` to assert dynamic census row generation across archetypes.


## Branching & Release Policy
- **Feature Branch**: Implement all changes on `feature/switchgear-topology-engine` (branched from `main`). Never commit directly to `main`.
- **Merge Gate**: Merging to `main` requires 100% green automated test suite (`pytest`) AND explicit manual review and testing sign-off by the maintainer.

**Blocked by:** #49, #50

<!-- status: closed -->
**Status:** closed

- [x] Update `build_switchgear_scan_spec` and `build_switchgear_panel_scan_spec` in `src/full_report/models.py` to consume `SwitchgearTopologyEngine`.
- [x] Implement strict 1-to-1 photo pairing with zero-fallback in `SwitchgearScanAdapter` (`src/full_report/scan_adapters.py`), mapping `"FRONT COMPARTMENT"` $\to$ `panel.breaker_photo` and `"REAR COMPARTMENT"` $\to$ `panel.cable_photo`, and explicitly eliminating the `ir_num = panel.photo_numbers[0]` fallback line.
- [x] Update `SwitchgearScanAdapter` overview photo mapping to handle Front (Row 27), Rear (Row 26), and Top (Row 28) views.
- [x] Migrate `resolve_switchgear_compartments()` callsite at line ~580 in `src/full_report/scan_adapters.py` to `SwitchgearTopologyEngine`.
- [x] Update `ExecutiveSummaryCensusBuilder` (`src/full_report/census.py`) to generate switchgear rows dynamically via `SwitchgearTopologyEngine` using `CbmDefectRecord` objects.
- [x] Ensure omitted compartments generate zero census rows in Table 2.
- [x] Add unit tests in `tests/test_full_report_scan_adapters.py` validating zero-fallback.
- [x] Add unit tests in `tests/test_full_report_census_builder.py` validating dynamic census row generation across all 6 archetypes.
