<!-- status: closed -->
# Ticket #127: feat(survey): Polymorphic US and US+TEV discovery across graph, audio, and sound embedding workflows

## Parent
Part of #90

## What to build
Standardize survey discovery and output directory resolution across all workflows so that substation raw data folders named either `US` (canonical for 33kV) or `US+TEV` (canonical for 11kV) work interchangeably and polymorphism is fully respected:

- **Survey Discovery (`src/quick_report/prpd.py`)**:
  - Update `discover_ultratev_survey_dir()` to check `raw_path / "RAW DATA" / "US"` and `raw_path / "US"` in `candidate_roots` (ordered after `US+TEV` candidates to preserve 11kV priority).
  - This immediately eliminates the slow recursive `rglob("survey_summary.js")` fallback on 33kV datasets, restoring O(1) survey root discovery.
- **Pre-generated Graph Lookup (`src/quick_report/prpd.py`)**:
  - Update `find_pregenerated_prpd_graph()` (lines 1340–1352) to check `US/graphs/` candidates alongside `US+TEV/graphs/`.
- **Standalone US+TEV Graphs Workflow (`src/workflows/us_tev_graphs.py`)**:
  - In `discover_us_tev_candidate_substations()` and `run_substation()` / `run_batch()`, dynamically resolve output directory using a 2-level bounded container check (`survey_dir.name` then `survey_dir.parent.name` for `"US"` or `"US+TEV"`).
  - Target `<SUBSTATION>/RAW DATA/<CONTAINER>/graphs/` instead of hardcoding `US+TEV`.
  - If neither container is found, raise `ValueError` (caught and logged per-substation by `SubstationIsolatedBatchResiliencePolicy`).
- **Ultrasound Audio Workflow (`src/workflows/us_audio.py`)**:
  - In `resolve_sounds_output_dir()`, eliminate the duplicate return dead-code bug at lines 88–89.
  - Implement 2-level bounded container check matching `us_tev_graphs.py` to anchor standalone 16-bit WAV exports to `<SUBSTATION>/RAW DATA/<US or US+TEV>/sounds/`.
  - If neither container is found, raise `ValueError`.
- **Sound Embedding Transitive Fix (`src/workflows/full_report_postprocessing.py` & `src/workflows/postprocessing_pipeline.py`)**:
  - Verifies that post-processing sound embedding seamlessly locates `8k.wav` for both `US` and `US+TEV` structures transitively via updated `discover_ultratev_survey_dir()`.

## Acceptance criteria
- [x] `discover_ultratev_survey_dir()` in `src/quick_report/prpd.py` includes `raw_path / "RAW DATA" / "US"` and `raw_path / "US"` in `candidate_roots` after `US+TEV`.
- [x] `find_pregenerated_prpd_graph()` in `src/quick_report/prpd.py` includes `US/graphs` candidates for survey root and feeder directories.
- [x] `discover_us_tev_candidate_substations()` and `run_substation()` in `src/workflows/us_tev_graphs.py` resolve output directory to `<SUBSTATION>/RAW DATA/<CONTAINER>/graphs/` via 2-level bounded container check, raising `ValueError` if neither `US` nor `US+TEV` is detected.
- [x] `resolve_sounds_output_dir()` in `src/workflows/us_audio.py` eliminates the duplicate return bug and resolves output to `<SUBSTATION>/RAW DATA/<CONTAINER>/sounds/` via 2-level bounded container check, raising `ValueError` if neither container is detected.
- [x] Full Report and Quick Report CBM defect page rendering tests pass against both `US` and `US+TEV` structures without triggering recursive tree fallbacks.
- [x] Unit and mock tests verify discovery, graph lookup, and audio destination resolution for both 11kV (`US+TEV`) and 33kV (`US`) structures.

## Blocked by
- #126 (Closed)
