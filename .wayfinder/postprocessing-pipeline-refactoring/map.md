<!-- label: wayfinder:map -->
# 1-Click Substation Post-Processing Pipeline Refactoring

## Destination

Refactor the **1-Click Substation Post-Processing Pipeline** into a robust, maintainable 6-stage orchestration workflow that delivers complete client deliverable bundles (synchronized folders, signed & diagonalized testsheets, merged deliverable PDFs in `QUICK REPORT/`, and daily WhatsApp reports in `PYTHON/WHATSAPP/`) strictly reusing existing domain and workflow modules under DRY principles with zero duplicated logic.

## Notes

- **Domain**: PCE Substation Post-Processing & Deliverable Automation (Pahang TNB project)
- **Primary Skills**: `/tdd`, `/domain-modeling`, `/unslop`
- **Architectural Seam & DRY Reuse**: The pipeline is strictly an orchestration layer invoking existing modular functions:
  - Discovery: `LocalTestsheetPackageRepository.find_packages`
  - Renaming & Sync: `src.workflows.rename_files.rename_files_match`
  - Daily WhatsApp Report: `src.workflows.whatsapp.run_generate_whatsapp_report`
  - Signature Stamping / Sanitization: `src.workflows.replace_signatures.replace_pce_images`
  - Diagonal Blank Cells: `src.workflows.diagonal_borders.process_workbook`
  - COM Conversion & PDF Merging: `src.postprocessing.converters.ComDocumentConverter`
- **COM Lifecycle Management**: Word and Excel COM application instances must be managed via a batch-level context manager (`try...finally`) to avoid spinning up/down processes per substation.
- **Testsheet Immutability**: Source `.xlsx` workbooks in `TESTSHEET/<DATE>/` remain untouched; modified working copies are written to `TESTSHEET/<DATE>/processed_testsheet/<STEM>.xlsx`.
- **Per-Substation Resilience**: Substation processing errors are isolated—individual failures are logged to the audit summary without crashing the entire batch loop.
- **Strict TDD Requirement**: All implementation tickets must be developed test-first using the red-green-refactor cycle.
- **Dead Code Cleanup**: Final ticket must purge dead/redundant legacy code, orphan converters, and unused helper functions.

## Decisions so far

- [Decision 1: Final Deliverable Destination](map.md) — Comprehensive Client Deliverable Bundle (synchronized folders, signed & diagonalized workbooks, combined deliverable PDF, WhatsApp report, audit summary) built strictly via modular reuse.
- [Decision 2: Canonical Lifecycle Stages](map.md) — 6-stage pipeline: Discovery $\to$ Configuration $\to$ Pre-Flight Renaming $\to$ WhatsApp Reporting $\to$ Per-Substation Document Processing $\to$ Execution Summary.
- [Decision 3: Target Scoping Rules](map.md) — WhatsApp reporting is prompted and run only in `by_date` mode; Renaming sync dynamically targets the parent date folders of selected substations in both `by_date` and `by_fl` modes.
- [Decision 4: Pre-Flight Integrity & Renaming Validation](map.md) — Strict fail-fast check enforcing equal counts between `QUICK REPORT/`, `TESTSHEET/` (`.xlsx` only, ignoring `processed_testsheet/`, `UNSORTED RAW DATA/`, and lock files), and `RAW MATERIAL/` folders.
- [Decision 5: Signature Placeholder Sanitization & Immutability](map.md) — Original testsheets are immutable; working copies live in `processed_testsheet/`; when signatures are skipped, raw `{{signvendor}}` and `{{signtnb}}` placeholders are cleanly stripped using the existing `NONE` mode.
- [Decision 6: PDF Deliverable Placement & Page Ordering](map.md) — Merged deliverable PDF is saved in-place at `QUICK REPORT/<DATE>/<STEM>.pdf`; standalone testsheet PDF is preserved at `TESTSHEET/<DATE>/processed_testsheet/pdf/<STEM>.pdf`. Canonical page order: Quick Report $\to$ PCE Testsheet $\to$ PCE VI.
- [Decision 7: Shared COM Session & Batch Resilience](map.md) — Reuses a single shared Word and Excel COM session for the entire batch; per-substation errors are caught and recorded to prevent batch aborts.
- [Decision 8: Progress Logging & Final Audit Manifest](map.md) — Step-by-step real-time CLI feedback per substation and structured final execution summary box detailing counts, outputs, warnings, and timer.

## Execution Tickets

1. [001: Pre-Flight Integrity Validator & File Filter](001-pre-flight-validator.md) — Closed
2. [002: Shared COM Session Context Manager](002-shared-com-session.md) — Closed
3. [003: Lean Post-Processing Orchestrator Service](003-orchestrator-service.md) — Closed
4. [004: CLI Presentation Adapter & Audit Summary Box](004-cli-presentation-adapter.md) — Closed
5. [005: End-to-End Integration Test Suite](005-integration-tests.md) — Closed

6. [006: Dead Code Cleanup & Redundant Logic Removal](006-dead-code-cleanup.md) — Closed
7. [007: Domain Model & Documentation Sync](007-domain-model-docs-sync.md) — Closed

## Out of scope

- **Batch Master Combined PDF with Separator Sheets**: Merging all daily substations into a single multi-station PDF with separator sheets is excluded from the 1-Click pipeline. (Maintained as a standalone utility action).
