<!-- status: closed -->
Part of #71
Specification: [spec.md](../spec.md)

# 076: docs(adr): record ADR 0006, update CONTEXT.md, and run full E2E regression suite

**What to build:** Record formal Architecture Decision Record (`docs/adr/0006-us-tev-survey-graph-generation-workflow.md`), update `CONTEXT.md` with domain models (broadening existing `SubstationIsolatedBatchResiliencePolicy` to cover batch US+TEV generation), perform manual CLI dry-run verification, and run the complete automated test suite to ensure zero regressions across the codebase.

**Blocked by:** #74, #75

**Status:** Closed

- [x] Author `docs/adr/0006-us-tev-survey-graph-generation-workflow.md` following project ADR format (verified 0006 is next available after 0005):
  - **Status**: Accepted
  - **Context**: Explains edge-case PRPD regeneration needs, multi-point VCB switchgear compartments, and the rationale for isolating graph generation from report compilation.
  - **Decision**: Standalone utility at menu position 9, output destination `<SUBSTATION>/RAW DATA/US+TEV/graphs/`, `{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}` schema, deterministic fallback via `measurement_metadata.js`, `BrowserPrerequisiteError` pre-flight check, and `SubstationIsolatedBatchResiliencePolicy`.
  - **Consequences**: Explicitly documents positive outcomes (robust multi-point naming, zero regression risk to report pipelines) and known limitations (reports do not automatically ingest pre-rendered graphs from `RAW DATA`).
- [x] Update `CONTEXT.md`:
  - Add new domain concepts under `## Concepts`:
    - **`UsTevGraphWorkflow`**: Standalone utility workflow generating PRPD graphs independently for operator-selected substations.
    - **`UsTevGraphOutputDirectory`**: Canonical output folder strictly located at `<SUBSTATION_FOLDER>/RAW DATA/US+TEV/graphs/`.
    - **`SurveyMeasurementNaming`**: Canonical schema `{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}.png`, preserving physical compartment labels (`CIRCUIT_BREAKER`, `CABLE_BOX`, `UPPER_BUSBARS`) across switchgear types.
    - **`BrowserPrerequisitePolicy`**: Enforces Chromium presence check prior to batch execution in Option C mode.
  - Broaden existing **`SubstationIsolatedBatchResiliencePolicy`** (lines 233–235) to explicitly encompass batch US+TEV graph generation alongside batch document post-processing (isolating single-substation survey/render failures to ensure remaining queue completes).
- [x] Run full automated test suite:
  - `pytest tests/test_us_tev_discovery.py`
  - `pytest tests/test_us_tev_graph_workflow.py`
  - `pytest tests/test_us_tev_cli.py`
  - `pytest tests/test_prpd_preview_script.py`
  - Full test suite `pytest` across all existing tests.
- [x] Perform manual CLI menu dry-run:
  - Verify `"Generate US+TEV survey graphs"` appears at Position #9 in `python -m src.workflow_cli` Utilities menu.
  - Verify interactive date drill-down, checklist filtering, and clean loop-back when cancelled.
