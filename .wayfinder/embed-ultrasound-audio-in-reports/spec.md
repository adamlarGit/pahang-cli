# Specification: Automated Ultrasound Audio Embedding & 16-Bit Audio Generation

## Problem Statement
High Voltage (HV) equipment condition assessments require acoustic ultrasound (US) inspections to detect partial discharge (corona, tracking, arcing, and mechanical vibration). In Pahang CLI, generated deliverables—specifically Full Reports and Quick Reports—currently include Phase-Resolved Partial Discharge (PRPD) scatter plots and measurement tables, but lack embedded acoustic audio recordings. Inspectors and client engineers reviewing deliverable PDFs must manually search external folder structures to listen to audio clips corresponding to specific switchgear panels or transformer compartments.

Furthermore, field instrument data analysis from UltraTEV Plus 2 surveys reveals two critical technical challenges:
1. **24-bit Audio Incompatibility**: Raw ultrasound audio files (`8k.wav`, `10k.wav`, `192k.wav`) recorded by UltraTEV instruments are encoded in **24-bit PCM** (`sampwidth=3`). The ISO 32000-1 PDF specification (§13.3 Sound Objects) and Adobe Acrobat's internal audio playback engine strictly support only **8-bit or 16-bit PCM**. Directly embedding raw 24-bit files causes silent failure, player errors, or loud static noise.
2. **Disk Constraints & Retroactive Processing**: Due to operator local disk limitations, raw US+TEV survey materials are not always present during initial report compilation. When operators later transfer survey folders to disk, they need a mechanism to:
   - Export converted, standard 16-bit WAV files into `<SUBSTATION>/RAW DATA/US+TEV/sounds/` for archival and manual inspection.
   - Retroactively embed ultrasound audio into previously generated Full Report and Quick Report deliverable PDFs without re-running entire Word COM automation suites.

## Solution
Deliver an integrated ultrasound audio conversion, export, and PDF annotation capability across the Pahang CLI:
1. **Pure-Python In-Memory 24-to-16-Bit PCM Downscaler**: A lightweight, zero-binary converter using Python's standard library `wave` and `bytearray` slice assignment (`sample >> 8`), executing in ~1.2 ms with 0 bytes written to temporary disk.
2. **ISO 32000-1 Low-Level Sound Annotation Engine**: An xref-based PyMuPDF injection service that embeds compliant `/Subtype /Sound` objects and links them to speaker annotations positioned cleanly inside the `"Sound clip"` table cells present in switchgear and transformer scanning templates.
3. **Deterministic Measurement-to-Page Matching Engine**: An asset matching engine that parses PDF pages, locates `"Sound clip"` markers, extracts panel/feeder number and compartment area, and pairs each page with its corresponding `8k.wav` recording from UltraTEV survey data.
4. **Standalone CLI Utility Workflow (`UsAudioWorkflow`)**: A dedicated utility action in the CLI Utilities menu providing:
   - Retroactive PDF sound embedding into existing `<STEM>.pdf` deliverables.
   - 16-bit WAV audio regeneration into `<SUBSTATION>/RAW DATA/US+TEV/sounds/{label}.wav` adhering to canonical naming schema `{ASSET}_{SUBASSET}_{COMPONENT}_US.wav`.
5. **Automatic Post-Processing Pipeline Integration**: Seamless post-processing hooks in `FullReportPostProcessingWorkflow` and `PostProcessingPipelineWorkflow` that embed sounds automatically on final deliverable PDFs when raw US+TEV data is present.
6. **Robust Missing Data Resilience (`UsTevAudioResiliencePolicy`)**: Non-blocking diagnostics and clean fallback when US+TEV surveys or individual compartment recordings are absent, guaranteeing zero report generation failures.

---

## User Stories

