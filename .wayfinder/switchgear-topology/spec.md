# Specification: Switchgear Topology Engine & Sub-Row Evidence Pipeline

## Problem Statement

Distribution substation condition-based monitoring (CBM) inspection reports require 100% fidelity to physical on-site equipment assets. Current switchgear reporting relies on a legacy procedural categorization system (`SwitchgearCategory`) that groups switchboards into broad manufacturer buckets (`INDKOM`, `TAMCO_LUCY`, `OTHER_RMU`, `VCB`) and applies rigid, hardcoded compartment lists.

This legacy model fails across multiple physical switchgear installations:
1. **VCB Cubicles with Varying Compartment Topologies**: Standard VCB bays physically vary in the presence of Potential Transformers (PT / VT) and anti-condensation heaters. The legacy generator assumes fixed 5-compartment structures, resulting in empty "ghost" PT scanning pages and census rows when no PT exists on site. Furthermore, Transition bays and Bus Section bays have fundamentally different internal physical layouts (e.g. Front/Rear/Busbar vs Breaker/Cable/Busbar/Secondary), but are currently mishandled.
2. **Evidence Misattribution & Photo Re-use**: When sub-row photos (such as separate breaker, busbar, or secondary thermal scans) are missing from the testsheet, downstream adapters aggressively fall back to `photo_numbers[0]` (the cable compartment photo). This duplicates photos across distinct physical chambers, producing misleading and potentially fraudulent engineering deliverables.
3. **Overview Perspective Distortion**: Different switchgear physical geometries require distinct visual and thermal overview angles. For example, VCB lineups require Front (breaker), Rear (cable), and Top (busbar) views; Indkom INS24 RMUs require an Overview and an Overview Top (gas gauge and fuse canister housing); Tamco and Lucy RMUs require an Overview and an Overview Bottom (cable trench / plinth entry). The current implementation collapses many of these into generic single-view overviews.
4. **Sub-Row Testsheet Evidence Loss**: Field inspectors record granular 4-row sub-grid diagnostic data (`PCE Testsheet` rows `r..r+3` and column `P`) capturing individual breaker, busbar, PT, and secondary panel IR photos. The existing extraction pipeline only reads the top row (`r`) and flattens photos into an unkeyed tuple, discarding physical chamber associations.
5. **Coupled Modality and Layout Logic**: Physical compartment existence is conflated with diagnostic testing contract eligibility (e.g. whether TEV or Ultrasound is active), creating brittle code where changing a contract scope risks breaking the physical switchgear census.

## Solution

Implement a **hybrid hierarchical topology engine** comprising a pure domain resolution pipeline, an extended sub-row testsheet evidence extractor, strict zero-fallback photo assignment in scan adapters, and dynamic Executive Summary census row generation.

The topology engine operates in two clean, decoupled phases:
1. **Phase 1: Board-Level Classification (Macro Archetype & Voltage Class)**:
   Given board-level metadata (switchgear type, manufacturer, model, voltage rating), classify the switchgear board into one of 6 canonical physical hardware archetypes (`VCB_CUBICLE`, `GIS_CUBICLE`, `RMU_DUAL_CABLE_ENTRY`, `RMU_FUSE_CANISTER`, `RMU_OIL`, `RMU_STANDARD`) and a normalized `VoltageClass` (`11kV`, `33kV`). This establishes board-level overviews (`swg-overview.docx`), busbar geometry expectations, and base bay blueprint profiles.
2. **Phase 2: Bay-Level Resolution (Dynamic Bay Roles & Empirical Presence Gates)**:
   Given an archetype, bay functional role (`STANDARD`, `TRANSFORMER`, `TRANSITION`, `BUS_SECTION`, `BUS_COUPLER`), and sub-row testsheet evidence, evaluate empirical presence gates:
   - **Dynamic PT Gate**: Emits `PT COMPARTMENT` on VCB/GIS standard bays if and only if sub-row `r+3` contains recorded photo evidence or non-empty measurement data.
   - **Dynamic Secondary Gate**: Emits `SECONDARY COMPARTMENT` on transition bays if and only if a secondary IR photo was recorded in column `P`. Standard and Bus Section bays include `SECONDARY COMPARTMENT` unconditionally, removing brittle gating on heater current.
   - The engine outputs a pure tuple of compartment name strings, completely decoupled from COM automation, disk operations, or rendering logic.

