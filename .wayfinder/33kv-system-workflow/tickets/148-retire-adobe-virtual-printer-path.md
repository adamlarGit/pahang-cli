<!-- status: open -->
# Ticket #148: refactor(converters): retire the Adobe PDF virtual-printer path

## Parent
Part of #149 (and #145, #144, #143, #142, #141, #140, whose machinery this ticket deletes).
Implements [ADR 0009](../../../docs/adr/0009-native-export-with-source-image-restoration.md) Decision §1 (supersedes ADR 0008). It removes the machinery added by #140, #142, #143, #144 and #145.

## Context
After #147, Full Report conversion no longer reaches the Adobe path. ADR 0009 removes that path outright, with no flag, once the acceptance gate (#149) has passed. The inventory below comes from the 33kV impact research (01-11-2026).

## What to remove
- **`src/postprocessing/converters.py`**:
  - Acrobat and Distiller process sentinels (`terminate_stray_acrobat_processes`, `terminate_hung_distiller_processes`, `ensure_session_distiller_warmed`)
  - spooler helpers (`drain_word_spooler` where it is only used for printing, `get_printer_jobs_info`, `get_active_printer_job_ids`, `wait_for_printer_job_drain`, `purge_printer_jobs`)
  - `ConversionFeedbackMonitor` and `ConversionFeedbackState`
  - `compute_dynamic_conversion_timeout` and `probe_two_tier_pdf_completion`
  - Distiller joboptions, `PrinterJobControl` and `ViewPrintOutput` registry code
  - `_convert_docx_via_adobe_pdf`, `_find_adobe_pdf_printer`, `_is_distiller_available`, `_export_fixed_format_isolated` (superseded by the #147 temp flow)
  - the `try_adobe_printer` option, in both `ComDocumentConverter` and `FakeDocumentConverter`
  - Distiller handling in `BatchComSession`
- **Exports** in `src/postprocessing/__init__.py`. **Callers** in `workflows/docx_to_pdf.py`, `workflows/postprocessing_pipeline.py`, `workflows/full_report.py` and `workflows/full_report_postprocessing.py`, but only where they reference removed symbols.
- **Tests:** 179 references across 8 files, mainly `test_converters.py` (127), `test_full_report_postprocessing.py`, `test_docx_to_pdf.py`, `test_com_session.py`, `test_postprocessing_orchestrator.py`, `test_full_report_workflow.py`, `unit/test_word_com_recycling.py` and `test_full_report_postprocessing_33kv.py`. Delete tests of removed behaviour and keep the tests of Word session behaviour.

## What to keep (do not remove)
- `BatchComSession` as the shared Word and Excel COM session (ADR 0005 Q84 parity).
- `configure_uniform_printer` and `get_installed_printers`, run once per session for layout metrics (ADR 0009 §1, "Kept"). Excel testsheet conversion also relies on its printer setup.
- `safe_unlink_with_retry` and `safe_replace_with_retry`, which #146 and #147 use.

## Docs
- `CONTEXT.md`: remove or rewrite entries that describe removed behaviour. `InterimPdfFallbackPolicy`, `WordExportConfigurationIsolationPolicy` and `PdfConversionInvestigationSequence` are already marked retired by ADR 0009. Delete them in this ticket.
- `docs/workflows/utility_actions.md` and `docs/full_report_domain_analysis.md`: remove Adobe-printer statements.

## Acceptance criteria
- [ ] `grep -rE "Distiller|PrinterJobControl|ConversionFeedbackMonitor|try_adobe_printer|purge_printer_jobs|ViewPrintOutput" src tests` returns nothing.
- [ ] `configure_uniform_printer` still runs once per batch session, verified by an existing or new test.
- [ ] Pagination of the #149 acceptance reports is unchanged before and after this ticket (page counts equal).
- [ ] All tests pass with zero regressions.

## Blocked by
#149 (the acceptance gate must pass on the new path before the old one is deleted).
