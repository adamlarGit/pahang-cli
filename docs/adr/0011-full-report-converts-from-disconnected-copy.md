# 11. Full Report Conversion Opens a Copy With FLIR Controls Disconnected

Date: 2026-11-10
Status: Proposed (experiment branch `experiment/disconnected-word-open`; accepted only after the proof in #212 passes)
Adds to: [ADR 0009](./0009-native-export-with-source-image-restoration.md). Does not replace it.

## Decision

`convert_docx_to_pdf` for Full Report parts opens a throwaway copy of the DOCX with its FLIR ActiveX controls (`w:control`) removed, then exports it with Word. Source Image Restoration (ADR 0009) still runs, and takes its snapshot from the original DOCX.

- The delivered DOCX is never modified.
- If making or opening the copy fails, conversion opens the original normally and the operator gets a warning.
- A report with no FLIR controls takes the normal path unchanged.
- No setting. Quick Report and testsheets are unchanged.
- `configure_uniform_printer` still decides layout.

## Why

Live controls make Word's open slow. The proof (#210) saw 56-65% less total conversion time on reports with controls (#212 proof, 2026-11-10).

## Accepted downside

The PDF shows the preview picture stored in the DOCX, not what the live control draws. A thermogram's colour-bar scale can therefore differ: tick labels can be fewer (APMM Part 32 page 13 shows 40 and 30 where the normal conversion shows 45, 40, 35 and 30), and the colour-bar image can have a different resolution. The owner accepts this because the spot readings in the report's table are unchanged. Edits made to a thermogram in FLIR Tools show in the PDF only as far as the saved preview shows them.
