# 7. Ultrasound Audio Embedding and In-Memory 16-Bit Conversion

Date: 2026-10-15
Status: Accepted

## Context

During field condition-based maintenance inspections of distribution substations, acoustic ultrasound measurements are acquired using EA Technology UltraTEV Plus2 instruments. In addition to Phase-Resolved Partial Discharge (PRPD) scatter data, the instrument records acoustic audio tracks:
1. Demodulated audible acoustic track: `8k.wav` (0–4 kHz heterodyne demodulated signal, 8000 Hz sample rate, ~160 KB per 10-second recording).
2. Raw transducer track: `192k.wav` (undemodulated ultrasonic signal, 192 kHz sample rate, ~5.8 MB per 10-second recording).

Field surveys revealed two critical engineering challenges:
1. **Audio Format Incompatibility with ISO 32000-1**: UltraTEV WAV files are encoded in 24-bit PCM (`sampwidth=3`, `int24`). PDF specifications (ISO 32000-1 §13.3) and desktop PDF viewers (notably Adobe Acrobat Reader) fail or reject 24-bit PCM sound streams, requiring downscaled 16-bit PCM (`sampwidth=2`, `int16`, signed little-endian) for native inline playback.
2. **Intermediate Disk I/O Constraints**: Writing converted audio files to disk before embedding introduces heavy filesystem I/O across hundreds of substation directories, cluttering storage and creating stale file synchronization risks.
3. **PyMuPDF Annotation Architecture**: PyMuPDF (fitz 1.26.3) lacks a high-level `page.add_sound_annot()` method. Creating valid ISO 32000-1 `/Subtype /Sound` annotations requires low-level PDF cross-reference (`xref`) manipulation, stream dictionary construction, and indirect `/Annots` array management.
4. **Post-Merge Delivery Integration**: Report generation pipelines (Quick Report and Full Report) construct deliverable PDFs by compiling and concatenating multi-part Word documents and Excel testsheets via Word COM. Sound embedding must occur strictly after PDF compilation without altering upstream COM automation or Word templates.

## Decision

The system implements an end-to-end automated ultrasound audio conversion and PDF sound embedding engine (`src/postprocessing/sound_embedder.py`, `src/workflows/us_audio.py`, and `src/workflows/postprocessing_pipeline.py`):

### 1. Mandatory Demodulated Track Standardization
- Standardize strictly on `8k.wav` as the authoritative audio source. Raw `192k.wav` contains inaudible ultrasonic carrier signals and is excluded from report embedding.
- Enforce a strict **fail-loud invariant**: for any targeted acoustic measurement, `8k.wav` must exist and be non-empty; if missing, raises `FileNotFoundError` with zero silent fallback to `10k.wav` or `192k.wav`.

### 2. In-Memory 24-to-16-Bit PCM Downscaling
- Converted entirely in memory using Python standard library `wave` and `bytearray` slice assignment (`sample >> 8`).
- Zero intermediate disk I/O; typical conversion executes in ~1.2 ms per 10-second clip.
- Returns raw 16-bit PCM bytes (`sampwidth=2`, 8000 Hz, mono) ready for direct PDF stream insertion or standalone WAV export.

### 3. Low-Level PyMuPDF Xref Sound Annotation Injection
- Direct cross-reference (`xref`) table construction for ISO 32000-1 compliant sound annotations:
  - Sound Stream Xref: `/Type /Sound /R 8000 /C 1 /B 16 /E /Signed` populated via `doc.update_stream()`.
  - Annotation Xref: `/Type /Annot /Subtype /Sound /Rect [...] /Sound <xref> 0 R /C [1, 0, 0] /Contents (Ultrasound Audio Recording)`.
- **Indirect `/Annots` Resolution**: Safely resolves whether `page.xref` contains a direct `/Annots [...]` array or points to an indirect `/Annots <ref> 0 R` object, appending new sound annotations without corrupting existing drawing or link annotations.

### 4. Template Anchor & Superimposition Policy (`SoundClipAnchorPolicy`)
- Scans target PDF pages for `"Sound clip"` key text within inspection table cells (Row 31 of `swg-panel.docx` and `tx-hv-sides.docx`).
- Detects the exact position of the visible speaker icon image embedded in Column 2 (`180 <= x <= 250` pt, aligned vertically within $\pm 15$ pt of the label) and centers an 18x18 pt hit target directly superimposed over the visible image (falling back to Column 2 center $c_x = 210.30$ pt if no image is present).
- Configures full transparency (`/CA 0.0`, `/Border [0 0 0]`, and an empty Form XObject appearance `/AP`) so PDF viewers seamlessly activate audio upon clicking the visible Word document icon without rendering duplicate or misaligned visual boxes.