Downstream consumers consume this pure seam:
- **Scan Adapter with Strict Zero-Fallback**: Resolves 1-to-1 photo assignments for each active compartment. Missing photos render as blank placeholders with `"-"` metrics; under no circumstances are photos duplicated from other compartments.
- **Executive Summary Census**: Populates Table 2 with exact active compartments. Healthy components render with `"-"` and solid Green status fill (`#00B050`); confirmed defects render with quantitative defect readings from master engineering workbooks and solid Red status fill (`#EE0000`). Absent compartments produce zero rows.

## User Stories

1. As a TNB asset owner, I want CBM inspection reports to reflect the exact physical chambers present in each switchgear bay, so that my maintenance records do not contain phantom compartments or unverified equipment.
2. As a field testing engineer, I want sub-row photos recorded in rows `r..r+3` of the testsheet to be mapped directly to their corresponding breaker, cable, busbar, PT, and secondary compartments, so that my on-site diagnostic records are accurately represented.
3. As a report QA reviewer, I want missing compartment photos to render as blank image placeholders rather than reusing cable termination photos, so that reports maintain complete forensic integrity without photo duplication.
4. As a report automation operator, I want standard VCB feeder bays without PTs to generate exactly 4 scanning pages (`BREAKER`, `CABLE`, `BUSBAR`, `SECONDARY`), so that deliverable page counts match the physical site realities.
5. As a report automation operator, I want standard VCB feeder bays equipped with PTs (indicated by row `r+3` photo or measurement data) to generate exactly 5 scanning pages (`BREAKER`, `CABLE`, `BUSBAR`, `PT`, `SECONDARY`), so that all tested PT equipment is fully documented.
6. As a CBM inspector, I want VCB transition bays to generate `FRONT`, `REAR`, and `BUSBAR` compartments by default, and only append `SECONDARY` when a secondary panel IR photo was taken, so that transitional bus chambers are distinguished from standard breaker bays.
7. As a CBM inspector, I want VCB transition bays to never generate a PT compartment, so that impossible physical combinations are prevented by design.
8. As a substation maintenance engineer, I want VCB Bus Section and Bus Coupler bays to resolve to `BREAKER`, `REAR`, `BUSBAR`, and `SECONDARY` compartments, so that bus interconnecting bays are modeled with their actual rear riser architecture.
9. As an executive reviewer, I want the Executive Summary Table 2 to omit rows for absent compartments (such as omitted PTs), so that the summary table does not contain dummy entries or inaccurate asset counts.
10. As a report reviewer, I want healthy tested compartments in Executive Summary Table 2 to display `"-"` for IR, US, and TEV with solid green severity shading, adhering strictly to TNB distribution inspection recording conventions.
11. As a distribution engineer, I want defective switchgear compartments in Executive Summary Table 2 to display numerical defect readings and $\Delta T$ values with solid red severity shading, so that urgent hotspots are immediately visible.
12. As a report automation operator, I want VCB lineups to generate three distinct overview pages (`OVERVIEW FRONT`, `OVERVIEW REAR`, `OVERVIEW TOP`), so that all three inspection facets of a metal-clad cubicle are documented.
13. As a report automation operator, I want Indkom INS24 RMUs to generate two overview pages (`OVERVIEW` and `OVERVIEW TOP`), so that the gas pressure gauge and top fuse canister housing are properly represented.
14. As a report automation operator, I want Tamco and Lucy RMUs to generate two overview pages (`OVERVIEW` and `OVERVIEW BOTTOM`), so that the cable trench and lower plinth entry are documented.
15. As a report automation operator, I want Oil RMUs (such as Lucy VRN2a) to generate two overview pages (`OVERVIEW` and `OVERVIEW BOTTOM`), so that oil switchgear assemblies receive their required inspection views.
16. As a report automation operator, I want generic RMU switchgear (such as Siemens 8DJH or ABB SafeRing) to safely fall back to a single standard `OVERVIEW` page, so that unspecialized switchgear does not generate unwanted overview pages.
17. As an automation engineer, I want model token extraction to inspect co-mingled manufacturer strings (e.g. extracting `"INS24"` from `"INDKOM INS24"` when the model cell is blank), so that real-world testsheet entry variations are handled seamlessly.
18. As a software developer, I want the topology engine to be a pure domain module with zero dependencies on Word COM or image files, so that it can be tested completely in memory with millisecond unit tests.
19. As a software developer, I want `SwitchgearPanelSpec` to explicitly store typed sub-row photo numbers (`cable_photo`, `breaker_photo`, `busbar_photo`, `pt_photo`, `secondary_photo`, `has_pt_measurement`), so that downstream consumers avoid fragile index-based heuristics.
20. As a software developer, I want a first-class `VoltageClass` enum in the domain model, so that future 33kV dual-busbar switchgear features have a clean architectural seam without refactoring 11kV logic.
21. As a quality assurance tester, I want canonical benchmark substations (PE 179 Cenderawasih, PE 144 Telekom Tanah Putih, PE 005 Talapia, PE 157 Perpustakaan Awam) to pass strict regression assertions on exact page counts and compartment layouts, so that no regressions are introduced.
22. As a software maintainer, I want the legacy `SwitchgearCategory` enum and procedural helper functions to be completely removed, so that dead code and parallel lookup tables do not accumulate in the codebase.

