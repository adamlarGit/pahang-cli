# 5. VCB and GIS Multi-Part Full Report Generation and PDF Stitching Architecture

Date: 2026-09-24
Status: Accepted

## Context

In distribution substation condition-based maintenance, Vacuum Circuit Breaker (`VCB_CUBICLE`) and Gas-Insulated Switchgear (`GIS_CUBICLE`) installations present significantly higher physical complexity and page volume than compact Ring Main Units (RMU). A typical 5-panel to 11-panel VCB lineup comprises multiple individual bays, each with distinct breaker, cable, busbar, secondary, and potential transformer (PT) chambers, accompanied by thermal/visual photographic pairs and inline CBM defect pages (such as TEV PRPD scatter plots or ultrasound readings).

When compiled into a single monolithic Microsoft Word (`.docx`) file, these large deliverables (40 to 80+ pages) trigger acute stability problems:
1. **ActiveX / FLIR Tools+ Memory Exhaustion**: Field inspectors opening large documents experience Microsoft Word application hangs, out-of-memory errors, and COM automation crashes when loading tens of embedded FLIR ActiveX thermal images.
2. **Review Ergonomics**: Diagnostic inspectors need to isolate, edit, and re-check individual bay assessments without having to navigate or risk corrupting an unwieldy 60-page document.
3. **Contractual Deliverable Integrity**: Despite internal document modularity, the client (TNB) contractually mandates a **single consolidated PDF document** per substation (`<STEM>.pdf`), with the signed testsheet PDF attached at the end.

## Decision

The Full Report pipeline adopts a two-stage modular architecture for high-page-volume VCB and GIS switchgear, while preserving single-document generation for standard RMUs:

### 1. `MultiPartPartitionPolicy` (Stage 1 Word Partitioning)
- **Automatic Archetype Trigger**: Multi-part generation activates automatically for switchgear archetypes `VCB_CUBICLE` and `GIS_CUBICLE` (determined via `MultiPartPartitionPolicy.evaluate_package(eq_pkg)` or `plan.package.switchgears[0].archetype`). Standard RMUs (`RMU_STANDARD`, `RMU_DUAL_CABLE_ENTRY`, etc.) remain single Word documents.
- **Modular Bill of Materials Chunks**:
  - **Chunk 1 (`Part 01 - Summary`)**: Front Page, Executive Summary Census, Visual Defect Summary, and Switchgear Overview pages.
  - **Chunks 2..(N+1) (`Part {XX:02d} - Panel {no} ({name})`)**: One Word document per individual switchgear bay, containing all bay chamber scan pages and any inline CBM defect pages attached directly behind their parent panel.
  - **Chunk N+2 (`Part {N+2:02d} - TX and Condition`)**: Balance of plant assets including Transformers, LVDB / Feeder Pillar, Battery Bank, Substation Condition photo grid, Visual Defect detail pages, and Sticker page.
- **Deterministic Zero-Padded Naming**: Parts are named `<STEM> - Part {XX:02d} - {label}.docx` to ensure alphabetical order matches logical document sequence.
- **Idempotent Pre-Purge**: Re-running generation purges only matching exact-stem parts (`f"{exact_stem} - Part *.docx"`) before re-writing.

### 2. `MultiPartDocumentDeliveryPolicy` (Field Review Invariant)
Intermediate Word parts are retained permanently in the substation date directory (`FULL REPORT/<STATION>/<MONTH>/<DATE>/`). Field inspectors can safely open, edit, and re-save individual bay files without memory crashes.

### 3. `MultiPartPdfStitchingPolicy` (Stage 2 PDF Consolidation)
- **Discovery & Grouping**: `_group_multipart_targets()` groups matching `<STEM> - Part *.docx` files by their common substation stem.
- **Batch PDF Conversion & Concatenation**: Each part is converted sequentially to a temporary PDF, concatenated in numerical order via `merge_pdfs_batch()` on `DocumentConverter`, and merged with the signed testsheet PDF from `processed_testsheet/pdf/<STEM>.pdf`.
- **Final Deliverable**: Emits the canonical client deliverable `<STEM>.pdf` in the date directory and cleans up intermediate temporary PDFs.

## Consequences

### Positive
- **Complete Elimination of FLIR ActiveX Crashes**: Word documents remain lightweight (typically 4–12 pages per chunk), eliminating COM automation timeouts and ActiveX memory exhaustion.
- **Seamless Inspector Experience**: Field engineers can review, annotate, or replace thermal scans on specific panels independently.
- **Preserved TNB Deliverable Compliance**: TNB receives exactly one unified `<STEM>.pdf` per substation with full table of contents flow and appended testsheet.
- **Zero RMU Regression**: Compact RMU substations remain single-document deliverables without unnecessary file proliferation.

### Negative and Operational Trade-offs
- Multiple files exist in the date folder for VCB/GIS stations (`7` files for a 5-panel VCB).
- Stage 2 PDF post-processing requires batch conversion of all parts before stitching into the final master PDF.