1. **As an inspection review engineer**, I want clickable sound annotations embedded in deliverable PDFs on each high-voltage equipment scanning page, so that I can immediately listen to acoustic partial discharge audio inside Adobe Acrobat or Foxit Reader without hunting for raw files.
2. **As a client recipient (TNB)**, I want embedded ultrasound audio to play smoothly without static noise or playback errors, ensuring adherence to standard 16-bit audio formatting.
3. **As a CLI operator**, I want an option labeled `"Generate US 16-bit audio & embed sounds into PDFs"` in the Utility Actions menu, so that I can process ultrasound audio on demand without re-running full report generation.
4. **As a CLI operator**, I want the utility action to offer a choice between embedding sounds into existing PDFs, exporting converted 16-bit WAV files to disk, or executing both simultaneously.
5. **As an operator with limited disk space**, I want the report generation pipeline to continue successfully without crashing or halting when US+TEV raw data is missing on disk (`UsTevAudioResiliencePolicy`), cleanly leaving `"Sound clip"` cells blank.
6. **As an operator who transfers raw data later**, I want to retroactively run the utility action on pre-compiled `<STEM>.pdf` files, so that I can add sound annotations after freeing disk space and copying the survey files.
7. **As a reliability technician**, I want regenerated 16-bit WAV files to be systematically named with their engineering asset and compartment tokens (e.g. `VCB_PANEL_1_CABLE_BOX_US.wav`, `VCB_PANEL_1_CIRCUIT_BREAKER_US.wav`, `TX1_TRANSFORMER_PRIMARY_CABLES_US.wav`) inside `<SUBSTATION>/RAW DATA/US+TEV/sounds/`, so that audio files can be identified and verified at a glance.
8. **As a system administrator**, I want all 24-bit to 16-bit audio conversion to happen in pure Python without requiring external system dependencies like `ffmpeg` or `sox`, so that deployment across field laptops remains seamless.
9. **As a report designer**, I want speaker annotation icons to be positioned precisely within the designated `"Sound clip"` table cells already present in `swg-panel.docx` and `tx-hv-sides.docx` templates, so that the document visual layout remains clean and professional.
10. **As a Quick Report reviewer**, I want sound annotations to appear only on CBM Defect detail pages where an active ultrasound defect was identified, leaving regular visual condition pages uncluttered.
11. **As a Full Report reviewer**, I want every surveyed HV switchgear chamber (Breaker, Cable, Busbars, PT) and transformer HV side page to contain its corresponding sound clip, matching the comprehensive asset census of the Full Report.
12. **As an operations manager**, I want batch execution across multiple dates and substations to be isolated (`SubstationIsolatedBatchResiliencePolicy`), so that an unexpected error on one substation's audio file does not interrupt the rest of the queue.

---

## Implementation Decisions

### Decision 1: Pure-Python In-Memory 24-to-16-Bit PCM Downscaler
- **File & Mechanism**: Implemented in `src/postprocessing/sound_embedder.py` using Python's standard library `wave` and `bytearray`.
- **Downscaling Arithmetic**: UltraTEV 24-bit PCM samples are stored as 3 little-endian bytes `[b0, b1, b2]`. Shifting right by 8 bits (`sample >> 8`, dividing by 256) mathematically discards the least-significant byte `b0` and retains bytes `[b1, b2]`.
- **Performance & Disk Overhead**: Slice assignment `out[0::2] = raw[1::3]` and `out[1::2] = raw[2::3]` downscales a ~10-second 8 kHz mono recording in **1.2 ms** with **0 bytes of intermediate disk I/O**.
- **Dual Output**:
  - `convert_24bit_wav_to_16bit_pcm(wav_path) -> tuple[bytes, int, int]`: Returns in-memory `(pcm_bytes, framerate, channels)` for direct PDF embedding.
  - `export_16bit_wav(src_wav_path, dest_wav_path) -> Path`: Writes standard 16-bit WAV file with valid RIFF headers to disk for standalone archival.