## Implementation Decisions

### Decision 1: Hybrid Hierarchical Two-Phase Pipeline
Replace procedural `SwitchgearCategory` logic with a two-phase architecture:
- **Phase 1: Macro Archetype & Voltage Classification**: Board-level classifier operating on switchgear type, manufacturer, model, and voltage rating. Maps to `SwitchgearArchetype` (`VCB_CUBICLE`, `GIS_CUBICLE`, `RMU_DUAL_CABLE_ENTRY`, `RMU_FUSE_CANISTER`, `RMU_OIL`, `RMU_STANDARD`) and `VoltageClass` (`LV`, `6.6kV`, `11kV`, `22kV`, `33kV`). Resolves board-level overview tuples.
- **Phase 2: Bay-Level Compartment Resolution**: Dynamic bay resolver operating on `(archetype, bay_role, sub_row_evidence)` returning a pure `tuple[str, ...]`.
- *Interface Contract (Prototype Shape)*:
```python
class VoltageClass(str, Enum):
    LV = "LV"
    KV_6_6 = "6.6kV"
    KV_11 = "11kV"
    KV_22 = "22kV"
    KV_33 = "33kV"

class SwitchgearArchetype(str, Enum):
    VCB_CUBICLE = "VCB_CUBICLE"
    GIS_CUBICLE = "GIS_CUBICLE"
    RMU_DUAL_CABLE_ENTRY = "RMU_DUAL_CABLE_ENTRY"
    RMU_FUSE_CANISTER = "RMU_FUSE_CANISTER"
    RMU_OIL = "RMU_OIL"
    RMU_STANDARD = "RMU_STANDARD"

class BayRole(str, Enum):
    STANDARD = "STANDARD"
    TRANSFORMER = "TRANSFORMER"
    TRANSITION = "TRANSITION"
    BUS_SECTION = "BUS_SECTION"
    BUS_COUPLER = "BUS_COUPLER"
```

### Decision 2: Model Token Parsing and Precedence Hierarchy
Classification evaluates attributes in strict precedence: model decides, manufacturer hints, type bounds.
1. VCB priority: Any switchgear type containing `"VCB"` immediately resolves to `VCB_CUBICLE`.
2. GIS priority: Any switchgear type containing `"GIS"` resolves to `GIS_CUBICLE`.
3. Model token extraction: If model string is empty, scan manufacturer string for known tokens (`"INS24"`, `"GR1"`, `"FALCON"`, `"JMW12"`, `"VRN2A"`, `"GV3"`).
4. Manufacturer & Type fallback:
   - All `LUCY` variants (`LUCY`, `SSE LUCY`, `LUCY ELECTRIC`, `LUCY SWITCHGEAR`, etc.) $\to$ `RMU_DUAL_CABLE_ENTRY` (all Lucy RMUs in Pahang distribution are dual cable entry).
   - `TAMCO` $\to$ `RMU_DUAL_CABLE_ENTRY`.
   - `INDKOM`:
     - Explicit model containing `"INS24"` or token `"INS24"` extracted from manufacturer string $\to$ `RMU_FUSE_CANISTER`.
     - Model `"JMW12"` or blank/unrecognized model without `"INS24"` $\to$ `RMU_STANDARD` (where TX feeder is cable compartment, not fuse canister).
   - `MRMU` (switchgear type or manufacturer containing `"MRMU"`) $\to$ `RMU_STANDARD` (Motorized RMU / Modular RMU).
   - Oil or OCB $\to$ `RMU_OIL`.
   - Unrecognized RMU $\to$ safe fallback `RMU_STANDARD`.

