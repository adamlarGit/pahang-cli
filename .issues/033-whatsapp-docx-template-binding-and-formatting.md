# WhatsApp Docx Template Binding and Summary Formatting

Labels: wayfinder:research
Status: Closed
Parent: [Map: WhatsApp Report Generation Workflow (Pahang CLI)](file:///.issues/030-whatsapp-report-generation-map.md)

## Question

What Jinja2 placeholder tags exist inside `templates/WHATSAPP/TEMPLATE WHATSAPP PYTHON.docx`, how are populated substation metadata rows and summary tables constructed, and what is the output file naming convention in `PYTHON/WHATSAPP/`?

## Resolution

1. **Jinja2 Context Binding Schema**:
   - Template Path: `templates/WHATSAPP/TEMPLATE WHATSAPP PYTHON.docx`.
   - Render Context:
     ```python
     context = {
         "date": report_date,       # e.g., "25/07/2026"
         "station": station_name,   # e.g., "MARAN"
         "items": [
             {
                 "name": "SSU CHEROH",
                 "defect": "VI",      # Extracted from PDF suffix; "-" if missing
                 "msms": "40012345",  # Extracted from TOTAL PE.xlsx WO column
             },
             ...
         ]
     }
     ```
   - Rendered using `docxtpl.DocxTemplate(template_path).render(context)`.

2. **Output Formatting & Directory Rules**:
   - Deliverable: Strictly the `.docx` summary document in `PYTHON/WHATSAPP/` (no plain-text clipboard output).
   - Filename Stem Convention: `{next_num:02d}. {station_name} {clean_date}.docx` (e.g., `01. MARAN 25-07-2026.docx`).
   - `next_num`: Auto-incrementing 2-digit index calculated per output folder.
   - `clean_date`: Inspection date formatted with hyphens (e.g. `25-07-2026`).
