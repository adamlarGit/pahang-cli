---
id: "003"
title: "Equipment Classification Unification & Transformer Ultrasound Dynamic Blanking"
status: deferred
---

# Ticket 003: Equipment Classification Unification & Transformer Ultrasound Dynamic Blanking

<!-- status: deferred -->

## Status: DEFERRED

This ticket has been explicitly **deferred** by architectural decision pending a dedicated cross-equipment classification design session.

---

## Deferral Rationale & Problem Statement

### 1. The Classifier Fragmentation Problem
During analysis of Transformer templates (`tx-hv-sides.docx` and `tx-lv-sides.docx`) and the `{{ tx.location }}` placeholder resolution, the team identified severe architectural drift:
- Defect area, compartment, component, and location classification is currently fragmented across ad-hoc ternary checks, arbitrary regex patterns, and divergent string matching in multiple files:
  - **Quick Report**:
    - `src/quick_report/cbm_render.py` (lines 812–820): resolves `tx_location` via `any(k in search_loc for k in ("HV", "11KV", "33KV")) -> "HV - SIDE"`, `any(k in search_loc for k in ("LV", "415V")) -> "LV - SIDE"`.
    - `src/quick_report/cbm_rules.py` & `cbm_defect_planner.py`: ad-hoc substring heuristics for defect areas, ways, and phases.
  - **Full Report**:
    - `src/full_report/scan_adapters.py` (line 864): resolves `location` via `location = "HV SIDE" if "HV" in comp_name else ("LV SIDE" if "LV" in comp_name else "-")` (notice the omission of the `" - "` hyphen compared to Quick Report).
  - **Core Normalizers**:
    - `src/core/shading.py` (`normalize_swg_compartment`): hardcoded keyword precedence for switchgear compartments.
- Patching `{{ tx.location }}` in isolation or bolting transformer US blanking onto existing ad-hoc string matchers will exacerbate technical debt and maintenance drift across future report generations.

### 2. Architectural Consensus
Rather than applying another localized patch to `{{ tx.location }}`, the team agreed that:
1. **Unify Classifiers Across All Equipments**: We must establish dedicated, single-source-of-truth classification modules for each equipment family (`SWG`, `TX`, `FP` / `LVDB`) under `src/core/classifiers/`.
2. **Scope Alignment Before Implementation**: Only after the team has formally agreed upon the scope and design of unifying the classifier architecture for all equipment will we proceed with implementing Ultrasound blanking on Transformers (`tx-hv-sides.docx`).
3. **Multi-Session Roadmap Management**: Resolving the classifier design across all equipment and resolving all edge cases will span multiple dedicated sessions. Every decision, invariant, and open issue must be recorded in [`map.md`](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/dynamic-template-consolidation/map.md) so the roadmap maintains unambiguous direction.
4. **Roadmap Gating on Legacy Directory Deprecation (Phase 6)**: Because transformer IR-only defects currently rely on legacy `templates/QUICK REPORT/DEFECT IR/tx-hv-sides.docx` (where the US block is pre-removed), full retirement of legacy template folders cannot occur until Ticket 003 is un-deferred and completed.

---

## Required Scope for Future Design Sessions

When this ticket is un-deferred, the dedicated design sessions will address:

### A. Unified Equipment Classifier Subsystem (`src/core/classifiers/`)
Define canonical classification modules for each equipment family:

1. **Switchgear Classifier (`src/core/classifiers/swg.py`)**:
   - Canonical normalization of panel names, feeder numbers, and compartments (`BREAKER`, `CABLE`, `PT`, `BUSBAR`, `CABLE ENTRY`, `SECONDARY`, `LINK BOX`).
   - Unified mapping between testsheet specs, CBM defect records, and scan adapter items.
   - Consolidation of `normalize_swg_compartment` from `shading.py`.

2. **Transformer Classifier (`src/core/classifiers/tx.py`)**:
   - Canonical side and component classification: `HV Side`, `LV Side`, `Cable Box` (HV / LV), `Tank Body`, `Conservator`, `Radiator`, `Bushing`, `Tap Changer`.
   - Deterministic, standardized resolution of `{{ tx.location }}` across Full Report and Quick Report (e.g. agreeing on `"HV SIDE"` vs `"HV - SIDE"`).
   - Strict mapping of 7-point scan specs (`ADR 0004`: `OVERVIEW`, `OVERVIEW TOP`, `HV BUSHING`, `HV CABLE`, `HV CABLE SPLIT`, `LV BUSHING`, `LV CABLE`) to Quick Report defect pages.

3. **Feeder Pillar / LVDB Classifier (`src/core/classifiers/fp.py`)**:
   - Canonical classification of incoming ways, outgoing ways, busbars, and fuse carriers.
   - Standardized channel, phase, and feeder way parsing.

### B. Transformer Ultrasound (US) Dynamic Blanking Scope
Once the classifier subsystem is ratified and implemented:
1. **Tier 1 (Contract Technologies)**:
   - Use `is_us_contract_awarded(technologies)`.
   - When contract is IR-only (`["IR"]`), blank the US measurement block (rows 21–32, columns 1–8 of the 23-column table) in `tx-hv-sides.docx`.
2. **Tier 2 (Transformer Side / Point Eligibility)**:
   - `tx-hv-sides.docx`: 23-column table containing US measurement quadrant; blanked only when contract lacks US.
   - `tx-lv-sides.docx`: Statically IR-only across all contracts (rows 21–32 are permanently empty and borderless; zero blanking required).
3. **PRPD Optimization**:
   - Skip transformer US PRPD generation in `generate_prpd_graphs_for_transformer()` when contract lacks US.
4. **Scope Parity**:
   - Wire unified classifier and transformer US blanking into `TransformerScanAdapter` (`src/full_report/scan_adapters.py`) and Quick Report CBM renderer (`src/quick_report/cbm_render.py`).

---

## Next Steps to Un-defer

1. Schedule and hold the cross-equipment classifier unification design session.
2. Formalize an ADR / architecture document detailing `src/core/classifiers/` contracts.
3. Agree upon and ratify canonical classifier contracts for SWG, TX, and FP.
4. Re-open Ticket 003 for implementation of both the unified classifiers and transformer US dynamic blanking.
5. Unblock Phase 6 (full legacy template directory deprecation).
