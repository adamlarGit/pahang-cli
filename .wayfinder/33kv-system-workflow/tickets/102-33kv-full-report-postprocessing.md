<!-- status: settled -->
Part of #90
Specification: [spec.md](../spec.md)

# 102: feat(33kv-full-report-postprocessing): 33kV Full Report multi-part PDF batch conversion, stitching, and testsheet merge

**What to build:** Extend `FullReportPostProcessingWorkflow` to discover 33kV multi-part document chunks (`<STEM> - Part *.docx`), batch convert them to PDF, concatenate them in numerical sequence, and append the signed 33kV testsheet PDF to produce the unified client deliverable `<STEM>.pdf`.

**Blocked by:** #97, #101

**Status:** ready-for-agent

- [ ] Ensure `_group_multipart_targets()` in `src/workflows/full_report_postprocessing.py` groups 33kV multi-part Word documents by their substation stem (e.g. `06. SSU FLEXSYS CHEMICAL 33kV (VI)`), while transparently retaining standalone single-file fallback (Decision Q85).
- [ ] Extend `_find_pdf_in_dirs()` Phase 2 prefix matching to check `f"{prefix_num:02d}."` for 2-digit zero-padded testsheet PDFs alongside 3-digit and unpadded formats (Decision Q80).
- [ ] Strictly enforce D43 fail-fast pre-flight validation: require pre-existing signed testsheet PDF in `processed_testsheet/pdf/<STEM>.pdf` before conversion (Decision Q81).
- [ ] Convert each part sequentially to PDF via `ComDocumentConverter.convert_docx_to_pdf` inside a shared `BatchComSession`, following 100% 11kV parity with single batch session execution without per-substation recycling (Decision Q84).
- [ ] Concatenate parts in strict numerical order using `converter.merge_pdfs_batch()`.
- [ ] Append signed 33kV testsheet PDF from `processed_testsheet/pdf/<STEM>.pdf` as the final section, outputting `<STEM>.pdf` in the substation date directory (Decision Q83).
- [ ] Automatically clean up intermediate temporary `.tmp_conv_*` PDFs in a `finally` block while preserving the original `.docx` chunks permanently per ADR 0005 (Decision Q82).
- [ ] Add integration tests in `tests/test_full_report_postprocessing_33kv.py` verifying multi-part conversion and deliverable concatenation.

