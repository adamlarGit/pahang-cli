# 9. Native Word Export with Source Image Restoration for Full Report PDFs

Date: 2026-11-01
Status: Accepted
Supersedes: [ADR 0008: Spooler-Independent Full Report PDF Conversion](./0008-spooler-independent-full-report-pdf-conversion.md)

> **This ADR fully replaces ADR 0008.** ADR 0008 set the goal (a spooler-independent conversion path that preserves source pixels) and an investigation order (native Word settings first, then direct Distiller `PrintToFile → FileToPDF`). That investigation has now been run. Its first candidate failed, and a different mechanism met the goal. Where the two ADRs disagree, this one wins. ADR 0008 stays in the repo as history only.

## Context

Full Report deliverables must keep images readable at zoom: nameplate photos, thermograms, and the ultrasound graph and measurement panels. The manual Adobe PDF print with the `High Quality Print` preset gave acceptable quality. Automating that path (tickets #140–#145) caused Session 0 Distiller deadlocks and a large amount of spooler, registry, and process-management code. ADR 0008 therefore barred the Adobe virtual printer from production batches and ordered an investigation.

The fidelity probe ([findings](../research/pdf_image_fidelity_probe/FINDINGS.md)) was run on 01-11-2026 against copies of Cameron Highland 17-08-2026 reports `100`, `101` and `102` and established the following:

1. **The quality loss comes from Word's native PDF export, not from Session 0.** Word resamples any picture placed above roughly 200 PPI down to roughly 200 PPI:
   - 1200x380 ultrasound panels come out at 629x199, which blurs their table text.
   - 2048x1536 nameplate photos come out at about 600x450.
   - Thermogram bitmaps inside FLIR ActiveX preview metafiles keep their size but are re-encoded as JPEG.

   Pictures at or below about 220 PPI pass through untouched. The "53x53 thumbnails" cited in earlier investigations are a 53x53 icon present in the source DOCX, not downsampled thermograms.
2. **Word cannot be configured out of this.** None of the following changed a single output image dimension:
   - `w14:defaultImageDpi` (0 / 330 / 32767 / 65536), with `doNotAutoCompressPictures` already set
   - `ExportAsFixedFormat2(OptimizeForImageQuality=True)`
   - `SaveAs2(FileFormat=17)`
   - the `LastPdfExportImageDownsampleOption` registry value (0 / 1 / 2)

   `Word.Options` exposes no image-resolution property. ADR 0008's first candidate ("native Word export with converter-owned quality settings") is therefore not achievable.
3. **Replacing image streams after export works.** A prototype ([`h2_swap.py`](../research/pdf_image_fidelity_probe/h2_swap.py)) reads the original pixels from the DOCX and replaces the matching PDF image streams. It gave these results on all three reports:
   - Page count, text, and links are identical, and the worst page render difference is ≤ 0.29/255.
   - Graphs, photos, and thermograms are back to source dimensions, and thermograms are lossless.
   - Every restored image survives the production merge and the audio-embedding save.
   - Report `100`'s large-image dimensions match the Adobe `High Quality Print` reference deliverable exactly.
   - The cost is 7–10 s per report, and output grows from about 2.4 MB to 5–8 MB, comparable to Adobe output.

## Decision

Full Report DOCX→PDF conversion is **native Word `ExportAsFixedFormat` followed by Source Image Restoration**, applied to each Full Report Part before any merge.

1. **Single backend.** The Adobe PDF virtual printer is removed from the Full Report converter, along with everything that existed only to support it:
   - Distiller COM pre-warm
   - `PrinterJobControl` registry registration
   - per-document `ActivePrinter` switching to Adobe PDF and `PrintOut`
   - the spooler `ConversionFeedbackMonitor`
   - port drain and job purge
   - stray Acrobat process sentinels
   - dynamic spool timeouts

   This removal happens only after the acceptance batch below passes with the new path. There is no feature flag.

   **Kept:** the session-level printer selection (`configure_uniform_printer`, run once per batch session). Word lays out pages against the active printer's metrics, so this selection decides pagination for native export. It never creates a print job. Removing it would silently change the layout of every 11kV and 33kV part, so any change to it needs its own decision.
2. **Source Image Restoration** runs inside `convert_docx_to_pdf`, on the PDF of exactly one DOCX, while the one-to-one mapping between that PDF and its DOCX still holds. Merge (`merge_pdfs_batch`), testsheet append, and ultrasound audio embedding are unchanged. Testsheet PDFs exported from Excel are never touched.
3. **It may only change image streams.** Page content streams, text, links, annotations, and page geometry are never modified. An image is replaced only when its matched source has more pixels than the PDF copy, or is lossless at an equal or higher pixel count. When a match is ambiguous or fails its self-check, the image Word rendered stays in place.
4. **Failure policy.** If restoration fails for a part, that part keeps its native PDF, the batch continues, and the CLI warns the operator. The batch summary shows, per report, how many images were restored and how many were left unmatched. Unmatched images do not fail the batch.
5. **Scope.** Full Report (11kV and 33kV) only. Quick Report and testsheet conversion are out of scope until they show the same defect.
6. **Acceptance gate.** This extends the `PdfConversionDeliveryContract` gate with a 33kV case, because 33kV substations are always multi-part. The gate is:
   - 11kV Cameron Highland 17-08-2026 reports `093`–`102`, including `100`, `101`, `102`
   - the full 32-part 33kV `01. PPU APMM 3311kV` (GEBENG 07-10-2026), which includes a 17.9 MB "TX and Condition" part

   Each report in the gate must show all of the following:
   - unchanged text, links, and per-page image placement against its native export
   - no restored image lost in merge
   - zero wrong-source substitutions in the restoration report
   - a completed deliverable with ultrasound audio still embedded

## Relationship to ADR 0008

| ADR 0008 element | Status under ADR 0009 |
|---|---|
| Ban the Adobe virtual printer from production batches | **Kept and completed**: the code path is deleted, not just bypassed |
| `PdfConversionDeliveryContract` (no spooler; source pixels preserved in `101`, `102`, plus one normal report) | **Kept**: met by native export plus restoration, verified by the probe |
| "Native Word export with converter-owned quality settings" as first candidate | **Rejected**: Word has no setting that stops export resampling (Context §2) |
| `WordExportConfigurationIsolationPolicy` (apply and restore Word settings) | **Retired**: the converter no longer changes any Word or Office setting |
| Direct Session 1 Distiller `PrintToFile → FileToPDF` as second candidate | **Not pursued**: restoration meets the contract without Adobe, and `PrintToFile` still creates a spooler job |
| `InterimPdfFallbackPolicy` (native fallback, operator notice) | **Replaced**: native export is the primary path, and the notice now covers restoration failure (Decision §4) |

## Considered Options

- **Keep hardening the Adobe virtual printer (tickets #140–#145).** Rejected. The failure depends on Session 0 and port-monitor state that the CLI cannot control, and each fix added more process and registry management.
- **Configure Word so native export keeps full resolution.** Rejected after testing: no setting has any effect (Context §2).
- **`PrintToFile` PostScript followed by Distiller `FileToPDF`.** Not pursued. It still uses the print spooler and the Adobe driver, keeps a dependency on Acrobat 11, and would cost 45–60 s of spooling per large document (ticket #144 measurements).
- **Microsoft Print to PDF or third-party virtual printers.** Rejected. They are spooler-based, and their image fidelity is unproven.
- **Restoring images on the merged deliverable instead of per part.** Rejected. After a merge, images from several parts and the testsheet share one file, which makes source matching ambiguous.

## Consequences

- Deliverable PDFs grow to roughly the size of the Adobe outputs (8–12 MB for 11kV reports). Multi-part 33kV reports grow in proportion to their image count.
- Conversion no longer depends on Acrobat, Distiller, the print spooler, or the printer queue. Several hundred lines of converter code and their mocked tests are removed.
- Restoration is heuristic matching (aspect ratio plus pixel similarity) with a mandatory self-check per image. The safe failure mode is "Word's rendering is kept", never "the wrong picture is inserted".
- Any picture Word flattens together with vector overlays into a single raster has no single source bitmap, so it stays at Word's resolution.
- Implementation and robustness requirements (atomic temp files, DOCX snapshot consistency, memory bounds for large multi-part 33kV batches, idempotence) are specified in ticket #146 of the 33kV workflow map.

## References

- [ADR 0008](./0008-spooler-independent-full-report-pdf-conversion.md) (superseded)
- [ADR 0005](./0005-vcb-gis-multipart-full-report-pipeline.md): multi-part pipeline that restoration plugs into
- [ADR 0007](./0007-ultrasound-audio-embedding-and-conversion.md): audio embedding that runs after restoration
- [Probe findings and evidence images](../research/pdf_image_fidelity_probe/FINDINGS.md)
- [Session 0 deadlock investigation](../research/adobe_pdf_spooler_session0_deadlock_investigation.md) (historical; its fidelity premise is corrected by this ADR)
- Tickets #140–#145 (Adobe path history) and #146 (implementation of this decision)
