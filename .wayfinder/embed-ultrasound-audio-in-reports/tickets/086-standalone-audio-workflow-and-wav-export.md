<!-- status: open -->
Part of Wayfinder Map: [map.md](../map.md)
GitHub Issue: [#86](https://github.com/adamlarGit/pahang-cli/issues/86)
Specification: [spec.md](../spec.md)

# 086: feat(workflow): standalone US audio generation & retroactive PDF sound embedding workflow

**What to build:** Core workflow engine (`UsAudioWorkflow` in `src/workflows/us_audio.py`) coordinating both standalone 16-bit WAV audio file export into `<SUBSTATION>/RAW DATA/US+TEV/sounds/` and retroactive PDF sound embedding across Full Report and Quick Report `<STEM>.pdf` deliverables. Enforces `UsTevAudioResiliencePolicy` and `SubstationIsolatedBatchResiliencePolicy` across batch executions.

**Blocked by:** #084, #085.

**Status:** ready-for-agent

- [ ] Create `src/workflows/us_audio.py` module.
- [ ] Define domain models:
  - `UsAudioCandidate`: Dataclass containing `package`, `raw_data_dir`, `survey_dir`, `sounds_output_dir`, `full_report_pdf`, `quick_report_pdf`.
  - `UsAudioWorkflowSummary`: Dataclass tracking `total_substations`, `total_wavs_exported`, `total_sounds_embedded`, `errors`, and `elapsed_time`.
- [ ] Implement `export_substation_16bit_wavs(survey_root: Path, output_dir: Path) -> list[Path]`:
  - Discovers all US measurements via `discover_survey_measurements(survey_root)`.
  - Iterates measurements and locates `8k.wav`.
  - Asserts `8k.wav` exists and is non-empty; if missing, raises `FileNotFoundError` (fail-loud invariant).
  - Directly consumes canonical deduplicated label `meas.label` (`SurveyMeasurementNaming`) to ensure 100% naming parity and duplicate counter safety with PRPD graphs.
  - Exports standard 16-bit WAV to `<output_dir>/{meas.label}.wav` with idempotent overwrite.
  - Returns list of generated `.wav` paths.
- [ ] Implement `embed_survey_ultrasound_into_pdf(pdf_path: Path, survey_root: Path | None, package: SubstationTestsheetPackage | None = None) -> int`:
  - Validates `pdf_path.is_file()`. If survey root is missing, logs `INFO` and returns 0 (`UsTevAudioResiliencePolicy`).
  - Pre-flight unlinks any stale `.tmp_sound_{pdf.name}` in `pdf_path.parent`.
  - Uses context-managed PyMuPDF session (`with fitz.open(pdf_path) as doc:`) to guarantee handle closure:
    - Caches discovered US measurements for `survey_root`.
    - Iterates pages:
      - Finds `"Sound clip"` anchor using `find_sound_clip_anchor(page)` (centered in Column 2).
      - If found, extracts context using `extract_page_equipment_context(page, package=package)` (`TwoTierPanelMatchingPolicy`).
      - Resolves matching `8k.wav` via `resolve_measurement_audio_for_page()` (applying `VcbAudioAttributionPolicy` with tie-breaking, `TransformerAudioAttributionPolicy` with prefix tolerance, and `RmuAudioAttributionPolicy` with board fallback).
      - Downscales 24-bit to 16-bit PCM in memory via `convert_24bit_wav_to_16bit_pcm()`.
      - Injects sound annotation idempotently via `embed_sound_annotation()` (`IdempotentSoundEmbeddingPolicy`).
    - Writes modified PDF bytes to `.tmp_sound_{pdf.name}` in the same directory.
  - Enforces `AtomicPdfSavePolicy`: outside document context (handles closed), replaces `pdf_path` atomically via `os.replace(tmp_path, pdf_path)`, guarded with `try...finally` to ensure temp file cleanup on error.
  - Returns total count of inserted/updated sound annotations.
- [ ] Implement `UsAudioWorkflow`:
  - Supports execution modes: `"export_wav"`, `"embed_pdf"`, `"both"`.
  - Implements `run_substation(...)` and `run_batch(...)`.
  - Enforces `SubstationIsolatedBatchResiliencePolicy`: isolates single-substation exceptions, appends to `summary.errors`, and continues batch queue.
- [ ] Implement unit and workflow tests in `tests/test_us_audio_workflow.py`:
  - Test WAV export writes canonical `{ASSET}_{SUBASSET}_{COMPONENT}_US.wav` files and fails loudly if `8k.wav` is missing.
  - Test retroactive PDF embedding modifies deliverable PDF idempotently without leaking duplicate annotations.
  - Test `AtomicPdfSavePolicy` releases handles cleanly on Windows, unlinks stale temp files, and cleans up on exceptions.
  - Test missing survey directory returns 0 without raising an exception (`UsTevAudioResiliencePolicy`).
  - Test batch resilience isolates corrupted file error and finishes valid candidates.
