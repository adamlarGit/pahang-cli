# Quick Report Photo Embedding and Layout Rules

Labels: wayfinder:research
Status: Closed
Parent: [Map: Quick Report Generation Workflow (Pahang CLI)](file:///.issues/019-quick-report-generation-map.md)

## Question

How should thermal (`IR`) and digital camera (`DG`) photo files be located from `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_FOLDER>/RAW DATA/`, matched with `PhotoRange` bounds from `TestsheetExtractor`, resized, and embedded into `.docx` inline image placeholders without breaking Word layout or table cell dimensions?

## Resolution

1. **Photo Location & Numerical Range Matching**:
   - Locate photos in `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_FOLDER>/RAW DATA/{IR,DG}/`.
   - Match filename sequence numbers using `_extract_photo_number` (prefixes `"FLIR"` for IR, `"IMG_"` for DG) against `PhotoRange(start_num, end_num)` extracted by `TestsheetExtractor`.
2. **`docxtpl.InlineImage` Mechanics & Sizing**:
   - Embed images using `docxtpl.InlineImage(doc, photo_path, width=Mm(w))`.
   - Pass width explicitly (omitting height) to automatically preserve the original image aspect ratio and prevent table column stretching.
   - Sizing standards: Front page IR overview `width=Mm(120)`, 2-column defect table `width=Mm(68)`, 6-defect summary grid `width=Mm(55)`.
3. **Missing Photo Fallbacks & Warnings**:
   - If a photo in `PhotoRange` is missing, inject a fallback placeholder image (or Jinja2 template conditional fallback) and record a non-blocking warning in `QuickReportResult.warnings`.
4. **Architecture Seam**:
   - `src/quick_report/photo_resolver.py`: Responsible for range-matching photo paths in `RAW MATERIAL`.
   - `src/quick_report/template_engine.py`: Responsible for creating sized `InlineImage` instances for docxtpl context rendering.
