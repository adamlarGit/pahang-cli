Part of #55
Specification: [spec.md](../spec.md)

# 058: test(full-report): cli telemetry, benchmark e2e verification & docs

**What to build:** Synthetic VCB benchmark fixture creation, CLI dry-run telemetry updates, end-to-end integration verification, and domain model documentation updates. Create a self-contained synthetic benchmark fixture for PE 157 PERPUSTAKAAN AWAM in `tests/benchmarks/`. Update CLI interactive dry-run inspection prompts for both Full Report generation and post-processing to clearly display multi-part file status and part counts. Implement end-to-end integration tests verifying the full lifecycle (Stage 1 multi-part generation followed by Stage 2 post-processing PDF stitching) on realistic VCB switchgear packages and benchmark deliverables. Sync the project domain glossary (`CONTEXT.md`) and architectural analysis docs with the multi-part domain models and policies.

**Blocked by:** #57: feat(full-report): post-processing multi-part discovery & sequential PDF merge.

<!-- status: closed -->
**Status:** closed

- [x] Create a self-contained synthetic VCB benchmark fixture in `tests/benchmarks/` for PE 157 PERPUSTAKAAN AWAM:
  - 5-panel TAMCO VCB 11kV lineup with transition bay, PT on panel 4, 1 transformer, 1 feeder pillar, and 1 inline CBM defect page.
  - Minimal testsheet Excel workbook, stub panel thermal/visual photos, and pre-sliced Quick Report sections based on existing PE 157 fixture data in `tests/test_full_report_scan_models.py`.
- [x] Update CLI dry-run telemetry in `src/project_workflow_actions.py`:
  - `_print_full_report_dry_run_telemetry`: display multi-part indicators (such as `[Multi-part: X files]`) when a substation is planned for partitioning.
  - `_print_full_report_postprocessing_dry_run_telemetry`: display multi-part file grouping (such as `[X docx parts -> 1 pdf deliverable]`).
- [x] Add end-to-end verification tests in `tests/test_full_report_multipart_e2e.py` validating:
  - Full lifecycle execution from testsheet package to final stitched PDF for a 5-panel VCB switchgear (including PT, transition bay, and inline defect detail pages).
  - Regression validation that standard RMU benchmarks (PE 005, PE 144, PE 179) remain single-document deliverables without unintended partitioning.
- [x] Update `CONTEXT.md` with new domain vocabulary:
  - `PlanDocumentChunk`
  - `MultiPartPartitionPolicy`
  - `MultiPartDocumentDeliveryPolicy`
  - `MultiPartPdfStitchingPolicy`
- [x] Update `docs/full_report_domain_analysis.md` Section 4 and Section 5 with multi-part delivery conventions and architectural policies.
