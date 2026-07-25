# Quick Report Templates and Docxtpl Binding Schema

Labels: wayfinder:research
Status: Closed
Parent: [Map: Quick Report Generation Workflow (Pahang CLI)](file:///.issues/019-quick-report-generation-map.md)

## Question

What are all the Jinja2 context variable placeholders present in `templates/QUICK REPORT/*.docx` (Front Page, Substation Configuration templates, VI Summary, Visual Defect, CBM Defect Summary), and how should docxtpl / python-docx be configured to render and compose these template sections into a single output `.docx` report?

## Resolution

1. **Template Inventory**:
   - 24 `.docx` templates inside `templates/QUICK REPORT/` categorized into Front Page (`1. FRONT PAGE...`), Substation Configuration (`SUBSTATION CONFIGURATION/*.docx`), Visual Inspection Summary/Cards (`2. VI SUMMARY...`, `10. VISUAL DEFECT...`), and CBM Defect Summary & Detail (`CBM DEFECT SUMMARY.docx`, `DEFECT IR/*.docx`).
2. **Context Binding Schema**:
   - Metadata: `station_name`, `pe_name`, `date`, `fl`, `voltage`, `substation_type`, `building_type`, `gps_coordinate`.
   - Photos: `ir_photo_overview`, `dg_photo_overview`, `item.ir_photo`, `item.dg_photo` wrapped as `docxtpl.InlineImage`.
   - Inventory lists: `transformers`, `feeders`, `switchgears`, `batteries`.
   - Defect lists: `vi_defects` (Visual defects, max 6 per page), `cbm_defects` (CBM diagnostic defects, max 6 per page), `defects` (Visual defect cards).
3. **Template Composition Mechanics**:
   - `QuickReportTemplateEngine` (`src/quick_report/template_engine.py`) renders sub-template sections individually using `docxtpl.DocxTemplate.render(context)`.
   - Sub-sections are merged sequentially using `docxcompose.Composer` in standard order: Front Page → Substation Configuration → VI Summary → Visual Defect Cards → CBM Summary → Defect IR Detail Pages.
   - 6-item pagination chunking and page breaks (`add_page_break()`) prevent layout overflow.