### Decision 2: Target Audio Track Selection (`8k.wav`)
- UltraTEV survey folders contain `8k.wav`, `10k.wav`, and `192k.wav`.
- **Authoritative Selection & Mandatory Presence**: Strictly select `8k.wav`.
- **Fail-Loud Invariant**: `8k.wav` must exist and be non-empty for every ultrasound measurement. If `8k.wav` is missing or 0 bytes in a measurement directory, the engine must fail loudly (raising `FileNotFoundError` in converter functions or recording an explicit failure in the workflow summary). Zero fallback to `10k.wav` or `192k.wav` is permitted.
- **Rationale**:
  - `8k.wav` is the demodulated heterodyne signal (0–4 kHz audible spectrum) rendered by UltraTEV's native `Ultrasonic.html` web player.
  - `192k.wav` is raw ultrasonic transducer sampling (5.75 MB per page), inaudible to human ears, and would bloat a 12-page PDF deliverable by ~45 MB.
  - Converted `8k.wav` requires only ~160 KB per page (~1.9 MB total overhead for a typical substation PDF).

### Decision 3: Low-Level ISO 32000-1 Sound Annotation Injection
- PyMuPDF 1.26.3 lacks high-level `page.add_sound_annot()` (raising `AttributeError`).
- Injection is implemented using PyMuPDF low-level cross-reference (`xref`) stream methods:
  1. Allocate new xref for Sound Object:
     ```text
     << /Type /Sound /R 8000 /C 1 /B 16 /E /Signed >>
     ```
  2. Populate stream with 16-bit PCM bytes via `doc.update_stream(sound_xref, pcm_bytes)`.
  3. Allocate new xref for Sound Annotation:
     ```text
     << /Type /Annot /Subtype /Sound /Rect [x0 y0 x1 y1] /Sound <sound_xref> 0 R /Name /Speaker /F 4 /P <page_xref> 0 R >>
     ```
  4. Append annotation xref to page `/Annots` array.
- **Coordinate Conversion**: Converts PyMuPDF coordinates (top-left origin) to PDF points (bottom-left origin):
  `pdf_y0 = page_h - rect.y1`, `pdf_y1 = page_h - rect.y0`.
- **Idempotency Guard (`IdempotentSoundEmbeddingPolicy`)**:
  Before injecting a sound annotation, inspect existing annotations on the page. If a `/Subtype /Sound` annotation already intersects `sound_rect`, either update its sound object stream directly via `doc.update_stream(existing_sound_xref, pcm_bytes)` or replace it cleanly, strictly preventing duplicate stacked speaker icons and redundant sound stream bloat.
- **Indirect `/Annots` Handling**:
  Check `doc.xref_get_key(page.xref, "Annots")`. If stored as an indirect object reference (`('xref', '<xref> 0 R')`), resolve and update the indirect xref array directly rather than overwriting page key with an unlinked string, preserving PDF cross-reference integrity across diverse PDF compilers.

### Decision 4: Anchor & Positioning via `"Sound clip"` Marker (`SoundClipAnchorPolicy`)
- Templates `swg-panel.docx` and `tx-hv-sides.docx` across Full Report and Quick Report contain Table Row 31 structured as a key-value pair:
  - Column 1 ($x \in [64.4, 184.6]\text{ pt}$): Label cell containing literal text `"Sound clip"` ($x \in [66.9, 113.0]\text{ pt}$).
  - Column 2 ($x \in [185.0, 305.1]\text{ pt}$): Empty value cell situated directly beneath the ultrasound measurement values (`{{ us.reading }}dB`, `{{ us.char }}`, `{{ us.severity }}`).
- Detection uses `page.search_for("Sound clip")`.
- **Icon Placement**:
  To ensure visual alignment with the data reading cells above, the 18x18 pt speaker annotation rectangle is centered inside **Column 2**:
  `sound_rect = fitz.Rect(236.0, inst.y0 - 2, 254.0, inst.y1 + 2)`.
- If `"Sound clip"` text is absent on a page (e.g. overviews, condition photos, summaries, sticker pages, or non-acoustic secondary control compartments), that page is safely skipped.

