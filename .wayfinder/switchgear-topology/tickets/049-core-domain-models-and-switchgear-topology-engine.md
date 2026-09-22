Part of #48

# 049: Core Domain Models & Switchgear Topology Engine

**What to build:**
Implement the pure domain core in `src/core/topology.py` providing the two-phase switchgear topology engine:
1. Domain Enums:
   - `SwitchgearArchetype(str, Enum)`: `VCB_CUBICLE`, `GIS_CUBICLE`, `RMU_DUAL_CABLE_ENTRY`, `RMU_FUSE_CANISTER`, `RMU_OIL`, `RMU_STANDARD`.
   - `VoltageClass(str, Enum)`: `LV`, `KV_6_6` ("6.6kV"), `KV_11` ("11kV"), `KV_22` ("22kV"), `KV_33` ("33kV").
   - `BayRole(str, Enum)`: `STANDARD`, `TRANSFORMER`, `TRANSITION`, `BUS_SECTION`, `BUS_COUPLER`.
2. Phase 1 Board Classification:
   - `classify_voltage_rating(rating: str) -> VoltageClass` normalizing raw rating strings (`"11kV"`, `"12kV"`, `"12kV, 630A"`, blank/empty strings $\to$ `KV_11`; `"33kV"` $\to$ `KV_33`).
   - `extract_model_from_manufacturer(manufacturer: str, model: str) -> str` extracting known model tokens (`INS24`, `GR1`, `FALCON`, `JMW12`, `VRN2A`, `GV3`) when model is blank.
   - `resolve_switchgear_archetype(switchgear_type: str, manufacturer: str, model: str) -> SwitchgearArchetype` with VCB/GIS priority, model token matching, manufacturer fallback, and generic fallback:
     - VCB / GIS priority: `VCB` $\to$ `VCB_CUBICLE`, `GIS` $\to$ `GIS_CUBICLE` (note: `GIS_CUBICLE` mirrors `VCB_CUBICLE` blueprints as an unexecuted forward seam).
     - All Lucy variants (`LUCY`, `SSE LUCY`, `LUCY ELECTRIC`, etc.) $\to$ `RMU_DUAL_CABLE_ENTRY`.
     - Tamco $\to$ `RMU_DUAL_CABLE_ENTRY`.
     - Indkom:
       - Model containing `INS24` (or token `INS24` extracted from manufacturer) $\to$ `RMU_FUSE_CANISTER`.
       - Model `JMW12` or blank/unrecognized without `INS24` $\to$ `RMU_STANDARD` (where TX feeder is cable compartment, not fuse canister).
     - MRMU (type or manufacturer containing `"MRMU"`) $\to$ `RMU_STANDARD`.
     - Oil or OCB $\to$ `RMU_OIL`.
     - Generic / unrecognized RMU $\to$ `RMU_STANDARD`.
   - `resolve_overview_compartments(archetype: SwitchgearArchetype, voltage_class: VoltageClass = VoltageClass.KV_11) -> tuple[str, ...]`:
     - VCB / GIS: 3 views (`"OVERVIEW FRONT"`, `"OVERVIEW REAR"`, `"OVERVIEW TOP"`).
     - INDKOM INS24: 2 views (`"OVERVIEW"`, `"OVERVIEW TOP"`).
     - TAMCO & all LUCY: 2 views (`"OVERVIEW"`, `"OVERVIEW BOTTOM"`).
     - RMU OIL: 2 views (`"OVERVIEW"`, `"OVERVIEW BOTTOM"`).
     - RMU Standard (including Indkom JMW12, MRMU): 1 view (`"OVERVIEW"`).
