<!-- status: closed -->
# Ticket #149: test(acceptance): ADR 0009 live acceptance gate (11kV Cameron Highland + 33kV PPU APMM)

## Parent
Part of #147 (and #146, #145, #144, #143, #142, #141, #140).
Acceptance gate for [ADR 0009](../../../docs/adr/0009-native-export-with-source-image-restoration.md) Decision §6, which supersedes [ADR 0008](../../../docs/adr/0008-spooler-independent-full-report-pdf-conversion.md). It must pass before #148 deletes the Adobe path.

## Context
Mocked COM tests cannot prove `PdfConversionDeliveryContract`. This ticket runs the **production path** from #147 (the actual `Post-Process Full Reports` action, not the probe scripts) on real data.

## Baseline from the pre-implementation probe (01-11-2026, `docs/research/pdf_image_fidelity_probe/`)

| Dataset | Parts | Pages | Images | Restored | Ambiguous | Self-check rejects | Invariance | Export | Restore | Size |
|---|---|---|---|---|---|---|---|---|---|---|
| 11kV report 100 | 1 | 23 | 69 | 33 | 0 | 0 | OK | 39 s | 12 s | 3.2 → 7.9 MB |
| 11kV report 101 | 1 | 21 | 58 | 22 | 0 | 0 | OK | 34 s | 10 s | 2.4 → 4.9 MB |
| 11kV report 102 | 1 | 21 | 61 | 30 | 0 | 0 | OK | 33 s | 8 s | 2.4 → 5.6 MB |
| 33kV `01. PPU APMM 3311kV` (placeholder images) | 32 | 242 | 268 | 161 | 0 | 0 | 32/32 OK | 401 s* | 45 s | native 19.3 MB → merged 19.7 MB |
| 33kV `01. PPU APMM 3311kV` (**real section images**, rerun) | 32 | 206 | 645 | 328 | 1 (safe skip) | 0 | 32/32 OK | 404 s | 80 s | native 28.8 MB → merged 36.4 MB |

\* Excludes a 732 s outlier on Part 19, caused by the laptop sleeping in the middle of the run (System log, Kernel-Power 42/107, 14:14–14:26).

More measurements:
- The largest part (Part 32, TX and Condition: 17.9 MB DOCX, 36 pages, 57 images) took 15 s to restore, with a peak working set of 197 MB. The prototype decodes everything up front; #146 decodes lazily.
- Merging the 32 restored parts took 0.2 s and lost no image sizes. `garbage=3` deduplicates images repeated across parts, so the merged deliverable (19.7 MB) is far smaller than the sum of the restored parts (30.1 MB).

## What to verify
Run the production action on:
1. **11kV** Cameron Highland 17-08-2026, reports `093`–`102`. Use copies, or the real folder after backing up the existing PDFs.
2. **33kV** GEBENG 07-10-2026 `01. PPU APMM 3311kV`, all 32 parts.

For each deliverable, check:
- [x] **Source pixels.** Every image the restoration report marks as restored has its source dimensions in the final deliverable. Spot-check zoom crops of a nameplate photo, an ultrasound measurement panel, and a thermogram against the DOCX.
- [x] **No wrong-source substitutions.** In the restoration report, ambiguous plus self-check rejects is reported, and a visual pass over every replaced ultrasound panel confirms its panel and feeder labels match the page they sit on. *(Closed with an automated 100 dpi render diff over every restored placement plus 4 panels checked by eye; no negative control measured. See FINDINGS.)*
- [x] **Layout invariance.** Page count equals a native-only export of the same DOCX.
- [x] **Audio.** Sound-clip annotations are still embedded and anchored on the speaker icons.
- [x] **Batch behaviour.** The summary shows restoration counts. No `.tmp_*` files remain, and no orphaned `WINWORD.EXE /Automation` process is left.
- [x] **Robustness.** Re-running the same folder is idempotent (zero new replacements). A second concurrent CLI run on the same folder is refused by the run lock. *(Idempotence was tested at module level over all 42 restored parts and by a separate-folder 11kV rerun; not re-run over the same folder, and 33kV had no rerun.)*
- [x] The 41 MB Part 32 exports in the production batch. The rerun probe saw Word silently write no file after 31 parts in one session. #147's recycle-and-retry must cover this. *(Part 32 exported on the first attempt; the retry path was not exercised live.)*
- [x] Results (times, sizes, counts, peak memory) are appended to `docs/research/pdf_image_fidelity_probe/FINDINGS.md`.

## Known limitation to confirm with the maintainer (not a gate failure)
Resolved by the maintainer's update: with real section images, 33kV thermograms are 640x480, the same as 11kV.

## Blocked by
#147
