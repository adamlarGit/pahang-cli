Part of #48

Blocked by: #52

# 053: Legacy Category Purge & Documentation Update

**What to build:**
Perform complete removal of deprecated switchgear category enums and procedural helpers, and document the new ubiquitous domain models:
1. Legacy Code Purge:
   - Completely delete `SwitchgearCategory` enum from `src/full_report/models.py`.
   - Purge all legacy category constants and helpers from `src/full_report/models.py`:
     - `VCB_STANDARD_COMPARTMENTS`
     - `VCB_TRANSITION_COMPARTMENTS`
     - `OVERVIEW_COMPARTMENTS_MAP`
     - `classify_switchgear()`
     - `resolve_overview_compartments()`
     - `resolve_switchgear_compartments()`
     - `resolve_panel_page_count()`
     - `is_tx_feeder()`
   - Purge deprecated category tokens (`TAMCO_LUCY`, `OTHER_RMU`) across source and test files.
   - Note: Stale specs in `docs/specs/` (`switchgear_archetype_compartment_spec.md` and `dynamic_vcb_and_battery_spec.md`) have been deleted.
2. Ubiquitous Language & Domain Documentation:
   - Update `CONTEXT.md` with definitions for:
     - `SwitchgearArchetype` (6 canonical hardware archetypes).
     - `VoltageClass` (Normalized voltage class seam).
     - `BayRole` (Functional panel configuration classifier).
     - `SwitchgearTopologyEngine` (Two-phase resolution pipeline).
     - `StrictZeroFallbackPolicy` (Zero photo duplication invariant).
3. Exhaustive Regression Audit:
   - Run the full test suite (`pytest`) across all unit, adapter, workflow, and regression test suites to guarantee 100% green pass rate and zero dead code.


## Branching & Release Policy
- **Feature Branch**: Implement all changes on `feature/switchgear-topology-engine` (branched from `main`). Never commit directly to `main`.
- **Merge Gate**: Merging to `main` requires 100% green automated test suite (`pytest`) AND explicit manual review and testing sign-off by the maintainer.

**Blocked by:** #52

**Status:** closed

- [x] Completely delete `SwitchgearCategory` enum from `src/full_report/models.py`.
- [x] Delete `VCB_STANDARD_COMPARTMENTS`, `VCB_TRANSITION_COMPARTMENTS`, and `OVERVIEW_COMPARTMENTS_MAP` constants from `src/full_report/models.py`.
- [x] Remove deprecated procedural helpers (`classify_switchgear`, `resolve_overview_compartments`, `resolve_switchgear_compartments`, `resolve_panel_page_count`, `is_tx_feeder`) from `src/full_report/models.py`.
- [x] Remove all remaining references to `TAMCO_LUCY` and `OTHER_RMU` across codebase and tests.
- [x] Update `CONTEXT.md` with ubiquitous vocabulary (`SwitchgearArchetype`, `VoltageClass`, `BayRole`, `SwitchgearTopologyEngine`).
- [x] Run full test suite (`pytest`) to confirm 100% green pass rate.