### Decision 5: Deterministic Page-to-Measurement Matching Engine & Attribution Policies
- **Shared Feeder Matching Engine**: Reuses and modularizes the battle-tested 3-tier precedence logic from `find_swg_feeder_survey_dir` and `find_tx_survey_dir` in `src/quick_report/prpd.py` to ensure complete parity between PRPD graph generation and audio embedding.
- **`TwoTierPanelMatchingPolicy`**:
  - *Tier 1 (Direct Digit Extraction)*: Extracts explicit panel digits from `Panel No.` if present (`r"Panel No\.\s*[:\n\r]*\s*([A-Za-z0-9_\-]+)"`, capturing `1`, `Panel 1`, `1 (CRB70001)` $\to$ `1`).
  - *Tier 2 (Package Feeder Catalog Fallback)*: When `Panel No.` contains an unnumbered utility code (e.g. `CRB00764`) or descriptive name, matches against the substation's `SubstationTestsheetPackage` equipment panel list (`panel.panel_feeder_no` or `panel.name`) to resolve the canonical 1-based sequential `panel.panel_no`.
  - *Decoupled Panel Context Extraction*: `extract_page_equipment_context` extracts both `Panel No.` (Row 3, capturing digits) and `Panel Name` (Row 4, `r"Panel Name\s*[:\n\r]*\s*([^\n\r]+)"`). This enables `find_swg_feeder_survey_dir` to resolve feeder folders by `panel_name` directly even when `package` is `None`.
- **`VcbAudioAttributionPolicy`**:
  - *Strict 1-to-1 Chamber Attribution*:
    - `BREAKER COMPARTMENT` $\longleftrightarrow$ `$CIRCUIT_BREAKER`
    - `CABLE COMPARTMENT` $\longleftrightarrow$ `$CABLE_BOX` (or `$CABLES`)
    - `BUSBAR COMPARTMENT` $\longleftrightarrow$ `$UPPER_BUSBARS` / `$LOWER_BUSBARS` / `$BUSBAR`
    - `PT COMPARTMENT` $\longleftrightarrow$ `$VT_CHAMBER` / `$VOLTAGE_TRANSFORMER`
  - *Zero Cross-Chamber Leaking*: If a VCB panel has only 1 recording (e.g. `$CIRCUIT_BREAKER` on a spare bay), it applies strictly to that compartment's page and is **never** cloned into Cable Box or Busbar pages.
  - *Multi-Measurement Disambiguation*: If a survey contains multiple measurements within the same physical compartment: for busbars, prioritize `$UPPER_BUSBARS` over `$LOWER_BUSBARS`; for duplicate component measurements, select the recording with the highest ultrasound dB reading.
  - *Unmeasured Chambers*: Unmeasured primary compartments and non-acoustic `SECONDARY COMPARTMENT` leave the `"Sound clip"` cell completely empty with zero sound annotations injected.
- **`TransformerAudioAttributionPolicy`**:
  - Field surveys record 1 ultrasound measurement per transformer tank (e.g. `$PRIMARY_CABLES` or `TRANSFORMER_US`).
  - This single recording is shared across all active HV side scanning pages (`HV CABLE`, `HV BUSHING`, and `HV CABLE SPLIT` via `tx-hv-sides.docx`) for that transformer unit.
  - *Regex Tolerance*: Matches `Tx No.` with optional prefix tolerance: `r"Tx No\.\s*[:\n\r]*(?:TX|Tx|TRANSFORMER)?\s*(\d+)"` and `r"(?:Tx No\.|TX)\s*[:\n\r]*\s*(?:TX)?\s*(\d+)"` to accommodate `TransformerScanAdapter` emitting normalized `"TX1"`, `"TX2"` as well as bare numbers.
- **`RmuAudioAttributionPolicy`**:
  - In compact Ring Main Units (`RMU_STANDARD`, `RMU_DUAL_CABLE_ENTRY`), single untagged US recordings (where `$COMPONENT` is `None` or `$NONE` in `RMU_FEEDER_1_US`) automatically match the panel's active scanning page (`CABLE COMPARTMENT`).
  - *Board-Level Acoustic Fallback*: If an RMU survey lacks feeder subfolders (`FEEDER_1`, `FEEDER_2`) but contains a single board-level acoustic measurement (`RMU_US` or `SWG_US`), attribute that single recording to all active RMU cable scanning pages (reflecting the common hermetic SF6 tank), while strictly keeping 1-to-1 chamber isolation for modular VCB cubicles.

