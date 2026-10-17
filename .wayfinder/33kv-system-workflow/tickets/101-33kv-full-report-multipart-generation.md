<!-- status: closed -->
Part of #90
Specification: [spec.md](../spec.md)

# 101: feat(33kv-full-report): 33kV Full Report multi-part chunk generation

**What to build:** Extend `FullReportWorkflow` and `MultiPartPartitionPolicy` to generate modular multi-part Full Report Word documents for 33kV substations (VCB and GIS cubicles across dual-voltage 33kV and 11kV lineups, plus Power Transformers), adhering to ADR 0005 and using the field-verified reports in `C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\FULL REPORT` as content and visual benchmarks.

**Blocked by:** #93, #96

**Status:** closed

- [x] Extend `MultiPartPartitionPolicy` in `src/full_report/plan_builder.py` to recognize 33kV switchgear packages containing multiple switchgear lineups (`switchgears` plural):
  - Automatically classify 33kV switchgear lineups as `SwitchgearArchetype.VCB_CUBICLE` or `GIS_CUBICLE`.
  - **Chunk 1 (`Part 01 - Summary`)**: Front Page, Executive Summary Census (`executive_summary_census.docx`), Visual Defect Summary, and Switchgear Overview pages for all active lineups.
  - **Chunks 2..(N+1) (`Part {XX:02d} - Panel {no} ({voltage} - {name})`)**: One Word document per bay cubicle across both 33kV and 11kV lineups, containing all 6 physical compartment scans (`BREAKER`, `CABLE`, `BUSBAR`, `PT`, `CABLE ENTRY`, `LINK BOX`), Column Q Secondary Compartment, and inline CBM defect pages (Decisions Q74).
  - **Chunk N+2 (`Part {N+2:02d} - TX and Condition`)**: Power Transformers (HV/LV sides via `tx-hv-sides.docx` and `tx-lv-sides.docx`, auxiliary thermals `Marshalling Kiosk`, `Conservator Tank`, `Cooling Fin` via `tx-overview.docx`), Local TX, battery bank, PPU/SSU condition photo grid, Visual Defect detail pages, and Sticker page (Decision Q75).
  - Dynamically omit empty chunks when assets are absent (e.g. omitting Part N+2 if no transformers, condition photos, or VI pages exist) (Decision Q76).
- [x] Implement power transformer report page rendering for $\ge 5$ MVA units using `PowerTransformerSpec` (Ticket #93), rendering auxiliary thermal scans and ultrasound measurements.
- [x] Maintain standard title transformation for Front Page: replace `QUICK SCANNING REPORT` with `FULL SCANNING REPORT` with 100% parity with 11kV (Decision Q77).
- [x] Format 33kV chunk and report output filenames with 2-digit zero-padding `f"{pe_number:02d}."` (e.g. `06. SSU FLEXSYS CHEMICAL 33kV (VI) - Part 01 - Summary.docx`), preserving 3-digit for 11kV (Decision Q78).
- [x] Ensure `FullReportComposer` compiles clean Word chunks with zero ActiveX crashes, saving chunks with zero-padded deterministic naming (`<STEM> - Part {XX:02d} - {label}.docx`).
- [x] Ensure intermediate Word documents are permanently retained in the date directory for operator review per ADR 0005 (Decision Q79).
- [x] Add unit and integration tests in `tests/test_full_report_33kv.py` testing partition planning and chunk rendering on synthetic 33kV substations.

