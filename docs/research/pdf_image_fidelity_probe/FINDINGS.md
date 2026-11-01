# PDF Image Fidelity Probe: Findings (01-11-2026)

Goal: images in the Full Report PDF are as readable as in the source `.docx` (the manual Adobe "High Quality Print" output is the reference). Probed on copies of Cameron Highland 17-08-2026 reports 100, 101, and 102, using a private Word instance (Word 16.0.20527). Production files and the operator's Word profile were left unchanged.

## What Word native export actually does

- Pictures above roughly 200 PPI on the page are resampled to roughly 200 PPI. Graphs are 1200x380 PNGs placed at 3.15 in (381 PPI) and come out at 629x199. Nameplate photos are 2048x1536 JPEGs placed at about 3 in (about 700 PPI) and come out at about 600x450.
- Pictures at or below about 220 PPI (640x480 and 700x526 JPEGs) pass through at full size.
- Bitmaps inside WMF OLE previews (640x480 thermograms plus 11x142 colour-scale bars) keep their size but are re-encoded as JPEG.
- The earlier reports' "53x53 thumbnails" are a 53x53 icon that exists in the source DOCX. They were never downsampled thermograms.

## H1: make Word stop downsampling. Rejected.

None of these changed a single image dimension:

- `w14:defaultImageDpi` = 0, 330, 32767, 65536 (`doNotAutoCompressPictures` is already set in the documents)
- `ExportAsFixedFormat2(OptimizeForImageQuality=True)`
- `SaveAs2(FileFormat=17)`
- `HKCU\...\Word\Options\LastPdfExportImageDownsampleOption` = 0, 1, 2 (original value 1 restored)

`Word.Options` exposes no image-resolution property.

## H2: native export, then restore source images. Works.

`h2_swap.py` harvests source pixels from the DOCX: raster blips with `srcRect` or VML crop applied, and 24/32-bit DIBs inside WMF/EMF files. It matches each PDF image XObject by aspect ratio and pixel similarity, and replaces an image stream only when the source has more pixels, or is lossless at an equal or higher pixel count. Page content streams are never modified.

| Report | Replaced | Of which upscaled to source px | Unmatched (already full-res) | Size | Restore time |
|---|---|---|---|---|---|
| 101 | 22 | 9 | 9 (icons, 28x384 scale bars, rasterised metafile composites) | 2.4 → 7.7 MB | 7 s |
| 102 | 30 | 7 | 2 | 2.4 → 5.3 MB | 7 s |
| 100 | 33 | 9 | 2 | 3.2 → 7.7 MB | 10 s |

Verification (`h2_verify.py`):

- Page count, text, and links are identical. The worst page render difference at 50 dpi is 0.29/255.
- All restored image sizes survive the production `merge_pdfs_batch` plus a `garbage=3, deflate=True` re-save (the same save options as `us_audio`).
- Restored report 100 matches the Adobe deliverable's large-image dimensions exactly (1200x380, 640x480, 70xx525, 755x566).
- Visual evidence: `cmp_graph_full.png` (graph and table text), `cmp_p15_x125.png` (nameplate photo), `cmp_p4_x46.png` (thermogram). In each image, the top or left half is native and the bottom or right half is restored.

## Matching safety: thumbnails are not enough

Comparing 64 px thumbnails cannot reliably separate look-alike images. Different ultrasound graph panels scored 0.1 against 2.4 (mean grey diff), and some pairs of distinct sources were only 0.1 apart.

A second check at the PDF image's own resolution does separate them. It resamples the source to that size and measures the % of pixels whose grey diff is ≥ 48:

| Case | Measured % pixels differing |
|---|---|
| True matches, all 3 reports (~180 images) | ≤ 0.23% |
| Distinct look-alike graphs (wrong panel) | ≥ 2.2% |
| Word rasterised composites / alpha icons (no single source) | ≥ 2.2% |

The prototype therefore accepts a match at ≤ 0.5% and treats any distinct candidate under 1.5% as ambiguous (skip). It always restores the best-scoring source. An earlier variant preferred the larger of two "equivalent" files and swapped `image39` (700x526) for `image3` (753x566) in report 101. Those are near-identical but are not the same file, so that rule was dropped.