### Decision 6: Output Destinations & Systematic Naming (`SurveyMeasurementNaming`)
1. **Embedded PDF**: Modified atomically on the final client deliverable:
   - Full Report: `FULL REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.pdf`
   - Quick Report: `QUICK REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.pdf`
2. **Exported 16-bit WAV Files**:
   - Destination: `RAW MATERIAL/<STATION>/<MONTH>/<DATE>/<SUBSTATION>/RAW DATA/US+TEV/sounds/`
   - Naming: Directly consumes `meas.label` from `DiscoveredMeasurement`:
     `output_dir / f"{meas.label}.wav"`
   - Guarantees 100% naming parity and automatic duplicate counter handling (`_2`, `_3`) with PRPD graph generation:
     - `VCB_PANEL_1_CIRCUIT_BREAKER_US.wav`
     - `VCB_PANEL_1_CABLE_BOX_US.wav`
     - `VCB_PANEL_1_UPPER_BUSBARS_US.wav`
     - `TX1_TRANSFORMER_PRIMARY_CABLES_US.wav`

### Decision 7: Post-Merge Pipeline Integration Point
- Embedding is hooked **strictly after Word COM export and testsheet merging** are complete:
  - In `FullReportPostProcessingWorkflow._compile_deliverable(self, group, testsheet_pdf_path, output_pdf_path, environment=...)`:
    Hooked at the unified exit point following both multi-part (`group.is_multipart`) and single-file merge branches, passing `environment` to resolve `raw_dir`.
  - In `PostProcessingPipelineWorkflow.execute`:
    Hooked immediately following Step 6 (`converter.merge_pdfs(quick_report_pdf, testsheet_pdf, quick_report_pdf)`), resolving `raw_dir` via `env.storage.get_substation_raw_data_dir()`.
- **Rationale**: PyPDF2 does not preserve indirect `/Subtype /Sound` streams during page concatenation. Applying sound embedding to the final unified PDF guarantees 100% sound stream persistence.

### Decision 8: UsTevAudioResiliencePolicy & Atomic File Replacement (`AtomicPdfSavePolicy`)
- Missing raw survey data is handled gracefully:
  - If `discover_ultratev_survey_dir(raw_dir)` returns `None` or directory is absent, logs an `INFO` diagnostic:
    `"[INFO] US+TEV raw survey folder not present for %s; skipping sound embedding"`
    and exits cleanly.
  - If a specific compartment was not measured during the survey, its `"Sound clip"` cell remains blank.
  - If sound embedding raises an exception on a corrupted PDF, the error is caught, logged to `summary.errors`, and the original PDF is preserved intact without failing the batch.
- **`AtomicPdfSavePolicy`**:
  To protect deliverable PDFs against mid-write corruption and Windows file locking handles:
  - Enforces a context-managed document lifecycle (`with fitz.open(pdf_path) as doc:`) to guarantee handle closure before replacing files.
  - Performs pre-flight unlinking of any stale `.tmp_sound_{pdf.name}` files left behind by prior aborted processes.
  - Writes modified PDF bytes to `.tmp_sound_{pdf.name}` in the same directory, closes document handles, and replaces the target file atomically via `os.replace`.
  - Wraps execution in `try...finally` to ensure temporary files are unlinked on unexpected exceptions.

### Decision 9: CLI Utility Action Menu Registration
- Registered at **Position #10 (index 9)** in `UTILITY_ACTIONS` (`src/utility_actions.py`), immediately following `"Generate US+TEV survey graphs"`.
- Label: `"Generate US 16-bit audio & embed sounds into PDFs"`
- Interactive Sub-Menu options:
  1. `Embed ultrasound sounds into existing report PDFs (Full & Quick Report)`
  2. `Export converted 16-bit WAV files to RAW DATA/US+TEV/sounds/`
  3. `Both (Export WAV files and embed into PDFs)`
