# Ticket 105: Part 4 CBM Defect Detail Pages Context Builder & Composer Integration

Labels: wayfinder:task, afk, state:closed

Blocked by: [Ticket 101: Dynamic Table Cell Severity Shading & Formatting Specification](file:///.issues/101-dynamic-table-cell-severity-shading-and-formatting.md), [Ticket 102: Testsheet Ultrasound & TEV Measurement Ingestion Schema](file:///.issues/102-testsheet-ultrasound-and-tev-measurement-ingestion-schema.md), [Ticket 103: UltraTEV Survey Directory Asset Structure & Feeder Matching Policy](file:///.issues/103-ultratev-survey-directory-feeder-matching-policy.md), [Ticket 104: Automated PRPD Graph Generation and Rendering Pipeline](file:///.issues/104-automated-prpd-graph-generation-and-rendering-pipeline.md)

## Question

How should `src/quick_report/cbm_defect_pages.py` and `src/quick_report/cbm_render.py` be updated to assemble the enriched multi-technology context (`us.reading`, `us.char`, `tev.bg`, `tev.reading`, `tev.ppc`, `us.prpd`, `tev.prpd`), render `swg-panel.docx`, `tx-hv-sides.docx`, and other family detail pages, and execute post-render table cell severity shading?

## Resolution

- **Context Integration**:
  - `_build_swg_render_context` and `_build_tx_render_context` discover `survey_root` via `pe_info["raw_data_dir"]`, match target feeders / transformers, generate high-resolution PRPD graphs into `prpd_output_dir`, and bind `us.prpd` and `tev.prpd` image paths into both root and nested contexts.
  - `_build_fp_lvdb_render_context`, `_build_blackbox_render_context`, and `_build_battery_render_context` initialize `us.prpd = ""` and `tev.prpd = ""` gracefully.
- **Rendering & Image Processing**:
  - `_process_inline_images` in `_render_docx_template` recursively converts PRPD image file paths into `docxtpl.InlineImage` instances with width `80 mm`, leaving unsurveyed slots as `""`.
  - `QuickReportContext` preserves `InlineImage` instances and blanks out empty image paths without inserting placeholder hyphens (`"-"`).
  - Table cell severity shading (`#EE0000` / `#00B050`) executes post-render XML mutation seamlessly.
- **Verification**: Verified via `tests/test_cbm_defect_pages_integration.py`.
