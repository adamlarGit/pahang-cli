<!-- status: closed -->
Part of Wayfinder Map: [map.md](../map.md)
GitHub Issue: [#88](https://github.com/adamlarGit/pahang-cli/issues/88)
Specification: [spec.md](../spec.md)

# 088: feat(pipeline): automatic post-processing sound embedding for Full Report & Quick Report

**What to build:** Seamless post-merge sound embedding hooks integrated directly into `FullReportPostProcessingWorkflow` and `PostProcessingPipelineWorkflow`. Embeds sound annotations automatically into the final unified `<STEM>.pdf` whenever an UltraTEV survey folder exists, while gracefully degrading without error when raw US data is absent (`UsTevAudioResiliencePolicy`).

**Blocked by:** #086 (standalone audio workflow engine).

**Status:** closed

- [x] Integrate post-processing hook in `src/workflows/full_report_postprocessing.py`:
  - Update `_compile_deliverable(self, group, testsheet_pdf_path, output_pdf_path, *, environment: ProjectEnvironment | None = None, ...)` to receive `environment`.
  - In `process()` (and `process_single()`), pass `environment` into `_compile_deliverable()`.
  - At the unified exit point of `_compile_deliverable` immediately following both multi-part (`group.is_multipart`) and single-file PDF merges:
    - Extract path tokens `(station, month, date_str, pe_num)` from `group.primary_docx_path` (using `extract_numerical_prefix(group.stem)`).
    - If `environment` is provided:
      - Resolve raw directory: `raw_dir = environment.storage.get_substation_raw_data_dir(station, month, date_str, pe_num)`.
      - Discover survey root: `survey_root = discover_ultratev_survey_dir(raw_dir)`.
      - If `survey_root` exists:
        - Call `embed_survey_ultrasound_into_pdf(output_pdf_path, survey_root=survey_root)`.
        - Relies on Row 4 `Panel Name` extraction in `extract_page_equipment_context` to match feeder folders via `find_swg_feeder_survey_dir` without requiring `package`.
        - Enforces `IdempotentSoundEmbeddingPolicy` so multiple post-processing passes do not duplicate annotations.
        - Log progress: `"[FULL REPORT] Embedded {count} ultrasound sounds into {output_pdf_path.name}"`.
      - If `survey_root is None`:
        - Log non-blocking notice: `"[FULL REPORT] No US+TEV raw data found for {stem}; skipping sound embedding"`.
- [x] Integrate post-processing hook in `src/workflows/postprocessing_pipeline.py`:
  - Locate `execute()` in `PostProcessingPipelineWorkflow` around line 230:
    - Immediately following Step 6 (`self._converter.merge_pdfs(quick_report_pdf, testsheet_pdf, quick_report_pdf)`):
    - Resolve date folder, month, station from `pkg.testsheet_xlsx.parent`.
    - Resolve `raw_dir = env.storage.get_substation_raw_data_dir(pkg.station_name, month, date_str, pkg.substation_number)`.
    - Discover `survey_root = discover_ultratev_survey_dir(raw_dir)`.
    - If present, call `embed_survey_ultrasound_into_pdf(quick_report_pdf, survey_root=survey_root, package=pkg)`.
    - Log progress or non-blocking notice.
- [x] Protect with guarded execution blocks:
  - If unexpected error occurs during sound injection, catch exception, log warning (`"[WARN] Sound embedding failed for %s: %s; keeping original PDF"`), and do not halt the post-processing pipeline.
- [x] Implement pipeline integration unit tests in `tests/test_pipeline_sound_integration.py`:
  - Test Full Report delivery includes sound annotations when survey data is supplied.
  - Test Full Report deliverable remains valid and unmodified when survey data is missing.
  - Test Quick Report deliverable includes sound annotations on CBM defect pages when survey data is supplied.
  - Test Quick Report compiles cleanly when survey data is missing.
