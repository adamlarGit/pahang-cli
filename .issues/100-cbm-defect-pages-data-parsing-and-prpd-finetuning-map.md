# Map 100: CBM Defect Detail Pages Data Parsing, Severity Cell Styling & PRPD Graph Integration Map

Labels: wayfinder:map

## Destination

Enhance the CBM Defect Pages generator (`src/quick_report/cbm_defect_pages.py`, `src/quick_report/cbm_render.py`, `src/testsheet/extractor.py`) and DOCX template rendering across all equipment families (`swg-panel.docx`, `tx-hv-sides.docx`, etc.) to:
1. Dynamically highlight severity placeholder cells in **red** (`#EE0000`) when a defect is detected for that technology (`ir.severity`, `us.severity`, `tev.severity`), **green** (`#00B050`) when non-defective, and clear the placeholder text.
2. Parse ultrasound and TEV measurement metadata (`us.reading`, `us.char`, `tev.bg`, `tev.reading`, `tev.ppc`) directly from the substation testsheet workbook (`PCE Testsheet`) into the CBM render context.
3. Discover, decode, and embed respective Ultrasound and TEV **PRPD graph images** (`us.prpd`, `tev.prpd`) from the extracted raw material into the defect detail pages via native Python 4-tier density plotting.

## Notes

- **Target Domain**: `src/quick_report/`, `src/testsheet/`, `src/workflows/`
- **Reference Documentation**:
  - `docs/prpd_graph_generation_guide.md` (PRPD extraction and decoding technical guide)
  - `docs/etl_pipeline_refactoring_methodology.md`
- **Color Standards**:
  - Defective Technology Severity Cell: `#EE0000` (Red background fill, text cleared)
  - Non-Defective Technology Severity Cell: `#00B050` (Green background fill, text cleared)
  - Overview Page Severity: Plain text `-` (no background fill)
- **PRPD Specification**:
  - Direct Python binary FlatBuffers (`eventData.js`) and JSON (`ultrasonic_phase_plot.js`) decoding.
  - 4-Tier density scatter bins (`#00FF00`, `#0000FF`, `#FF0000`, `#640000`).
  - No reference sine wave.
- **Skills**: `/wayfinder`, `/codebase-design`, `/domain-modeling`, `/tdd`

## Decisions so far

- **Decision 1 (2026-09-02)**: **Option B (Native Python PRPD Plotting Engine) Locked for Production**. PRPD graphs will be rendered directly via Python binary FlatBuffers/JSON decoding (`scripts/generate_prpd_option_b.py` -> `src/quick_report/prpd.py`) with 4-tier repetition density scatter bins (`#00FF00`, `#0000FF`, `#FF0000`, `#640000`) and no reference sine wave. Option C (HTML Bootstrap UI Composite) was successfully prototyped and documented in `docs/prpd_option_c_specification.md` and `docs/prpd_graph_generation_guide.md` for future reference.
- [Ticket 101: Dynamic Table Cell Severity Shading & Formatting Specification](file:///.issues/101-dynamic-table-cell-severity-shading-and-formatting.md) — OpenXML `w:shd` cell fill applied during `_render_docx_template` post-processing (`#EE0000` on defect, `#00B050` on normal) with placeholder text cleanly cleared, leaving overview pages as plain `-` without fill.
- [Ticket 102: Testsheet Ultrasound & TEV Measurement Ingestion Schema](file:///.issues/102-testsheet-ultrasound-and-tev-measurement-ingestion-schema.md) — Ingested `tev_background` from PCE Testsheet `P6`, switchgear panel measurements from Cols Q/S/T/U/V, and transformer measurements from Cols K/L/V/X, propagating into typed models and render contexts.
- [Ticket 103: UltraTEV Survey Directory Asset Structure & Feeder Matching Policy](file:///.issues/103-ultratev-survey-directory-feeder-matching-policy.md) — Established 3-tier switchgear matching anchored on testsheet sequential `panel_no` (Column A) across multi-page sheets, multi-TX folder layout matching (`TX1/Transformer/`, `TX/Transformer/`), latest timestamp run selection, and dual PRPD graph embedding with clean empty-cell fallback.
- [Ticket 104: Automated PRPD Graph Generation and Rendering Pipeline](file:///.issues/104-automated-prpd-graph-generation-and-rendering-pipeline.md) — Implemented native Python decoding (`decode_tev_event_data`, `decode_ultrasonic_phase_plot`) and PRPD graph rendering in `src/quick_report/prpd.py` with `InlineImage` template binding for `{{ us.prpd }}` and `{{ tev.prpd }}`.
- [Ticket 105: Part 4 CBM Defect Detail Pages Context Builder & Composer Integration](file:///.issues/105-part4-cbm-defect-detail-pages-context-builder-and-composer-integration.md) — Integrated PRPD graph generation into `_build_swg_render_context`, `_build_tx_render_context`, and `generate_cbm_defect_pages` with `InlineImage` conversion and OpenXML severity table shading.
- [Ticket 106: End-to-End Verification with Real Inspection Datasets](file:///.issues/106-end-to-end-verification-with-real-inspection-datasets.md) — Verified end-to-end extraction and rendering against real inspection datasets (`020. TRAS`), confirming accurate cell shading, measurement population, and PRPD graph embedding.

## Open Tickets (Frontier)

*All Map 100 frontier tickets completed.*

## Not yet specified

- Audio waveform embedding (`.wav` sound clip icon / link) in Quick Report DOCX.
- UltraTEV survey auto-discovery for non-standard multi-switchgear configurations.

## Out of scope

- Direct modification of legacy .doc / .pdf conversion external binaries.
- Visual defect summary redesign (handled separately in Part 3/6).
