---
ticket: 230
type: prototype
map: 221
status: open
updated: 2026-11-12
agent: Claude Code, claude-opus-5-5
---
# Can every slice bound be read from a Quick Report's own XML, without Word?

## Verdict

Yes, with one change to the CBM rule. The ticket's rule cuts the CBM region at every page break. It passes every check on 345 of 401 live Quick Reports (C2). It breaks on 27 reports where a page break is missing between two defect tables, or between the summaries and the first one (C3). In those reports each defect table still gets its own rendered page, because a defect table fills the page and pushes the next one over (C10). Cutting the CBM region at each defect table instead, which rests on the owner's rule that one CBM defect fills exactly one page, fixes all 27 (C5). On the nine reports run through the COM slicer, that rule gives the same text, tables, images and objects as COM for every slice and every CBM page (C9, C10).

The Master count check is the weak part. It fails on 38 reports under the defect-table rule. None of the 38 is a slicing fault: 7 have no CBM rows in the Master and 31 hold more CBM pages than the Master generates, mostly extra overview views an operator seems to have added (C6, C7, C8). The COM slicer never checks this count (C12) and keeps those pages.

| Check | Ticket rule (cut at breaks) | Defect-table rule |
|-------|-----------------------------|-------------------|
| Reports passing every check | 345 of 401 | 353 of 401 |
| Each CBM piece holds exactly one defect table | fails on 27 reports | holds by construction |
| Header parses | yes, every CBM piece | yes, every CBM piece |
| CBM page count matches the Master | fails on 42 | fails on 38, none a slicing fault |
| Same slices as COM, five benchmarks | 5 of 5 | 5 of 5 |
| Same slices as COM, four failure-shape reports | 1 of 4 | 4 of 4 |

Recommendation: structure-derived bounds are enough. Don't build Slice Anchors (#226) on this evidence. Build the slicer on the defect-table rule, and make the Master count a Run Record warning rather than a fallback trigger. Fall back to COM for what the XML can't place: Strict Open XML files (C1), a missing slicer heading, or a non-summary table in the summary area.

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | The two project folders hold 401 Quick Report `.docx` files under `QUICK REPORT`. 400 read. One is saved as Strict Open XML (`purl.oclc.org` relationship types), which python-docx can't open. | Tested | `evidence/bounds.py`, `evidence/results.json` (`unreadable`), `evidence/live_data_read.tsv` |
| C2 | The ticket's rule (front page before the first break, heading sections as in `slice_sections`, CBM region cut at every break) passes every check on 345 of 401 reports. 8 more pass the structural checks but have no Master match: they are copies in a `GEBENG/New folder` that no testsheet package points to. | Tested | `evidence/summary.json`, `evidence/run.log` |
| C3 | The ticket's rule fails on 27 reports with a missing break: 24 have two or three defect tables in one piece, and 3 have the first defect table in the summary piece. 9 reports have a page break inside a defect table. 2 reports hold CBM pages naming another substation. | Tested | `evidence/results.json`, `failures` |
| C4 | Every page break in the 401 reports is a `w:br w:type="page"`. None uses `pageBreakBefore` or a section break in the body. | Tested | `evidence/results.json`, `page_breaks` |
| C5 | The defect-table rule passes every check on 353 of 401 reports. Its failures are 38 count mismatches, 2 reports with pages naming another substation, and the Strict Open XML file. | Tested | `evidence/summary.json`, `rule_b_*` |
| C6 | Of the 38 count mismatches under the defect-table rule, 7 are 33kV reports whose Master has no CBM rows for the station, and 31 hold more CBM pages than the Master generates. None holds fewer. | Tested | `evidence/summary.json`, `rule_b_mismatch_causes` |
| C7 | Overview pages with a suffixed area (`OVERVIEW_TOP`, `_BOTTOM`, `_REAR`, `_LHS`, `_RHS`) make up 35 pages in 23 of the 38 mismatching reports, and 1 page in the 354 matching reports. | Tested | `evidence/summary.json`, `rule_b_suffixed_overview_pages` |
| C8 | The extra CBM pages were added by operators after the compile. | Assumed | none. Settled by the owner checking a few of the 31 reports, or by re-rendering one report's CBM parts from its Master and comparing. |
| C9 | On the five benchmarks (Talapia, Sentosa, 094, APMM, PE157) every slice matches the COM slicer under both rules: front page, VI summary, condition pages, VI defect pages, sticker page, and each CBM page. Compared by whitespace-free text hash and by table, image and object counts. | Tested | `evidence/com_compare.json`, `evidence/bounds.py` `compare_with_com` |
| C10 | On four failure-shape reports (Kuala Lipis, Astana View, Lian Fatt, Telanok) the defect-table rule matches COM for every slice and every CBM page. The ticket's rule misses 2 of 4, 2 of 2 and 4 of 4 CBM pages on Lipis, Astana and Telanok, and its Telanok VI summary swallows the four defect pages. | Tested | `evidence/com_compare.json` |
| C11 | The front-page rule (everything before the first page break) matches COM in 9 of 9 compared reports. In all 401 reports Word's saved layout has no rendered page break before the first explicit one, so page 1 ended at that break when each file was last saved. | Tested | `evidence/com_compare.json`, `evidence/summary.json` `front_page_lrpb_nonzero` |
| C12 | The COM slicer doesn't compare its CBM pages with any Master count. This prototype takes the count as the pages `CbmDefectPlanner` and `CbmDefectPageBuilder` would render from the QR03 CBA rows: one overview page per group plus one page per detail defect. | Read | `src/full_report/slicer.py` `_slice_cbm_defects_from_doc`, `src/full_report/plan_builder.py` lines 963 to 985, `src/quick_report/cbm_defect_planner.py`, `src/quick_report/cbm_defect_pages.py` `build` |
| C13 | The Quick Report compiler inserts a page break before every part after the first. | Read | `src/quick_report/compiler.py` lines 322 to 323 |
| C14 | The missing breaks were deleted by operators, not lost in the compile. | Assumed | none. Settled by recompiling one affected report from its rendered parts and checking for the break. |
| C15 | Slicer headings are often split across runs and vary in case: `EXECUTIVE SUMMARY` spans more than one `w:t` in 99 reports, `SUBSTATION CONDITION` in 44 and `VISUAL DEFECT SUMMARY` in 29. Joined and upper-cased, every heading matched. No retyped heading and no heading split across two paragraphs was found. | Tested | `evidence/results.json`, `notes` and `near_miss_headings` |
| C16 | A page break inside a defect table is harmless in Lian Fatt: both rules give the same CBM pages as COM. The other 8 reports with that shape weren't run through COM. | Tested | `evidence/com_compare.json` `lianfatt` |
| C17 | One file under the project folders changed during the final run, out of 91,879 compared by path, size and modified time: `<BASE>/FULL REPORT/40. PMU JENGKA.txt`, an operator's hand-written note saved at 18:44:02. The script writes only to `--out`, and no `.txt` is written by it or by the slicer it calls. The exploratory run before it changed nothing. | Tested | `evidence/run.log`, `evidence/summary.json` `read_only_changed_files`, `evidence/bounds.py` |
| C18 | The live Talapia Quick Report holds 3 CBM defect tables, not the 27 the ticket background describes. | Tested | `evidence/com_compare.json` `talapia`, `evidence/results.json` |