### 5. Idempotent Sound Embedding (`IdempotentSoundEmbeddingPolicy`)
- Before creating a new annotation, inspects existing page annotations. If an existing sound annotation exists in that row (intersecting or matching Column 2 within $\pm 20$ pt):
  - Updates the sound stream in-place via low-level xref replacement.
  - Updates `/Rect`, `/CA 0.0`, `/Border [0 0 0]`, and `/AP` in-place, seamlessly migrating any legacy offset hit boxes.
  - Prevents duplicate stacked speaker icons and unreferenced xref table bloat during repeated post-processing runs.

### 6. Physical Compartment & Equipment Attribution Engines
- **`VcbAudioAttributionPolicy`**: Strict 1-to-1 physical chamber matching (`$CIRCUIT_BREAKER`, `$CABLE_BOX`, `$UPPER_BUSBARS`, `$VT_CHAMBER`) with zero cross-chamber leakage. Multi-measurement tie-breaking prioritizes `$UPPER_BUSBARS` over `$LOWER_BUSBARS` and highest dB readings. Unmeasured and secondary chambers remain blank.
- **`TransformerAudioAttributionPolicy`**: Shared TX high-voltage acoustic attribution applying a single ultrasound recording across all active HV side scanning pages (`HV CABLE`, `HV BUSHING`, `HV CABLE SPLIT`) with regex tolerance for `Tx No. TX1`.
- **`RmuAudioAttributionPolicy`**: Single-measurement fallback for compact RMU panels attributing untagged US recordings to the active scanning page (`CABLE COMPARTMENT`), with board-level acoustic fallback (`RMU_US`) when feeder subfolders are absent.
- **`TwoTierPanelMatchingPolicy`**: Resolves panel numbers via Tier 1 explicit digits in `Panel No.` cell, falling back to Tier 2 Row 4 `Panel Name` directory matching or `SubstationTestsheetPackage` equipment panel list, decoupling matching from package dependency.

### 7. Standalone Audio Generation (`UsAudioWorkflow` & `UsAudioOutputDirectory`)
- Provides on-demand WAV export saving canonical 16-bit `{meas.label}.wav` files into `<SUBSTATION>/RAW DATA/US+TEV/sounds/`.
- Reuses exact PRPD graph naming grammar (`SurveyMeasurementNaming`) for 100% naming parity.

### 8. Atomic PDF Replacement & Handle Closure (`AtomicPdfSavePolicy`)
- Document operations execute within context managers (`with fitz.open(...) as doc:`), ensuring file locks are released immediately on Windows.
- Pre-flight cleanup unlinks any stale `.tmp_sound_{pdf.name}` files.
- Deliverable PDF is written to a temporary sibling file and swapped via `os.replace` within guarded `try...finally` blocks.

### 9. Non-Blocking Survey Resilience (`UsTevAudioResiliencePolicy`)
- If US+TEV raw survey directories or specific compartment recordings are missing on disk, logs an informative diagnostic and completes report processing cleanly without throwing exceptions or interrupting batch execution.

### 10. Post-Merge Integration & CLI Registration
- Seamless post-merge hooks integrated at unified deliverable exit points:
  - `FullReportPostProcessingWorkflow._compile_deliverable()`
  - `PostProcessingPipelineWorkflow.execute()` (Step 6)
- Registered at **Position #10 (index 9)** in `UTILITY_ACTIONS` (`src/utility_actions.py`) labeled `"Generate US 16-bit audio & embed sounds into PDFs"`, with multi-date selection and deliverable readiness tags (`[PDF READY]` vs `[NO PDF]`).

## Consequences

### Positive
- **Universal Playback Compatibility**: Converted 16-bit mono PCM streams play natively and reliably inside Adobe Acrobat Reader, Foxit, PDF-XChange, Apple Preview, and web browsers.
- **Zero Intermediate Disk Overhead**: In-memory conversion eliminates temporary disk artifacts and filesystem race conditions.
- **Idempotency & Re-run Safety**: Re-running post-processing or utility actions updates sound streams cleanly without orphaned xrefs or stacked icons.
- **Post-Merge Architecture**: Complete separation of concerns: Word COM automation remains focused on layout rendering, while PyMuPDF handles low-level PDF audio enhancement.
- **Graceful Degradation**: Substations without US+TEV survey data compile into valid deliverable PDFs without error.

### Negative and Known Limitations
- Embedded audio is interactive strictly within PDF deliverables; Microsoft Word `.docx` documents do not support embedded interactive audio.
- Low-level PyMuPDF xref stream construction requires ongoing verification against major PyMuPDF upstream releases.
