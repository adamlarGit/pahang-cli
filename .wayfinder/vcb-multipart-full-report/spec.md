# Specification: VCB and GIS Multi-Part Full Report Generation and PDF Stitching

## Problem Statement

Distribution substation Condition Based Assessment (CBA) Full Scanning Reports require documenting every asset across the substation regardless of condition. For substations equipped with Vacuum Circuit Breaker (VCB) or Gas-Insulated Switchgear (GIS) cubicles, each switchgear bay contains four to five inspection chambers (cable, breaker, busbar, secondary, and potential transformer). When a lineup contains five or more panels, the resulting Full Report Word document balloons to 40 to 60 or more pages.

Because thermal inspection images in the templates are embedded with FLIR Tools Plus ActiveX COM controls (`CIRViewer`), Microsoft Word suffers severe memory bloat and frequently crashes or freezes when opening or editing documents of this size. Field inspectors and report reviewers must be able to open, inspect, and adjust thermal spans and spot meters in Microsoft Word without experiencing application crashes.

Previously, inspectors worked around this by manually chopping reports into smaller parts before editing. However, there is no automated mechanism in the generator to partition large reports into stable Word files or to stitch them back together into the single consolidated PDF deliverable required by Tenaga Nasional Berhad (TNB).

## Solution

Implement an automated multi-part generation and post-processing merge pipeline for high-page-volume switchgear:

1. **Stage 1 (Automated Multi-Part Generation)**:
   When generating a Full Report for a substation with switchgear type `VCB` or `GIS` (resolved via `SwitchgearArchetype.VCB_CUBICLE` or `SwitchgearArchetype.GIS_CUBICLE`), the generator automatically partitions the planned Bill of Materials into modular, lightweight Word documents:
   - **Part 01 - Summary**: Front Page, Executive Summary Census, Visual Defect Summary, and Switchgear Overview.
   - **Parts 02 to (N+1) - Bay Files**: One independent Word document per switchgear panel, containing that panel's chamber scanning pages and any inline defect detail pages (TEV PRPD or thermal hotspots).
   - **Part (N+2) - TX and Condition**: Transformers, LVDB / Feeder Pillar, Battery Bank, Substation Condition pages, Visual Defect detail pages, and Sticker page.
   Non-VCB/GIS substations (such as standard RMU SF6, RMU Oil, and compact RMU) continue generating as a single consolidated Word document.

2. **Stage 2 (Post-Processing Multi-Part Discovery and PDF Stitching)**:
   The post-processing workflow discovers all valid `.docx` files through the existing 5-case discovery pipeline, groups matching `<STEM> - Part *.docx` files by their group stem, converts each part document to a temporary PDF, stitches the parts in numerical order using a new `merge_pdfs_batch()` converter method, appends the signed testsheet PDF from `processed_testsheet/pdf/<STEM>.pdf`, and emits the final unified client deliverable (`<STEM>.pdf`). The intermediate Word part documents remain untouched in the date folder for inspector reference and re-editing.

3. **Idempotency and Clean Lifecycle**:
   Re-running Full Report generation automatically cleans up any pre-existing part documents matching `f"{exact_stem} - Part *.docx"` for that substation before writing fresh ones, preventing orphaned files if panel counts or configurations change.

## User Stories

1. As a field report inspector, I want VCB switchgear reports to be generated in separate Word documents per panel, so that Microsoft Word and the FLIR Tools plugin never crash when I open and edit thermal photos.
2. As a field report inspector, I want each panel file to contain all of that panel's chamber scanning pages (cable, breaker, busbar, secondary, and PT), so that all diagnostic evidence for a single bay remains together in one place.
3. As a CBM diagnostic engineer, I want inline defect detail pages (such as TEV PRPD scatter graphs or thermal hotspot callouts) to stay attached immediately following their parent switchgear panel within that panel's Word document, so that anomalous findings are not separated from their bay.
4. As an inspector reviewing deliverables, I want Part 01 to contain the Front Page, Executive Summary Census, Visual Defect Summary, and Switchgear Overview, so that executive and lineup-level context can be reviewed without opening panel files.
5. As an inspector reviewing deliverables, I want the final part document to contain transformers, LVDB, battery bank, condition photos, visual defects, and stickers, so that non-switchgear assets are grouped logically and safely below page crash limits.
6. As a report automation operator, I want multi-part Word files to use descriptive names with zero-padded numbers (such as `005. TALAPIA (IR+VI) - Part 02 - Panel 1 (INCOMING 1).docx`), so that I can immediately tell which file to open when editing a specific bay.
7. As a report automation operator, I want standard RMU switchboard reports (such as 3-panel or 4-panel Indkom, Tamco, and Lucy RMUs) to continue generating as a single Word document, so that low-page reports are not needlessly split into parts.
8. As a post-processing operator, I want the post-processing workflow to automatically detect whether a substation has split part documents or a single document, so that I do not need to configure special flags or manual settings.
9. As a post-processing operator, I want the post-processing script to convert each Word part to PDF and stitch them in exact numerical order, so that the resulting document order perfectly matches contractual requirements.
10. As a TNB client representative, I want to receive a single, unified Full Report PDF deliverable per substation with the signed testsheet appended at the end, so that contractual filing and historical archiving remain standard across all substation types.
11. As a report operator re-running generation, I want existing part Word documents for that substation to be cleaned up before fresh parts are written, so that outdated ghost files are never left behind or accidentally merged.
12. As a CLI operator running dry-run inspection, I want to see whether a substation will generate as a single document or multiple parts, so that I have complete visibility into output plans before confirming execution.
13. As a software developer, I want the partition policy to be a pure domain component that works without Word COM dependencies, so that partitioning logic can be thoroughly unit tested in milliseconds.
14. As a quality assurance engineer, I want end-to-end tests using fake compilers and fake converters to verify the complete multi-part generation and stitching lifecycle, so that future refactors cannot break document assembly.

