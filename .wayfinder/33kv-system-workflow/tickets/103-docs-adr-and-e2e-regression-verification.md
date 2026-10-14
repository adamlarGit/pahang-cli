<!-- status: settled -->
Part of #90
Specification: [spec.md](../spec.md)

# 103: docs(33kv): Record ADR 0007, update CONTEXT.md, and e2e regression verification across all 14 workflows

**What to build:** Record Architecture Decision Record (ADR 0007) detailing the unified voltage-polymorphic architecture across all 14 Project Workflow actions, document all new domain concepts in `CONTEXT.md`, and execute the complete test suite verifying 100% green tests with 0 regressions on 11kV and complete verification on 33kV.

**Blocked by:** #97, #99, #100, #102

**Status:** ready-for-agent

- [ ] Record ADR 0007 in `docs/adr/0007-voltage-polymorphic-workflows-for-33kv.md` detailing (Decision Q86):
  - Context: Expansion to 33kV sub-transmission contract 750-39 and PPU/PMU/SSU facilities.
  - Decision: Unified 14-action Project Workflow menu with polymorphic runtime dispatch via `ProjectEnvironment.voltage_type`.
  - Architecture: `TestsheetParserStrategy`, statewide contract 750-39 storage resolution, shifted QR02 transaction, PPU condition builder, programmatic per-sheet PageSetup testsheet export, `TOTAL PE.xlsx` census sync, WhatsApp daily reporting, `T1SUB33` MSMS pipeline, and `MultiPartPartitionPolicy` Full Report assembly.
  - Consequences & trade-offs: Total backward compatibility for 11kV, clean separation without code bloat.
  - Non-goals & out-of-scope boundaries (no 132kV/275kV, no workbook layout mutation, no legacy sheet variants) (Decision Q90).
- [ ] Update `CONTEXT.md` with 33kV domain concepts (Decision Q87):
  - `TestsheetParserStrategy`, `PpuTestsheetParser`, `PceTestsheetParser`.
  - `PowerTransformerSpec` and rating threshold policy ($\ge 5$ MVA vs $100-1000$ kVA).
  - `SecondaryCompartmentRemarksPolicy` (Column Q `SP:` extraction).
  - `Qr02Cba33kVTransaction` (Columns G–R).
  - `PpuSubstationConditionPairBuilderPolicy`.
  - `HighFidelityDocumentExportPolicy` (per-sheet PageSetup landscape/portrait export).
  - `T1SUB33` MSMS Online Condition Assessment.
  - `MultiPartPartitionPolicy` 33kV multi-lineup expansion.
- [ ] Execute complete test suite (`pytest`) across all unit, adapter, workflow, and integration test suites, guaranteeing zero regression failures (Decision Q88).
- [ ] Perform manual end-to-end dry-run inspection on real 33kV project data (THUNDER at `C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER`) to satisfy the feature branch merge gate (Decision Q89).