- **Checklist Readiness Tags & Missing PDF Notice**:
  Candidate checklist items display deliverable PDF status tags (`[{date_str}] {name} [PDF READY]` vs `[{date_str}] {name} [NO PDF]`). If Mode 1 (`Embed into PDFs`) is selected and zero candidate substations possess pre-compiled deliverable PDFs, the runner displays an immediate actionable warning offering to switch to Mode 2 (Export WAV files) or compile reports first.

### Decision 10: Worktree Isolation & Downstream Branch Synchronization Protocol
- **Dedicated Implementation Worktree**:
  All implementation work across tickets #084–#089 is executed strictly inside `C:\Users\ADAM\Desktop\pahang-cli-audio` on feature branch `feature/embed-ultrasound-audio` (branched from `main`).
- **Multi-Session Agent Operating Invariant**:
  When starting or resuming a session, agents discover progress via `git -C C:/Users/ADAM/Desktop/pahang-cli-audio status` and `log`, execute tickets strictly inside `pahang-cli-audio`, and never commit directly to `main` or active peer worktrees (`pahang-cli-33kv`, `pahang-cli-web`).
- **Merge Gate & Downstream Sync**:
  Once 100% green on `pytest`, `feature/embed-ultrasound-audio` is merged into `main` in `pahang-cli`. Subsequently, downstream worktrees (`pahang-cli-33kv` and `pahang-cli-web`) are sequentially updated by merging `main` (verified clean before merging), preventing long-term branch divergence.

---

## Testing Decisions

1. **Audio Converter & Sound Annotator Unit Tests (`tests/test_sound_embedder.py`)**:
   - Test `convert_24bit_wav_to_16bit_pcm` with synthetic 24-bit, 16-bit, and 8-bit WAV byte buffers.
   - Test mathematical fidelity of 24-to-16 bit downscaling (verifying correct right-shift).
   - Test `export_16bit_wav` produces valid RIFF WAV with `sampwidth == 2`.
   - Test `embed_sound_annotation` injects valid `/Subtype /Sound` annotation verified by re-opening with PyMuPDF.
2. **Measurement-to-Page Matching Tests (`tests/test_sound_matching.py`)**:
   - Test matching against simulated PDF pages containing `"Sound clip"` and VCB Panel/Area strings.
   - Test matching against Transformer HV side pages.
   - Test non-matching pages (e.g. Overview, Condition, VI pages) are cleanly ignored.
3. **Workflow Engine & Resilience Tests (`tests/test_us_audio_workflow.py`)**:
   - Test standalone WAV export writes systematic `{ASSET}_{SUBASSET}_{COMPONENT}_US.wav` files into `sounds/`.
   - Test retroactive PDF embedding modifies PDF in-place.
   - Test `UsTevAudioResiliencePolicy`: missing survey root skips cleanly without raising exceptions.
   - Test batch resilience: corrupted substation file isolates error and completes remaining queue.
4. **CLI Integration Tests (`tests/test_us_audio_cli.py`)**:
   - Test interactive prompt selection and runner factory.
   - Test candidate filtering (only substations with valid US+TEV data).
5. **Pipeline Integration Tests (`tests/test_pipeline_sound_integration.py`)**:
   - Test Full Report post-processing hook embeds sounds when survey is present.
   - Test Quick Report post-processing hook embeds sounds on defect detail pages.
   - Test reports compile successfully when survey is absent.

---

## Out of Scope
- Re-encoding or modifying TEV event data into audio (TEV is electrical RF pulse data, not acoustic audio).
- Ingesting or decoding raw undemodulated `192k.wav` ultrasound data.
- Modifying Word `.docx` templates or altering table column widths.
- Real-time audio playback inside Microsoft Word `.docx` files (Word COM automation does not support embedded interactive audio players; audio is strictly an interactive feature of deliverable PDFs).