## Implementation Decisions

### Decision 1: Domain Partition Policy and Plan Document Chunks
The plan builder will introduce a partition policy that inspects the planned sequence of items. Archetype is accessed via `plan.package.switchgears[0].archetype`. If the switchgear archetype is `SwitchgearArchetype.VCB_CUBICLE` or `SwitchgearArchetype.GIS_CUBICLE`, the item sequence is partitioned into multiple `PlanDocumentChunk` structures:
- `PlanDocumentChunk(chunk_index=1, label="Summary", parts=[front_page, census, vi_summary, swg_overview])`
- `PlanDocumentChunk(chunk_index=2..N+1, label=f"Panel {p.panel_no} ({p.name})", parts=[panel_chambers, panel_inline_defects])`
- `PlanDocumentChunk(chunk_index=N+2, label="TX and Condition", parts=[transformers, lvdb, battery, condition, vi_defects, stickers])`
For all other archetypes, the policy emits a single chunk containing all planned parts with the default destination filename.

```python
@dataclass(frozen=True)
class PlanDocumentChunk:
    chunk_index: int
    label: str
    output_filename: str
    destination_path: Path
    parts: tuple[PlanPartItem, ...]
```

### Decision 2: Single-Pass Render with Chunked Compilation
In `FullReportComposer.compose()`, intermediate docx parts are rendered once via `plan.render_all()` in the `.temp/` workspace. The composer then partitions the rendered file paths across chunk boundaries and calls `compiler.compile(chunk_parts, chunk.destination_path)` for each chunk. Before compiling, the composer performs an idempotent pre-purge of any existing files matching `f"{exact_stem} - Part *.docx"`.

### Decision 3: Backward-Compatible Execution Result and Telemetry
To preserve backward compatibility with all existing CLI display functions and verification pipelines:
- `FullReportStationExecutionResult.output_path: Path | None` continues to hold the primary file (`Part 01` for multi-part, single `.docx` for RMU).
- Added `FullReportStationExecutionResult.chunk_paths: tuple[Path, ...] = ()` holding all generated file paths.
- Added `FullReportStationExecutionResult.is_multipart: bool = False`.
- `FullReportBatchResult.generated_paths` flattens all chunk paths across all stations.
- `FullReportPostProcessingTelemetry.docx_path: Path` continues to hold the primary file, accompanied by `part_docx_paths: tuple[Path, ...] = ()` and `is_multipart: bool = False`.

### Decision 4: DocumentConverter Batch Merge Seam
Extend `DocumentConverter` ABC with a first-class batch merge method:
```python
def merge_pdfs_batch(self, pdf_paths: Sequence[Path], output_pdf: Path) -> Path: ...
```
Implemented in `ComDocumentConverter` using PyPDF2 `PdfWriter` to merge all part PDFs into one file in a single pass without intermediate files. `FakeDocumentConverter` records batch calls in `merge_pdfs_batch_calls`. The existing 2-input `merge_pdfs()` remains untouched for backward compatibility.

### Decision 5: Post-Processing Staged Discovery and Group-Stem Matching
`_discover_docx_files()` remains unchanged to preserve its robust 5-case discovery logic. Immediately downstream, a new private helper `_group_multipart_targets()` groups discovered files matching `<STEM> - Part *.docx` by `<STEM>` and sorts them by numerical part index. Testsheet PDF matching is performed using the group stem (`<STEM>`), not individual part names.

## Testing Decisions

1. **Synthetic VCB Benchmark Fixture**:
   Create a self-contained synthetic benchmark fixture in `tests/benchmarks/` for PE 157 PERPUSTAKAAN AWAM (5-panel Tamco VCB 11kV with transition bay, PT on panel 4, minimal testsheet Excel, stub photos, and sliced sections).
2. **Pure Domain Testing**:
   Unit test `MultiPartPartitionPolicy` across diverse switchboard topologies:
   - 5-panel VCB lineup with transition bay and PT chamber.
   - VCB lineup with inline TEV PRPD defect pages, ensuring defect pages remain in the correct bay chunk.
   - 3-panel RMU SF6, ensuring it emits exactly one chunk.
3. **Headless Composer Testing**:
   Test `FullReportComposer` with `FakeDocumentCompiler` verifying that all chunks are compiled, named correctly, and that old part files are purged.
4. **Headless Post-Processing Testing**:
   Test `FullReportPostProcessingWorkflow` with `FakeDocumentConverter` verifying multi-part grouping, ordered batch PDF concatenation via `merge_pdfs_batch()`, and testsheet appending into `<STEM>.pdf`.
5. **Prior Art**:
   Existing tests in `tests/test_full_report_plan_builder.py`, `tests/test_full_report_composer.py`, and `tests/test_full_report_postprocessing.py` serve as patterns.

## Out of Scope

- Splitting transformer components into individual files. Transformers, LVDB, condition photos, and stickers will remain combined in the final part document.
- Splitting standard RMU switchgear (Indkom, Tamco, Lucy, Siemens 8DJH) into multi-part documents.
- Emitting separate client deliverable PDFs. Client always receives a single combined PDF (`<STEM>.pdf`).

## Further Notes

- In the future, if 33kV substations with dual transformers require further splitting, the partition policy can be extended with an additional transformer chunk without altering the post-processing merge logic.