### Decision 3: Dynamic Presence Gates & Omission of Heater Gating
- **Empirical PT Gate**: Evaluated exclusively on `STANDARD` and `TRANSFORMER` bays of `VCB_CUBICLE` and `GIS_CUBICLE`. Checks if sub-row `r+3` has a non-null photo number or non-empty measurement data in columns `K..V`. Appends `"PT COMPARTMENT"` if true; otherwise omits it.
- **Dynamic Secondary Gate**: Evaluated exclusively on `TRANSITION` bays of `VCB_CUBICLE` and `GIS_CUBICLE`. Appends `"SECONDARY COMPARTMENT"` if and only if a secondary IR photo was recorded in column `P`.
- **Rejection of Heater Current Gating**: In real substations, space heaters frequently trip, fail, or are switched off (recording `0.0A` or `"-"`), yet the physical LV relay compartment remains intact and inspected. Gating compartment presence on `heater_amp > 0` was rejected to avoid false-negative compartment omissions. Standard, Transformer, and Bus Section bays include `SECONDARY COMPARTMENT` unconditionally in their base blueprint.

### Decision 4: Extended Panel Spec, Scan Spec, and Clear Photo Extraction Seams
Extend `SwitchgearPanelSpec` (`src/testsheet/models.py`) and `SwitchgearPanelScanSpec` (`src/full_report/models.py`) with explicit sub-row photo attributes (`cable_photo`, `breaker_photo`, `secondary_photo`, `busbar_photo`, `pt_photo`, `has_pt_measurement`), propagating all fields in `build_switchgear_panel_scan_spec()`.

Maintain a clean architectural seam between board-level overview photos and panel-level sub-row photos in `src/testsheet/extractor.py`:
1. **Overview Photo Extraction (`_extract_overview_photos`)**:
   Inspects rows 26, 27, 28:
   - Row 27 Col O (`BREAKER`): Front Overview (`OVERVIEW FRONT` on VCB).
   - Row 26 Col O (`CABLE`): Rear Overview (`OVERVIEW REAR` on VCB, or primary `OVERVIEW` on RMU).
   - Row 28 Col O (`TOP PANEL`): Top Overview (`OVERVIEW TOP` on VCB and Indkom INS24, or bottom overview on Tamco/Lucy).
2. **Panel Sub-Row Extraction (`_extract_panels`)**:
   Inspects the 4-row sub-grid (`r` = 10, 14, 18, 22):
   - Row `r`: Cable photo from column `O` (`cable_photo`).
   - Row `r+1`: Breaker photo from column `O` (`breaker_photo`), secondary panel photo from column `P` (`secondary_photo`) via regex parsing `"S.PANEL IR <num>"` or bare digits.
   - Row `r+2`: Busbar photo from column `O` (`busbar_photo`).
   - Row `r+3`: PT photo from column `O` (`pt_photo`), PT measurement existence from columns `K..V` (`has_pt_measurement`).

### Decision 5: Strict Zero-Fallback in Scan Adapters
Within `SwitchgearScanAdapter`, each resolved compartment is paired 1-to-1 with its explicit photo attribute:
- `"BREAKER COMPARTMENT"` $\to$ `panel.breaker_photo`
- `"FRONT COMPARTMENT"` $\to$ `panel.breaker_photo`
- `"CABLE COMPARTMENT"` $\to$ `panel.cable_photo`
- `"REAR COMPARTMENT"` $\to$ `panel.cable_photo`
- `"BUSBAR COMPARTMENT"` $\to$ `panel.busbar_photo`
- `"PT COMPARTMENT"` $\to$ `panel.pt_photo`
- `"SECONDARY COMPARTMENT"` $\to$ `panel.secondary_photo`
If a compartment's photo is `None`, the adapter emits empty strings (`""`) for `ir_img` and `vis_img`. Under no circumstances will a missing photo fall back to `photo_numbers[0]` or cable photos. Templates render blank image placeholders and display `"-"` metrics.

### Decision 6: Executive Summary Census Formatting
In `ExecutiveSummaryCensusBuilder`:
- Switchgear overview rows render unshaded severity with `"-"`.
- Panel compartment rows render based on presence: healthy components display `"-"` metrics and solid Green fill (`#00B050`); confirmed defects (cross-referenced from passed `CbmDefectRecord` objects) display numerical metrics and solid Red fill (`#EE0000`).
- Dynamically omitted compartments (e.g. absent PTs) generate zero census rows, preventing phantom records.

### Decision 7: Decoupling from Battery Workstream
Battery bank normalization and dynamic sub-row extraction (rows 58–68) are completely separated from switchgear topology and scheduled for an independent workstream.

## Testing Decisions

### What Makes a Good Test
- **External Behavior Verification**: Tests must verify the input-to-output contract of the topology engine, testsheet extractor, scan adapter, and census builder rather than internal implementation details or private helper functions.
- **Zero COM Dependencies**: Pure domain tests for archetype classification, bay role detection, and compartment resolution must run entirely in memory with no dependencies on Microsoft Word COM, Excel COM, or disk assets.
- **Deterministic Deliverable Invariants**: Integration tests on canonical benchmark datasets must assert exact page counts, exact compartment sequences, and zero photo leakage across chambers.

