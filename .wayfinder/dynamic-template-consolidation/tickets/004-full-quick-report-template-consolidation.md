---
id: "004"
title: "Full Report vs. Quick Report Template Consolidation"
status: deferred
---

# Ticket 004: Full Report vs. Quick Report Template Consolidation

<!-- status: deferred -->

## Status: DEFERRED

This ticket has been explicitly **deferred** by architectural decision due to binary FLIR ActiveX serialization constraints and the lack of a verified methodology for dynamically modifying thermal image object properties.

---

## Deferral Rationale & Technical Roadblock

### 1. The Single-Template Vision
The ultimate consolidation ambition was to unify `templates/FULL REPORT/NORMAL IR US TEV/` and `templates/QUICK REPORT/DEFECT IR US TEV/` into a single canonical set of dynamic templates shared across both report generators.

### 2. The FLIR ActiveX OLE Compound Binary Roadblock
Detailed reverse-engineering and investigation of the embedded FLIR Tools+ ActiveX control (`CIRViewer`, `shapeid="_x0000_i1027"` / `_x0000_i1029"`) revealed a fundamental architectural constraint:
- **Palette Divergence**:
  - Full Report templates use the modern `RAIN900` thermal color palette.
  - Quick Report templates use the legacy `RAIN` thermal color palette.
- **Binary Serialization (`activeX1.bin`)**:
  - The thermal image object properties—including palette selection, temperature scale, isotherm settings, object geometry, and VML shape IDs—are serialized inside a proprietary Microsoft OLE Structured Storage Compound binary stream located at `word/activeX/activeX1.bin`.
- **Violation of ADR 0002**:
  - Per **ADR 0002** (*Word COM Automation for Quick Report Compilation and FLIR ActiveX Isolation*), pure Python libraries cannot synthesize or safely rewrite binary OLE compound streams.
  - Any byte-level modification of `activeX1.bin` in Python breaks binary header offsets, internal storage structures, and checksums.
  - When opened in Microsoft Word, modified documents trigger corruption warnings ("Word found unreadable content...").
- **Real Verification Evidence from Test Suite**:
  - During test suite execution, an accidental modification to `templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx` changed the VML shape ID from `_x0000_i1029` to `_x0000_i1027`.
  - This immediately failed 3 tests in `tests/test_full_report_normal_templates.py`:
    - `test_template_placeholders_consistency`
    - `test_template_inline_image_binding`
    - `test_render_smoke_test_all_seven_templates`
  - This proves that Word COM automation and template verification strictly depend on precise binary control specifications that cannot be casually altered.
- **No Purely Dynamic Runtime Mutation**:
  - Because there is no verified methodology to dynamically alter thermal image object properties at runtime from Python without violating ADR 0002 and corrupting `.docx` files, consolidating Full Report and Quick Report templates into a single dynamic template file is deferred pending deeper architectural exploration.

---

## Scope & Open Questions for Future Sessions

Consolidation of Full Report and Quick Report templates into a single dynamic template family is postponed until dedicated architectural sessions resolve:

1. **Palette Standardization**:
   - Can stakeholders and field thermographers agree on a single standardized palette (e.g. standardizing all templates on `RAIN900` across both Quick Report and Full Report ahead of time)?
   - If palettes are standardized ahead of time in the static `.docx` files, dynamic runtime palette switching becomes completely unnecessary.
2. **Dynamic Thermal Image Object Properties**:
   - Are there safe, external COM-driven or pre-processing mechanisms to manipulate FLIR thermal image object properties before template rendering?
   - How can isotherm and temperature scale properties be configured dynamically without breaking OLE compound binary structures?
3. **Template Layout & Field Divergence**:
   - Address discrepancies in metadata fields, table widths, margins, and header banners between Full Report and Quick Report templates:
     - Full Report templates contain `{{ substation.name_erms }}`, `{{ ir.severity }}` with dynamic green/red shading, and census tables.
     - Quick Report templates contain defect details, CBM defect planner tags, and customer signboard layouts.
4. **Compilation Pipeline Compatibility**:
   - Ensure that the Word COM compilation sequence (`src/quick_report/composer.py`) and Full Report composer pipeline can ingest the unified templates without regressions or ActiveX crosstalk.

---

## Conclusion & Direction

- Keep `templates/FULL REPORT/NORMAL IR US TEV/` and `templates/QUICK REPORT/DEFECT IR US TEV/` completely separated for their respective workflows.
- Proceed with internal Quick Report dynamic blanking (Tickets 001 and 002) without cross-contaminating Full Report templates.
- Revisit single-template consolidation in a future dedicated architectural initiative once the open questions are resolved.