## Detail

### The two CBM rules

Both rules read the body as one stream of text segments, tables and page breaks. A paragraph holding a break is split at the break, because a break and the next heading can share a paragraph. Talapia has one: body element 32 holds a break followed by `SUBSTATION CONDITION`. Headings match on joined `w:t` text, upper-cased, by equality, so `VISUAL DEFECT` never matches `VISUAL DEFECT SUMMARY`.

**Ticket rule.** Between the front page and `SUBSTATION CONDITION`, cut at every page break. A piece with a summary heading is a summary piece. A piece with one parsing defect table is a CBM page. A piece with two is a failure.

**Defect-table rule.** Find every table in that region whose header parses with `CbmDefectHeaderParser`. Between two defect tables, cut at the last page break if there is one, otherwise at the start of the second table. The summary area ends the same way before the first defect table. The VI summary ends at whichever comes first: the next break, the first defect table, or `SUBSTATION CONDITION`. A table in the summary area that isn't a summary table (first cell `NO.`) is a failure.

### Failures by shape

Ticket rule, 401 reports. A report can show more than one shape.

| Shape | Reports | Notes |
|-------|---------|-------|
| Deleted page break | 27 | 24 with two or three defect tables in one piece, 3 with a defect table in the summary piece |
| Added page break | 0 failures | Empty pieces are skipped. They are common, usually the break before `SUBSTATION CONDITION` |
| Heading split or retyped | 0 | See C15 |
| Template with a break inside it | 9 | The break sits inside a defect table. Harmless in the one report compared (C16) |
| Count mismatch | 42 | See C6 for why |
| Other | 3 | 2 reports with CBM pages naming another substation, which COM rejects too. 1 Strict Open XML file |

Defect-table rule: 38 count mismatches, the same 2 foreign-page reports, and the Strict Open XML file. The 27 missing-break reports and the 9 template-break reports all pass.

### COM comparison

Each COM run sliced a temp copy of the report with `WordComDocumentSlicer.slice_sections`. A slice matches when its whitespace-free text hash and its table, image and object counts all match. The front-page text is compared after the slicer's `QUICK SCANNING REPORT` to `FULL SCANNING REPORT` swap.

