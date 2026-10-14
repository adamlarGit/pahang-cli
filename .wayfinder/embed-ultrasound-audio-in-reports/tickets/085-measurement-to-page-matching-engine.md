<!-- status: open -->
Part of Wayfinder Map: [map.md](../map.md)
GitHub Issue: [#85](https://github.com/adamlarGit/pahang-cli/issues/85)
Specification: [spec.md](../spec.md)

# 085: feat(sound): measurement discovery to PDF page and compartment matching engine

**What to build:** Deterministic matching engine that identifies which UltraTEV ultrasound measurement corresponds to each target scanning page in a deliverable PDF. Parses page text for `"Sound clip"` visual markers, extracts physical equipment identifiers (VCB panel numbers, compartment areas, transformer indices), and links each page to its corresponding `8k.wav` survey file.

**Blocked by:** #084 (in-memory audio converter & PyMuPDF sound annotator).

**Status:** ready-for-agent

- [ ] Extend `src/postprocessing/sound_embedder.py` with page inspection and measurement matching helpers:
  - `find_sound_clip_anchor(page: fitz.Page) -> fitz.Rect | None`: Searches page for text `"Sound clip"`. If found, calculates target speaker annotation rectangle centered inside **Column 2** aligned beneath ultrasound measurement readings: `fitz.Rect(236.0, inst.y0 - 2, 254.0, inst.y1 + 2)`. If absent, returns `None`.
  - `extract_page_equipment_context(page: fitz.Page, package: SubstationTestsheetPackage | None = None) -> dict[str, Any]`:
    - Extracts text and regex matches:
      - Switchgear panel index / feeder tag: `r"Panel No\.\s*[:\n\r]*\s*([A-Za-z0-9_\-]+)"`
      - Feeder name: `r"Panel Name\s*[:\n\r]*\s*([^\n\r]+)"` (from Row 4)
      - Compartment area: `r"Area\s*[:\n\r]*\s*([A-Za-z0-9_\s]+?)(?:\s+(?:Panel|IR|Time|Model|Tx)|$)"`
      - Transformer unit index: `r"Tx No\.\s*[:\n\r]*(?:TX|Tx|TRANSFORMER)?\s*(\d+)"` and `r"(?:Tx No\.|TX)\s*[:\n\r]*\s*(?:TX)?\s*(\d+)"` (capturing both bare `1` and prefixed `TX1` / `TX2`)
    - Enforces `TwoTierPanelMatchingPolicy`:
      - *Tier 1*: Parses explicit digits from `Panel No.` if present (e.g. `1`, `Panel 1`, `1 (CRB70001)` $\to$ `1`).
      - *Tier 2*: If unnumbered utility code (e.g. `CRB00764`), uses extracted `Panel Name` to resolve via `find_swg_feeder_survey_dir` directly, falling back to `package.equipment.switchgears[0].panels` if package is provided.
- [ ] Modularize and reuse the 3-tier feeder matching engine from `src/quick_report/prpd.py` (`find_swg_feeder_survey_dir` and `find_tx_survey_dir`) across both PRPD graph generation and sound embedding.
- [ ] Implement canonical mapping resolver `resolve_measurement_audio_for_page(survey_root: Path, measurements: list[DiscoveredMeasurement], page_context: dict[str, Any]) -> Path | None`:
  - Filters measurements to `tech == "US"`.
  - Enforces `VcbAudioAttributionPolicy` for switchgear cubicles:
    - Strict 1-to-1 chamber mapping:
      - `BREAKER COMPARTMENT` $\longleftrightarrow$ `$CIRCUIT_BREAKER`
      - `CABLE COMPARTMENT` $\longleftrightarrow$ `$CABLE_BOX` (or `$CABLES`)
      - `BUSBAR COMPARTMENT` $\longleftrightarrow$ `$UPPER_BUSBARS` / `$LOWER_BUSBARS` / `$BUSBAR`
      - `PT COMPARTMENT` $\longleftrightarrow$ `$VT_CHAMBER` / `$VOLTAGE_TRANSFORMER`
    - Deterministic multi-measurement tie-breaking:
      - If both `$UPPER_BUSBARS` and `$LOWER_BUSBARS` exist for `BUSBAR COMPARTMENT`, prioritize `$UPPER_BUSBARS`.
      - If duplicate measurements exist for the same component, select the recording with the highest ultrasound dB reading.
    - Zero cross-chamber leaking: single recordings apply strictly to their own chamber and are never cloned.
    - Unmeasured chambers and non-acoustic `SECONDARY COMPARTMENT` return `None`.
  - Enforces `TransformerAudioAttributionPolicy` for transformers:
    - Shares single TX acoustic recording across all active HV side scanning pages (`HV CABLE`, `HV BUSHING`, `HV CABLE SPLIT` via `tx-hv-sides.docx`) for that transformer unit.
  - Enforces `RmuAudioAttributionPolicy` for compact RMU panels:
    - Single untagged US recordings (where `$COMPONENT` is `None` or `$NONE`) automatically match the panel's active scanning page (`CABLE COMPARTMENT`).
    - Board-level acoustic fallback: If an RMU survey lacks feeder subfolders (`FEEDER_1`, `FEEDER_2`) but contains an overall board-level measurement (`RMU_US` or `SWG_US`), attributes that recording across all active RMU cable scanning pages.
  - Resolves target `8k.wav` file inside matching measurement directory (`meas.meas_dir / "8k.wav"`).
  - Mandatory presence invariant: `8k.wav` must exist and be non-empty; if missing, raises `FileNotFoundError` (fails loudly; zero fallback to `10k.wav` or `192k.wav`).
  - Returns file path if valid and non-zero byte, else `None`.
- [ ] Implement unit test suite in `tests/test_sound_matching.py`:
  - Test anchor detection centers speaker rectangle inside Column 2 ($x \in [236, 254]\text{ pt}$).
  - Test anchor detection returns `None` on pages without `"Sound clip"` (overviews, condition pages, sticker pages, secondary compartments).
  - Test `TwoTierPanelMatchingPolicy` across bare digits (`1`), prefixed codes (`1 (CRB70001)`), and unnumbered SCADA codes (`CRB00764`) with Row 4 `Panel Name`.
  - Test `VcbAudioAttributionPolicy` asserts strict 1-to-1 chamber matching, zero cross-chamber leakage, and deterministic tie-breaking ($UPPER\_BUSBARS > $LOWER\_BUSBARS; highest dB).
  - Test `TransformerAudioAttributionPolicy` matches prefixed `"TX1"` and `"TX2"` as well as bare numbers, sharing single TX recording across `HV CABLE`, `HV BUSHING`, and `HV CABLE SPLIT`.
  - Test `RmuAudioAttributionPolicy` asserts single untagged US measurement matches RMU cable compartment and tests board-level fallback when feeder subfolders are absent.
  - Test missing `8k.wav` raises `FileNotFoundError` (fail-loud invariant).
