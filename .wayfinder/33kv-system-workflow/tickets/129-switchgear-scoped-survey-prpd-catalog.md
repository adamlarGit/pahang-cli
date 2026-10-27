<!-- status: closed -->
# Ticket #129: feat(survey): switchgear-scoped UltraTEV survey discovery and PRPD catalog for multi-switchgear substations

## Parent
Part of #90

## What to build
Enable accurate, collision-free ultrasound (US) and transient earth voltage (TEV) PRPD graph generation and attachment for substations with multiple switchgear lineups (e.g. 33kV GIS and 11kV VCB sharing panel indices 1..8):

- **Scoped Feeder Discovery (`src/quick_report/prpd.py`)**:
  - Update `_discover_substation_assets()` and `find_swg_feeder_survey_dir()` to accept switchgear context (`swg_idx`, `voltage_class`, or `switchgear_type`).
  - Restrict feeder searches so 33kV panels only match within 33kV directories (e.g. `GIS_33kV/` or matching `33kV`) and 11kV panels only match within 11kV directories (e.g. `VCB_11kV/` or matching `11kV`).
  - Prevent panel index collisions where Switchgear 2 (11kV) overwrites Switchgear 1 (33kV) entries in `swg_panels`.
- **Lineup-Scoped PRPD Catalog (`src/quick_report/prpd.py`)**:
  - Scope `catalog["swg"]` by switchgear lineup: `catalog["swg"][swg_idx][panel_no]` (or composite key `f"swg{swg_idx}_p{panel_no}"`) rather than a single flat dictionary.
  - Save rendered PRPD image files with switchgear index isolation: `prpd_swg{swg_idx}_panel{panel_no}_{comp}_{tech}.png` to avoid disk overwriting between lineups.
- **Switchgear Scan Adapter Resolution (`src/full_report/scan_adapters.py`)**:
  - Update `SwitchgearScanAdapter._resolve_prpd()` to look up waveforms using its `self.swg_index`.
  - Prevent fallback to headless Chrome rendering when a compartment has already been cataloged as unmeasured.
- **Unit and Integration Tests**:
  - Add tests verifying dual-switchgear PRPD graph generation on synthetic and live fixtures (e.g. `CJEN/PMU/J00001`).

## Acceptance criteria
- [x] `_discover_substation_assets` discovers feeders scoped to each switchgear lineup without overwriting shared panel numbers.
- [x] `catalog["swg"]` indexes graphs per switchgear lineup (`swg_index`).
- [x] Generated PRPD image filenames include switchgear index (`prpd_swg{swg_idx}_panel{panel_no}_...`).
- [x] `SwitchgearScanAdapter._resolve_prpd` correctly pulls waveforms for both 33kV and 11kV panels without cross-lineup graph contamination.
- [x] Passes all test suites in `tests/test_prpd_generator.py` and `tests/test_full_report_scan_adapters.py`.

## Blocked by
None (can start immediately)
