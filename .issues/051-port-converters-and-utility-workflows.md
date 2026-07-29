# Ticket 051: Port Converters & Core Utility Workflows

## Parent Map

[Map 048: Standalone Utility Actions Deep Dive & Implementation](file:///.issues/048-standalone-utility-actions-map.md)

## Type

`task` (AFK)

## Status

`CLOSED`

## Question

How should document converters and utility workflow modules be ported from the reference CLI (`C:\Users\ADAM\Documents\PO 42234207 - JOHOR - JBU - 400 PE IR US TEV\src\`) into `src/workflows/`?

## Resolution

Ported `converters.py` (`ComDocumentConverter`, `DocumentConverter`, sheet filters) and all 8 core utility workflow modules into `src/workflows/`:
- `docx_to_pdf.py`
- `testsheet_to_pdf.py`
- `combine_pdfs.py`
- `diagonal_borders.py`
- `pdf_extract.py`
- `rename_files.py`
- `rename_flir.py`
- `replace_signatures.py`
- `progress.py`

Cleaned up relative imports and verified syntax/compatibility across all modules.
