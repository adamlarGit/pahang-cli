Part of #48

Blocked by: #51

# 052: Benchmark Deliverables & Regression Suite Alignment

**What to build:**
Align canonical benchmark test suites with ground-truth substation deliverables, verifying exact page counts, overview counts, and dynamically gated compartment layouts:
1. Canonical Benchmark Substations:
   - **PE 179 Cenderawasih NO.1 (RMU_FUSE_CANISTER - INDKOM INS24)**:
     - 2 overview pages: `OVERVIEW` and `OVERVIEW TOP`.
     - 4 panel pages: 3 Line switch bays (`CABLE COMPARTMENT`) + 1 TX switch bay (`FUSE COMPARTMENT`).
     - Total: 6 SWG pages, 14 total substation pages.
   - **PE 144 Telekom Tanah Putih (RMU_FUSE_CANISTER - INDKOM INS24)**:
     - 2 overview pages: `OVERVIEW` and `OVERVIEW TOP`.
     - 4 panel pages: 3 Line switch bays (`CABLE COMPARTMENT`) + 1 TX switch bay (`FUSE COMPARTMENT`).
     - With severe TEV defect interleaving (4 defect pages appended after panels):
       - Total SWG: 10 SWG pages (2 overview + 4 panel + 4 TEV defect interleaving).
       - Total Substation: 19 total pages (10 SWG + 7 TX + 1 LVDB + 1 Battery).
   - **PE 005 Talapia (RMU_DUAL_CABLE_ENTRY - TAMCO)**:
     - 2 overview pages: `OVERVIEW` and `OVERVIEW BOTTOM`.
     - 8 panel pages.
     - Total: 10 SWG pages, 19 total substation pages.
   - **PE 157 Perpustakaan Awam (VCB_CUBICLE)**:
     - 3 overview pages: `OVERVIEW FRONT`, `OVERVIEW REAR`, `OVERVIEW TOP`.
     - Panels 1, 2, 3, 5: exactly 4 compartments each (`BREAKER`, `CABLE`, `BUSBAR`, `SECONDARY`), with zero phantom PT pages.
     - Panel 4: exactly 5 compartments (`BREAKER`, `CABLE`, `BUSBAR`, `PT`, `SECONDARY`) with photo 526 assigned to PT.
     - Total SWG: 24 SWG scanning pages (3 overviews + 4×4 + 1×5).
     - Total Substation: 34 total scanning pages (24 SWG + 7 TX + 1 FP + 2 Battery).
2. Regression Suite Verification:
   - Ensure all tests in `tests/test_full_report_scan_models.py`, `tests/test_full_report_scan_render_core.py`, `tests/test_full_report_scan_adapters.py`, `tests/test_full_report_census_builder.py`, `tests/test_full_report_defect_interleaving.py`, and `tests/test_full_report_plan_builder.py` pass cleanly.
   - Update baseline benchmark assertions:
     - PE 179 Cenderawasih NO.1 $\to$ 14 total pages (6 SWG).
     - PE 144 Telekom Tanah Putih (with `model="INS24"`) $\to$ 15 total pages base (6 SWG) / 19 total pages with 4 TEV defect pages (10 SWG).
     - SK Raub Indah (healthy standard VCB) $\to$ 21 total pages (19 SWG: 3 overviews + 4 panels $\times$ 4 compartments).
     - PE 005 Talapia $\to$ 19 total pages (10 SWG).
     - PE 157 Perpustakaan Awam $\to$ 34 total pages (24 SWG).


## Branching & Release Policy
- **Feature Branch**: Implement all changes on `feature/switchgear-topology-engine` (branched from `main`). Never commit directly to `main`.
- **Merge Gate**: Merging to `main` requires 100% green automated test suite (`pytest`) AND explicit manual review and testing sign-off by the maintainer.

**Blocked by:** #51

**Status:** ready-for-agent

- [ ] Add and verify PE 179 Cenderawasih NO.1 benchmark test asserting 6 SWG pages and 14 total substation pages.
- [ ] Add and verify PE 144 Telekom Tanah Putih benchmark test (RMU_FUSE_CANISTER - INDKOM INS24 with `model="INS24"`) asserting 10 SWG pages (with 4 TEV defect interleaving pages) and 19 total substation pages.
- [ ] Add and verify PE 005 Talapia benchmark test asserting 10 SWG pages and 19 total substation pages.
- [ ] Add benchmark assertion for PE 157 Perpustakaan Awam asserting 3 VCB overviews, 4-compartment standard bays, 5-compartment PT bay, 24 SWG pages, and 34 total substation pages.
- [ ] Ensure 100% green pass rate across `pytest tests/test_full_report_*.py` (including `test_full_report_defect_interleaving.py` and `test_full_report_plan_builder.py`).