3. Phase 2 Bay Role & Compartment Resolution:
   - Unified bay classification across VCB and RMU:
     `classify_bay_role(name: str = "", panel_feeder_no: str = "", panel_type: str = "", archetype: SwitchgearArchetype = SwitchgearArchetype.RMU_STANDARD) -> BayRole`:
     - `BUS_SECTION`: matched by keywords `["BUS SECTION", "BUS-SECTION", "B/S", "BUS SEC", "SECTION", "SEC"]`.
     - `BUS_COUPLER`: matched by keywords `["BUS COUPLER", "BUS-COUPLER", "B/C", "COUPLER"]`.
     - `TRANSITION`: matched by keywords `["TRANSITION"]`.
     - `TRANSFORMER`: matched by keywords `["TX", "TRANSFORMER", "ALATUBAH", "TEE-OFF"]` in `name` or `panel_feeder_no`.
     - Standard feeder bays (`FEEDER`, `INCOMING`, `OUTGOING`, `SPARE`, and regular line names) resolve to `BayRole.STANDARD`.
   - Base blueprint registry and dynamic presence gates:
     - Empirical PT Gate: Appends `"PT COMPARTMENT"` to VCB/GIS Standard and Transformer bays iff sub-row `r+3` has photo or measurement evidence.
     - Pure Photo Presence Secondary Gate: Appends `"SECONDARY COMPARTMENT"` to VCB/GIS Transition bays iff Col P secondary photo exists (unconditional on Standard, Transformer, and Bus bays; zero dependency on heater current).
     - Transition bays never emit PT compartments.
     - RMU blueprints:
       - `RMU_DUAL_CABLE_ENTRY` (Tamco, all Lucy): Panels = `("CABLE COMPARTMENT", "CABLE ENTRY")`.
       - `RMU_FUSE_CANISTER` (Indkom INS24): `BayRole.TRANSFORMER` emits `("FUSE COMPARTMENT",)`, other roles emit `("CABLE COMPARTMENT",)`.
       - `RMU_OIL`: Panels = `("CABLE COMPARTMENT", "CABLE ENTRY")`.
       - `RMU_STANDARD` (Generic RMU, Indkom JMW12, MRMU): Panels = `("CABLE COMPARTMENT",)` for all roles.
4. Engine Facade:
   - `SwitchgearTopologyEngine` class encapsulating board classification and bay compartment resolution, returning pure `tuple[str, ...]`.
5. Unit Tests:
   - Pure unit test suite in `tests/test_topology.py` covering all archetypes, bay roles, token extractions, and empirical presence gates in memory with zero COM or filesystem dependencies.


## Branching & Release Policy
- **Feature Branch**: Implement all changes on `feature/switchgear-topology-engine` (branched from `main`). Never commit directly to `main`.
- **Merge Gate**: Merging to `main` requires 100% green automated test suite (`pytest`) AND explicit manual review and testing sign-off by the maintainer.

**Blocked by:** None (can start immediately)

<!-- status: closed -->
**Status:** closed

- [x] Define `SwitchgearArchetype`, `VoltageClass`, and `BayRole` enums in `src/core/topology.py`.
- [x] Implement `classify_voltage_rating(rating: str) -> VoltageClass` with normalizations for `11kV`, `12kV`, blank.
- [x] Implement `extract_model_from_manufacturer(manufacturer: str, model: str) -> str`.
- [x] Implement `resolve_switchgear_archetype(switchgear_type: str, manufacturer: str, model: str) -> SwitchgearArchetype` strictly requiring `INS24` token for `RMU_FUSE_CANISTER` (Indkom JMW12 $\to$ `RMU_STANDARD`), all Lucy $\to$ `RMU_DUAL_CABLE_ENTRY`, MRMU $\to$ `RMU_STANDARD`.
- [x] Implement `resolve_overview_compartments(archetype: SwitchgearArchetype, voltage_class: VoltageClass = VoltageClass.KV_11) -> tuple[str, ...]`.
- [x] Implement `classify_bay_role(name: str = "", panel_feeder_no: str = "", panel_type: str = "", archetype: SwitchgearArchetype = SwitchgearArchetype.RMU_STANDARD) -> BayRole` with keyword matching for `TRANSFORMER`, `BUS_SECTION`, `BUS_COUPLER`, `TRANSITION`, and `STANDARD`.
- [x] Implement base blueprint profiles (including `RMU_OIL` panels as `("CABLE COMPARTMENT", "CABLE ENTRY")`) and dynamic presence gates (`eval_pt_gate`, `eval_secondary_gate`).
- [x] Implement `SwitchgearTopologyEngine` facade class with `classify_board(...)` and `resolve_panel_compartments(...)`.
- [x] Implement comprehensive unit test suite in `tests/test_topology.py` validating 100% of archetypes, roles, and gates.

