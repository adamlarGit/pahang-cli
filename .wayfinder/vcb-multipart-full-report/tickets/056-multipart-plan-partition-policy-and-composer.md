<!-- status: closed -->
Part of #55
Specification: [spec.md](../spec.md)

# 056: feat(full-report): multi-part partition policy & composer chunking

**What to build:** An automated partitioning and multi-document compilation feature for Full Report generation. When generating a Full Report for a substation with VCB or GIS switchgear, the system partitions the document into manageable Word files (Part 01 for summary and overview, Parts 02 to N+1 for each individual bay, and Part N+2 for transformers, LVDB, condition photos, and stickers). Prior to compilation, any pre-existing part documents matching `f"{exact_stem} - Part *.docx"` are purged. Intermediate files are rendered once, and compiled into subsets per chunk. Non-VCB/GIS substations continue generating as a single Word document.

**Blocked by:** None (can start immediately).

**Status:** Closed

- [x] Define `PlanDocumentChunk` dataclass in `src/full_report/models.py` (or `plan_builder.py`) representing a planned output Word file with `chunk_index: int`, `label: str`, `output_filename: str`, `destination_path: Path`, and `parts: tuple[PlanPartItem, ...]`.
- [x] Implement `MultiPartPartitionPolicy` in `src/full_report/plan_builder.py`:
  - Check switchgear archetype via `plan.package.switchgears[0].archetype` (or `plan.package.switchgear.archetype`):
    - For `SwitchgearArchetype.VCB_CUBICLE` or `SwitchgearArchetype.GIS_CUBICLE`, partition planned parts into:
      - Chunk 1: `Part 01 - Summary` (Front page, Executive Summary Census, Visual Defect Summary, Switchgear Overview).
      - Chunk 2..N+1: `Part {idx:02d} - Panel {no} ({name})` (Chambers for panel: Cable, Breaker, Busbar, Secondary, PT, plus any inline TEV/IR defect pages for that panel).
      - Chunk N+2: `Part {last_idx:02d} - TX and Condition` (Transformers, LVDB/FP, Battery Bank, Condition Pages, Visual Defect Pages, Sticker Page).
    - For all other archetypes (RMU SF6, Oil, Standard), emit a single chunk with `<STEM>.docx`.
- [x] Update `FullReportStationPlan` to expose `chunks: tuple[PlanDocumentChunk, ...]` and `is_multipart: bool`.
- [x] Update `FullReportComposer.compose()` in `src/full_report/composer.py`:
  - Execute single-pass rendering: call `plan.render_all()` once in the temp workspace to produce all indexed intermediate part files.
  - Partition the rendered file list by chunk boundaries (matching each chunk's part count and order).
  - For each chunk, call `self.compiler.compile(chunk_parts, chunk.destination_path)`.
  - Implement safe exact-stem pre-purge: delete any files matching `f"{exact_stem} - Part *.docx"` in destination directory before compiling chunks.
  - Return updated `FullReportCompilationResult` capturing all chunk output paths.
- [x] Update `FullReportStationExecutionResult` in `src/workflows/full_report.py`:
  - Keep `output_path: Path | None` pointing at the primary output (`Part 01` for multi-part, single `.docx` for RMU).
  - Add `chunk_paths: tuple[Path, ...] = ()` containing all generated chunk paths.
  - Add `is_multipart: bool = False`.
- [x] Update `FullReportBatchResult.generated_paths` to flatten all chunk paths across results.
- [x] Update workflow deliverable verification pipeline to check existence and attribution for each path in `chunk_paths`.
- [x] Add unit tests in `tests/test_full_report_plan_builder.py` and `tests/test_full_report_composer.py` with `FakeDocumentCompiler` validating partitioning, file naming, and chunk compilation across VCB (with 5 panels, PT, transition bay, inline defect pages) and RMU (single chunk).