| Report | Why it was picked | COM seconds | Ticket rule | Defect-table rule |
|--------|-------------------|-------------|-------------|-------------------|
| Talapia | benchmark | 29.3 | all same, 3 of 3 CBM | all same, 3 of 3 CBM |
| Sentosa | benchmark | 10.4 | all same, no CBM | all same, no CBM |
| 094 | benchmark | 33.6 | all same, 4 of 4 CBM | all same, 4 of 4 CBM |
| APMM | benchmark | 15.4 | all same, no CBM | all same, no CBM |
| PE157 | benchmark | 10.2 | all same, no CBM | all same, no CBM |
| Kuala Lipis | two defect tables in one piece | 25.3 | 2 of 4 CBM | all same, 4 of 4 CBM |
| Astana View | two defect tables in one piece | 23.7 | 0 of 2 CBM | all same, 2 of 2 CBM |
| Lian Fatt | break inside a defect table | 28.2 | all same, 3 of 3 CBM | all same, 3 of 3 CBM |
| Telanok | defect table in the summary piece | 35.4 | 0 of 4 CBM, VI summary differs | all same, 4 of 4 CBM |

COM seconds are the final run's, from `evidence/com_compare.json`. Each covers one `slice_sections` call, including Word start and quit.

### What the slicer spec would need

- The CBM bound is the defect table, not the page break.
- The Master count can't be a fallback trigger, because operators add CBM pages (C7) and the 33kV Master can be empty (C6). Log a mismatch as a Run Record warning.
- Fall back to COM, with a warning, for a Strict Open XML file, a missing `SUBSTATION CONDITION` or `NORMAL/DEFECT STICKER`, or a non-summary table in the summary area.
- Reject a CBM page whose header names another substation, as COM does.

## Disputed

None. One Path.

## Open questions

1. Are the extra CBM pages operator edits (C8)? If they are, the Master count is a warning at most.
2. Were the missing breaks deleted by operators, or lost in the compile (C14)? It changes nothing in the rule, but a compile fault would be worth its own ticket.
3. Is a break inside a defect table harmless in the other 8 reports (C16)?

## How to reproduce

From a clean worktree of the Integration Branch, with Word and Excel closed:

```
uv run --frozen python -W ignore docs/research/230-xml-slice-bounds/evidence/bounds.py \
    --config <path to .cli_config.json> --out <temp dir> --com \
    --com-extra "lipis=19. PMU KUALA LIPIS" "astana=080. ASTANA VIEW" \
                "lianfatt=125. LIAN FATT" "telanok=26. MINI PPU TELANOK" \
    --write-evidence
```

Leave out `--com` to skip Word. `--write-evidence` copies the summaries next to the script, with each CBM page named by kind instead of its D37 file name. The script writes only to `--out`, and checks that nothing under the project folders changed.

## Live data read

All 401 Quick Reports, with bytes and SHA-256, are in `evidence/live_data_read.tsv`. `<BASE>` is each project's base path. The script also read the QR03 CBA and QR03 VI Masters and the testsheets through `FullReportWorkflow.discover_packages`. The nine reports compared with COM:

| Path | File | Read on |
|------|------|---------|
| `<BASE>/QUICK REPORT/RAUB/01. AUGUST/04-08-2026/` | `005. TALAPIA (IR+VI).docx` | 2026-11-12 |
| `<BASE>/QUICK REPORT/RAUB/01. AUGUST/04-08-2026/` | `007. CS RESTORAN SENTOSA (VI).docx` | 2026-11-12 |
| `<BASE>/QUICK REPORT/CAMERON HIGHLAND/01. AUGUST/17-08-2026/` | `094. CHAN YIM SOM (IR+VI).docx` | 2026-11-12 |
| `<BASE>/QUICK REPORT/GEBENG/01. OCTOBER/07-10-2026/` | `01. PPU APMM 33-11kV (VI).docx` | 2026-11-12 |
| `<BASE>/QUICK REPORT/KUANTAN/01. AUGUST/25-08-2026/` | `157. PERPUSTAKAAN AWAM(VCB) (VI).docx` | 2026-11-12 |
| `<BASE>/QUICK REPORT/KUALA LIPIS/01. OCTOBER/14-10-2026/` | `19. PMU KUALA LIPIS 132-33kV (US+VI).docx` | 2026-11-12 |
| `<BASE>/QUICK REPORT/KUANTAN/01. AUGUST/14-08-2026/` | `080. ASTANA VIEW (IR+VI).docx` | 2026-11-12 |
| `<BASE>/QUICK REPORT/CAMERON HIGHLAND/01. AUGUST/20-08-2026/` | `125. LIAN FATT (IR+VI).docx` | 2026-11-12 |
| `<BASE>/QUICK REPORT/CAMERON HIGHLAND/01. OCTOBER/16-10-2026/` | `26. MINI PPU TELANOK 33-11kV (US+VI).docx` | 2026-11-12 |

Bytes and SHA-256 for each are in the TSV rows of the same path.

## Change log

- 2026-11-12: first version (Claude Code).
