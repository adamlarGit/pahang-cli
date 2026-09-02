# Ticket 101: Dynamic Table Cell Severity Shading & Formatting Specification

Labels: wayfinder:grilling, hitl, state:closed

## Question

How should the DOCX table cell XML manipulation engine detect `{{ ir.severity }}`, `{{ us.severity }}`, and `{{ tev.severity }}` placeholders across template tables, apply exact `#EE0000` (Red) shading on defect and `#00B050` (Green) shading on normal condition, and strip placeholder text cleanly without corrupting table layout?

## Resolution

- **Shading Mechanism**: Implemented `set_cell_shading(cell, hex_color)` in `src/quick_report/utils.py` manipulating OpenXML `w:tcPr/w:shd` (`w:val="clear"`, `w:color="auto"`, `w:fill=HEX`).
- **Placeholder Detection & Text Stripping**: In `_render_docx_template` (`src/quick_report/cbm_render.py`), post-processing inspects rendered cells for `__SEVERITY_IR__`, `__SEVERITY_US__`, `__SEVERITY_TEV__` (or raw `{{ ir.severity }}`, `{{ us.severity }}`, `{{ tev.severity }}`):
  - Defective technology: Shaded `#EE0000` (Red), text cleared.
  - Non-defective technology: Shaded `#00B050` (Green), text cleared.
  - Overview pages: Text rendered as plain `-` without background fill.
- **Verification**: Verified via `tests/test_cbm_severity_and_measurements.py` across `swg-panel.docx` and `swg-overview.docx`.