## Replacement mechanism

`Page.replace_image` draws the new image onto the page and then blanks that drawing. Rendering is unchanged, but the page is left with an extra empty content stream and an orphan `fzImg*` resource, and the strict invariance gate rejects it. `replace_xobject()` in `h2_swap.py` rewrites the image XObject (stream, size, colour space, filter, SMask) instead, so page objects stay byte-identical. On report 101 the gate passes, the render difference is unchanged at 0.26/255, and output is 4.9 MB against 7.7 MB.

## 33kV multi-part run: PPU APMM (32 parts, `h3_batch.py`)

Each part was run through a native export, restoration with the final matching and XObject rewrite rules, and the strict invariance gate. All restored parts were then merged with the production `merge_pdfs_batch`.

- **All 32 parts: invariance OK.** Content bytes, text, links, annotations and drawn image placements are identical.
- **Counts:** 268 images in total, 161 restored, 32 unmatched (icons and colour bars already at full resolution), 0 ambiguous, 0 self-check rejects.
- **Time:** export 401 s plus restore 45 s (about 11% overhead). The largest part (17.9 MB, 57 images) took 15 s to restore with a 197 MB peak working set.
- **Merge:** 0.2 s, 242 pages, no image size lost. The merged file is 19.7 MB against a 30.1 MB sum of restored parts, because `garbage=3` dedups images repeated across parts.
- **Sleep in the middle of the run:** the laptop slept for 12 minutes during Part 19's export. Word resumed and finished correctly (732 s). #147 now keeps the system awake during batches.

## 33kV rerun: PPU APMM with real section images (updated parts, 01-11-2026)

The maintainer replaced the placeholder images with real visual images for every section. The parts are now 6–16 MB, and Part 32 is 41 MB.

- **All 32 parts: invariance OK.** 206 pages, 645 images, 328 restored, 1 ambiguous (skipped safely), 0 self-check rejects.
- **Thermograms are now 640x480** FLIR preview bitmaps (previously 207x159 placeholders) and are restored losslessly instead of Word's JPEG copies.
- **Ultrasound panels** are restored from 629x199 to 1200x380. In Part 32 the 7 placements share one PDF image, and restoring it fixes all 7.
- **Photos** at 640x480 and 701x525 (about 210–220 PPI) pass through Word untouched and are left as they are.
- **The one ambiguous skip** is a 13x171 colour-scale bar shared by two near-identical thermograms. Word's copy is already full size.
- **Time:** export 404 s plus restore 80 s. Part 32 (41 MB, 123 images) took 45.6 s to open, 9.2 s to export, and 26.2 s to restore.
- **Merge:** 32 parts produced a 36.4 MB, 206-page file in 0.3 s, with no image size lost (restored parts sum to 45.2 MB; `garbage=3` dedups).
- **New failure mode.** In the long-lived Word session, Part 32's `ExportAsFixedFormat` **returned without error and wrote no file**, after 31 large parts had gone through the same `WINWORD.EXE` (32-bit). The same part exported correctly in a fresh Word instance. #147 must detect the missing output and retry once in a recycled Word session.

## 33kV observation

The FLIR CIRViewer preview bitmaps inside 33kV parts (PPU APMM) are **207x159**, against **640x480** in 11kV reports. Restoration makes them lossless but cannot add pixels the DOCX does not contain. If 33kV thermograms need more detail, the fix belongs upstream in Full Report generation (how the CIRViewer preview is produced), not in conversion.

## Known limits of the prototype

- Cropped JPEG sources are re-encoded (q95, 4:4:4) at full source resolution. Uncropped sources are inserted byte-for-byte.
- Word's rasterisation of a whole metafile (bitmap plus vector overlay, e.g. 603x460) is left untouched because no single source bitmap represents it.
- Matching uses heuristics (aspect within 4%, mean abs grey diff ≤ 10 at 64 px). Rotated or recoloured pictures would fail to match and stay as Word rendered them, which is safe.