### Modules to Test
1. **Core Topology Engine (`tests/test_topology.py`)**:
   - Classification of all 6 archetypes across diverse manufacturer and model strings.
   - Model token extraction from co-mingled strings and manufacturer fallbacks.
   - Bay role classification across keywords (`TX`, `TRANSITION`, `BUS SECTION`, `SPARE`, etc.).
   - Compartment resolution for VCB standard bays with and without PT evidence.
   - Compartment resolution for VCB transition bays with and without secondary photo.
   - Overview compartment resolution for all archetypes (3 for VCB, 2 for Indkom INS24, 2 for Tamco/Lucy, 2 for Oil, 1 for generic RMU).
   - Voltage class classification (11kV active scope, 33kV seam).
2. **Testsheet Extractor (`tests/test_testsheet_extractor.py`)**:
   - 4-row sub-grid parsing of cable, breaker, busbar, PT, and secondary photos.
   - Column `P` regex parsing for secondary panel IR numbers.
   - Verification against benchmark workbooks: PE 157 (VCB with PT on Panel 4), PE 082, PE 156.
3. **Full Report Adapters & Census (`tests/test_full_report_scan_adapters.py`, `tests/test_full_report_census_builder.py`)**:
   - Zero-fallback enforcement: absent photos result in blank image paths, never duplicating `photo_numbers[0]`.
   - Census Table 2 row generation: exact matching rows, green fill for healthy, red fill for defects, zero rows for absent PTs.
4. **Benchmark Regression Suite (`tests/test_full_report_scan_models.py`, `tests/test_full_report_defect_interleaving.py`, `tests/test_full_report_plan_builder.py`)**:
   - Full regression verification on PE 179 (14 pages, 6 SWG), PE 144 (15 pages base, 19 pages with TEV defect interleaving [10 SWG]), PE 005 (19 pages, 10 SWG), PE 157 (VCB 3 overviews, 4 bays $\times$ 4 comp, 1 bay $\times$ 5 comp).

### Prior Art
- `tests/test_full_report_scan_models.py`: Established canonical benchmark deliverable assertions and page count validations.
- `tests/test_full_report_scan_adapters.py`: Established mock-based Bill of Materials rendering assertions.
- `tests/test_full_report_census_builder.py`: Established Table 2 row assembly and XML cell merge verification.
- `tests/test_testsheet_extractor.py`: Established openpyxl testsheet parsing assertions.


## Branching & Release Policy

> [!IMPORTANT]
> **Branching & Merge Invariants**:
> - **Feature Branch**: All tickets in this specification must be implemented on a dedicated feature branch: `feature/switchgear-topology-engine` (branched from `main`).
> - **Isolation Invariant**: Under no circumstances should implementation commits be pushed directly to `main`.
> - **Manual QA & Verification Gate**: Merging `feature/switchgear-topology-engine` back into `main` is gated on:
>   1. 100% green automated test suite pass rate (`pytest`) across all unit, adapter, workflow, and regression suites.
>   2. Complete manual verification and visual deliverable inspection performed and explicitly approved by the human maintainer.

## Out of Scope

- **DC Battery Bank Dynamic Extraction**: Dynamic parsing of testsheet rows 58–68, cell string normalization, and battery health census rows are decoupled and tracked independently in `.scratch/battery-discovery/`.
- **33kV GIS Multi-Gas Execution**: `GIS_CUBICLE` archetype enum and profile stubs are defined, but multi-gas chamber views and dual busbars remain stubs until 33kV GIS inspection workbooks are delivered.
- **Word COM Template Layout Changes**: Modifying table borders, font sizing, or visual styling inside `.docx` binary template files.

## Further Notes

- **Ubiquitous Language**: Once implemented, `SwitchgearArchetype`, `VoltageClass`, `BayRole`, and `SwitchgearTopologyEngine` become part of the project's ubiquitous domain language and will be documented in `CONTEXT.md`.
- **Ticket Execution Sequence**: Five implementation tickets track this work sequentially:
  - Ticket #49: Core Domain Models & Switchgear Topology Engine
  - Ticket #50: SwitchgearPanelSpec Model Extension & Sub-Row Extraction
  - Ticket #51: Scan Adapters & Executive Summary Census Integration
  - Ticket #52: Benchmark Deliverables & Regression Suite Alignment
  - Ticket #53: Legacy Category Purge & Documentation Update
