Part of #55
Specification: [spec.md](../spec.md)

# 057: feat(full-report): post-processing multi-part discovery & sequential PDF merge

**What to build:** An automated post-processing discovery, multi-part conversion, and sequential PDF merge feature. The post-processing workflow automatically detects whether a substation was generated in multiple Word parts (matching `<STEM> - Part *.docx`). It converts each part document to a temporary PDF using Word COM automation, concatenates the parts in numerical order into a single Full Report PDF via a new `merge_pdfs_batch()` method, appends the signed testsheet PDF from `processed_testsheet/pdf/<STEM>.pdf`, and emits the unified deliverable `<STEM>.pdf`. The original Word part documents remain untouched for inspector editing, and temporary part PDFs are cleaned up.

**Blocked by:** #56: feat(full-report): multi-part partition policy & composer chunking.

**Status:** ready-for-agent

- [ ] Add `merge_pdfs_batch(self, pdf_paths: Sequence[Path], output_pdf: Path) -> Path` to `DocumentConverter` ABC in `src/postprocessing/converters.py`.
- [ ] Implement `merge_pdfs_batch()` in `ComDocumentConverter` using PyPDF2 `PdfWriter` to merge all input PDFs in one pass. Update `FakeDocumentConverter` to record calls in `self.merge_pdfs_batch_calls`. Existing 2-input `merge_pdfs()` remains unchanged.
- [ ] Keep `_discover_docx_files()` in `src/workflows/full_report_postprocessing.py` unchanged to preserve its 5-case discovery logic.
- [ ] Add private method `_group_multipart_targets(docx_paths: list[Path])` downstream of discovery:
  - For paths matching `<STEM> - Part *.docx`, extract `<STEM>` and group paths by stem.
  - Sort each group's part files in ascending order by numerical part index (`Part 01`, `Part 02`, ...).
  - Standalone `<STEM>.docx` files remain single-item targets.
  - Testsheet PDF matching consumes the group `<STEM>`, not individual part file stems.
- [ ] Update `FullReportPostProcessingTelemetry`:
  - Keep `docx_path: Path` as the primary/first `.docx` path.
  - Add `is_multipart: bool = False`.
  - Add `part_docx_paths: tuple[Path, ...] = ()` (all part paths for multi-part; 1-element tuple for single-file).
- [ ] Update `FullReportPostProcessingWorkflow.process()`:
  - For multi-part targets:
    1. Convert each part `.docx` to a substation-scoped temporary PDF (`.tmp_conv_{stem}_part_{idx:02d}.pdf`) via `self._converter.convert_docx_to_pdf()`.
    2. Merge all temporary part PDFs in sequential order into a consolidated full report PDF (`.tmp_conv_{stem}_master.pdf`) via `self._converter.merge_pdfs_batch()`.
    3. Append the signed testsheet PDF from `processed_testsheet/pdf/<STEM>.pdf` to the master PDF, writing directly to the final target deliverable path `<STEM>.pdf`.
    4. Clean up all temporary part PDFs and intermediate files in a `finally` block.
  - For single-file targets, preserve the existing single-conversion and testsheet append path.
- [ ] Ensure original Word part documents (`<STEM> - Part *.docx`) remain untouched in the date folder.
- [ ] Add unit tests in `tests/test_full_report_postprocessing.py` with `FakeDocumentConverter` testing:
  - Discovery and grouping of multi-part files vs single files.
  - Correct order of batch conversion and concatenation across multi-part files via `merge_pdfs_batch()`.
  - Missing testsheet validation and failure handling.
  - Clean cleanup of temporary part PDFs.
