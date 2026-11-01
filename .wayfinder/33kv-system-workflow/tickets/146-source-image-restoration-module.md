<!-- status: closed -->
# Ticket #146: feat(postprocessing): Source Image Restoration module

## Parent
Part of #145 (and #144, #143, #142, #141, #140). Those tickets built and hardened the Adobe virtual-printer path, which this work replaces.
Implements [ADR 0009](../../../docs/adr/0009-native-export-with-source-image-restoration.md), which supersedes [ADR 0008](../../../docs/adr/0008-spooler-independent-full-report-pdf-conversion.md).
Evidence: [`docs/research/pdf_image_fidelity_probe/FINDINGS.md`](../../../docs/research/pdf_image_fidelity_probe/FINDINGS.md). The prototype is `docs/research/pdf_image_fidelity_probe/h2_swap.py`.

## Context
Word's native `ExportAsFixedFormat` resamples pictures placed above roughly 200 PPI down to about 200 PPI, and re-encodes FLIR CIRViewer preview bitmaps as JPEG. No Word setting prevents this. Source Image Restoration puts the original pixels from the DOCX back into the exported PDF, one Full Report Part at a time, by replacing image streams only.

## What to build
A deep module, `src/postprocessing/image_restoration.py`. It has no COM, Word, or printer dependency, so it is unit-testable with synthetic fixtures.

```python
def restore_source_images(docx_bytes: bytes, native_pdf: Path, output_pdf: Path) -> RestorationReport
```

`RestorationReport` is a frozen dataclass with these fields:
- `images_total`
- `restored`
- `unmatched`
- `ambiguous`
- `self_check_rejected`
- `elapsed_s`
- `entries` (per-image page, xref, PDF size, source label, action)

The module raises `RestorationError` on any failure the caller must handle by keeping the native PDF.

### 1. Source harvesting
- Read the DOCX from **the caller's byte snapshot** (`zipfile.ZipFile(BytesIO(...))`), never from the path. This keeps the harvested pixels identical to what Word exported (see #147).
- Scan `word/document.xml`, `header*.xml` and `footer*.xml` through their `_rels`.
- **DrawingML** `a:blip r:embed` with `a:srcRect`: apply the crop, and skip negative (padding) crops.
- **VML** `v:imagedata r:id` with `croptop`, `cropbottom`, `cropleft` and `cropright` (`f` = 1/65536).
- **WMF/EMF previews** (FLIR CIRViewer OLE objects): extract every 24/32-bit uncompressed DIB (`BITMAPINFOHEADER`, `biSize=40`) as a lossless candidate.
- Skip external (linked) relationships. The research found none, but this is a guard.
- **Decode lazily.** Hold the original bytes plus the header dimensions and a 64 px grey thumbnail per source. Decode full pixels only for stage-2 verification and encoding, and release them straight after. Peak memory must not grow with the number of images in the part.

### 2. Matching (thresholds come from measurements on reports 100, 101, 102 and the 33kV APMM parts)
- **Stage 1 (pre-filter).** Aspect ratio within 4%, and 64 px grey thumbnail mean-abs-diff ≤ 10. Keep the best 6.
- **Stage 2 (verify at the PDF image's own resolution).** LANCZOS-resample the source to the PDF image size, then measure the % of pixels whose grey diff is ≥ 48.
  - Accept if ≤ **0.5%**. True matches measured ≤ 0.23%.
  - Distinct look-alikes, such as other ultrasound graph panels, measured ≥ 2.2%.
- **Ambiguity guard.** If any other candidate scores below **1.5%** and is not content-equivalent to the best (mutual stage-2 score ≤ 0.5%), skip the image and count it as `ambiguous`.
- **Always restore the best-scoring source.** Never substitute a different file that is "equivalent" but larger. This was observed on report 101: `image39` (700x526) and `image3` (753x566) are near-identical but are not the same file.

### 3. Replacement rules
- Replace only when the source has **more pixels** than the PDF copy (> 2%), or is **lossless while the PDF copy is JPEG** at an equal or higher pixel count. Never trade pixels for losslessness.
- Encoding:
  - Uncropped raster: original bytes, inserted verbatim.
  - Cropped JPEG: JPEG q95 with 4:4:4 subsampling at full source resolution.
  - PNG or DIB: optimised PNG. Alpha is preserved by PyMuPDF as an SMask.
- **Pre-write self-check.** Decode the exact payload bytes, resample them to the PDF image size, and re-run stage 2 against Word's pixels. If the result is above 0.5%, keep the image and count it as `self_check_rejected`.
- **Rewrite the image XObject in place, once per unique xref, and skip SMask xrefs.** The rewrite covers the stream (`update_stream`) and its `/Width /Height /BitsPerComponent /ColorSpace /Filter`. It clears `/DecodeParms` and `/Decode`. For an alpha source it creates a new `/SMask` stream. For an opaque source it removes the old `/SMask`, because that mask was sized for Word's pixels.
- **Do not use `Page.replace_image`.** It draws the new image onto the page and then blanks that drawing, which leaves an extra empty content stream and an orphan `fzImg*` resource on the page. The 33kV probe caught this with the invariance gate. Rewriting the XObject in place leaves every page object byte-identical, and the output is smaller (101: 4.9 MB against 7.7 MB).

### 4. Invariance gate (runs before anything is published)
Compare `output_pdf` with `native_pdf` page by page:
- page count and page rects
- **page content bytes** (`read_contents()`)
- text
- link URIs
- annotation count
- the drawn image placements (`get_image_info()` bbox and transform, compared **without xrefs**, because a full save renumbers objects)

Any difference raises `RestorationError`. The placement check protects the sound-clip speaker-icon anchor, which sits in the x 180–250 pt column (`sound_embedder.find_sound_clip_anchor`).

### 5. File safety
- The input files are never modified.
- Write to a unique temp sibling, `.tmp_restore_<token>_<name>` (`token = uuid4().hex[:8]`). Save fully with `garbage=3, deflate=True`, and never incrementally.
- Close every `fitz.Document` with context managers before publishing, then publish with `safe_replace_with_retry` (Windows AV, indexer and sync locks). The temp file is removed in `finally` on every path. This follows `AtomicPdfSavePolicy`.

### 6. Idempotence
Restoring an already restored PDF must make zero replacements.

## Acceptance criteria
- [x] `restore_source_images` exists with the interface above and has no COM or Word imports.
- [x] Unit tests (TDD, synthetic fixtures built with python-docx and PyMuPDF, no client data) cover:
  - [x] a downsampled PNG is restored to its source pixels
  - [x] JPEG re-encoding of a lossless source is restored losslessly
  - [x] a cropped source (DrawingML and VML) is restored to its cropped region
  - [x] a DIB inside a WMF is restored
  - [x] **look-alike graphs with different values each map to their own source (wrong-source substitution impossible)**
  - [x] an ambiguous match is skipped
  - [x] a smaller source never replaces a larger PDF image
  - [x] alpha is preserved
  - [x] the self-check rejects a payload that does not match
  - [x] the invariance gate raises on a tampered output
  - [x] idempotence
  - [x] a corrupt DOCX snapshot raises `RestorationError`
  - [x] no temp file is left after success or failure
- [x] Peak memory is bounded per part (lazy decode). The 33kV probe (#149) records the measured peak.
- [x] All tests pass with zero regressions.

## Blocked by
None. Can start immediately.
