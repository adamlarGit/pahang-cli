<!-- status: open -->
Part of Wayfinder Map: [map.md](../map.md)
GitHub Issue: [#89](https://github.com/adamlarGit/pahang-cli/issues/89)
Specification: [spec.md](../spec.md)

# 089: docs(adr): record ADR 0007, update CONTEXT.md, and run full E2E regression suite

**What to build:** Record formal architectural decision record ADR 0007 documenting the 24-to-16 bit in-memory audio conversion, PyMuPDF xref sound injection, and post-merge delivery integration. Synchronize `CONTEXT.md` with new domain concepts (`UsAudioWorkflow`, `UsTevAudioResiliencePolicy`, `UsAudioOutputDirectory`, `SoundClipAnchorPolicy`), perform end-to-end regression testing, and verify 100% green test suite across all project suites.

**Blocked by:** #087, #088.

**Status:** ready-for-agent

- [ ] Draft and record `docs/adr/0007-ultrasound-audio-embedding-and-conversion.md`:
  - Title: ADR 0007: Ultrasound Audio Embedding and In-Memory 16-Bit Conversion.
  - Status: Accepted.
  - Context: UltraTEV 24-bit PCM incompatibility with PDF ISO 32000-1 / Adobe Acrobat, disk storage limitations preventing on-site raw data download, and PyMuPDF xref annotation architecture.
  - Decision: Standardize strictly on `8k.wav` (mandatory presence, fail-loud invariant), downscale to 16-bit PCM in memory via `wave` and `bytearray`, inject sound annotations via low-level xrefs post-merge with `IdempotentSoundEmbeddingPolicy` and indirect `/Annots` handling, export standalone WAVs to `<SUBSTATION>/RAW DATA/US+TEV/sounds/`, enforce `AtomicPdfSavePolicy` with context-managed handle closure, and enforce `UsTevAudioResiliencePolicy`.
  - Consequences: Complete playback compatibility across PDF readers, zero intermediate disk I/O, robust non-blocking degradation on missing survey data, clean separation between report compilation and sound embedding.
- [ ] Update `CONTEXT.md` with new ubiquitous domain concepts:
  - `UsAudioWorkflow`: Standalone utility workflow generating 16-bit WAV audio files and retroactively embedding sounds into report PDFs.
  - `UsAudioOutputDirectory`: Canonical destination strictly located at `<SUBSTATION>/RAW DATA/US+TEV/sounds/`.
  - `UsTevAudioResiliencePolicy`: Non-blocking graceful skip policy when US+TEV survey folder or compartment recording is absent.
  - `SoundClipAnchorPolicy`: Detection and positioning rule placing speaker sound annotations centered in Column 2 adjacent to `"Sound clip"` table cells in scanning templates.
  - `IdempotentSoundEmbeddingPolicy`: Idempotent PDF sound injection policy checking for existing sound annotations intersecting target anchor coordinates and updating sound streams in-place to prevent duplicate stacked icons and unreferenced xref bloat.
  - `VcbAudioAttributionPolicy`: Strict 1-to-1 physical chamber matching (`$CIRCUIT_BREAKER`, `$CABLE_BOX`, `$UPPER_BUSBARS`, `$VT_CHAMBER`) with zero cross-chamber leakage; multi-measurement tie-breaking prioritizing `$UPPER_BUSBARS` and highest dB readings; unmeasured and secondary chambers stay blank.
  - `TransformerAudioAttributionPolicy`: Shared TX high-voltage acoustic attribution applying a single ultrasound recording across all active HV side scanning pages (`HV CABLE`, `HV BUSHING`, `HV CABLE SPLIT`) with prefix tolerance for `Tx No. TX1`.
  - `RmuAudioAttributionPolicy`: Single-measurement fallback for compact RMU panels attributing untagged US recordings to the panel's active scanning page (`CABLE COMPARTMENT`), with board-level acoustic fallback when feeder subfolders are absent.
  - `TwoTierPanelMatchingPolicy`: Two-tier resolution extracting explicit panel digits from `Panel No.` if present (Tier 1), falling back to Row 4 `Panel Name` directory matching or `SubstationTestsheetPackage` equipment panel list (Tier 2).
  - `AtomicPdfSavePolicy`: In-place deliverable PDF replacement pattern enforcing context-managed document handle closure, pre-flight cleanup of stale temp files, and atomic replacement via `os.replace` within guarded `try...finally` blocks.
- [ ] Run full automated test suite (`pytest`) across all unit, adapter, workflow, and regression suites:
  - Verify all new sound tests pass (`tests/test_sound_embedder.py`, `tests/test_sound_matching.py`, `tests/test_us_audio_workflow.py`, `tests/test_us_audio_cli.py`, `tests/test_pipeline_sound_integration.py`).
  - Verify zero regressions in existing testsheet, quick report, full report, and PRPD test suites.
- [ ] Perform manual CLI menu dry-run check:
  - Run `pahang-cli` or `start_cli.bat` dry run check verifying menu entry #10 renders cleanly.
- [ ] Execute Merge Gate & Worktree Synchronization Protocol:
  - Phase B: Merge `feature/embed-ultrasound-audio` into `main` in `pahang-cli` (`git merge --no-ff feature/embed-ultrasound-audio`).
  - Phase C: Sequentially sync downstream worktrees with `main`:
    - Merge `main` into `pahang-cli-33kv` (`feature/33kv-system`) and verify with `pytest`.
    - Merge `main` into `pahang-cli-web` (`feature/pwa-web-migration`).
  - Phase D: Teardown temporary worktree `pahang-cli-audio` and delete feature branch.
