---
ticket: 225
type: prototype
map: 221
status: open
updated: 2026-11-11
agent: Antigravity (original work, named by the owner; its comments were unsigned); Claude Code, claude-fable-5-2 (conversion)
---
# Can two real Full Report Parts with FLIR viewers be joined by hand-built XML, without Word?

## Verdict

Three of the four pass conditions are met and one is met in part. The joined files also have a field defect outside the four conditions.

| # | Pass condition | Result |
|---|----------------|--------|
| 1 | Word opens the joined file with no repair prompt | Pass (C10) |
| 2 | Every FLIR viewer loads and can be edited | Pass (C11) |
| 3 | No FLIR Crosstalk, including after save, close and reopen | Pass (C12) |
| 4 | Stage 2 disconnected export matches the COM-compiled file | Part met: Part 03 only, by a plain Word PDF export (C13, C14) |

The join itself takes 0.50 s for Part 03 and 1.65 s for Part 32, against 46.52 s and 173.59 s for the COM compile (C6, C7). Word then opens the joined file more slowly than the COM-compiled one: 15.42 s against 11.17 s for Part 03, and 129.02 s against 45.76 s for Part 32 (C8). The owner found one defect in both joined files: the `Sp1`, `Sp2`, `Ar1` and `Dt` fields do not link properly to the IR viewer (C16). A likely cause is found and untested (C18).

ADR 0002's ban is not ready to lift on this evidence. Condition 4 and the field linkage need closing first.

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | The engine joins the 7 Part 03 sources into one 2,278,628-byte docx without Word. | Tested | `evidence/run_prototype_225.py`; output hash in `evidence/live-data-sha256.txt` |
| C2 | The engine joins the 28 Part 32 sources (rendered 201 to 228, 26 viewers) into one 16,562,503-byte docx without Word. | Tested | `evidence/run_prototype_225.py`; output hash in `evidence/live-data-sha256.txt` |
| C3 | Joined Part 03 holds 7 controls and 7 ActiveX binaries, with no duplicate control name, shape ID, relationship ID, Instance GUID (7), Measurement GUID (28) or `_Fd` name (28). Every body `_Fd` field is in a binary and in `settings.xml`. | Tested | `evidence/validate_outputs.py`, `evidence/validate-outputs-2026-11-11.log` |
| C4 | Joined Part 32 holds 26 controls and 26 ActiveX binaries, with no duplicate control name, shape ID, relationship ID, Instance GUID (26), Measurement GUID (101) or `_Fd` name (101). Every body `_Fd` field is in a binary and in `settings.xml`. | Tested | `evidence/validate_outputs.py`, `evidence/validate-outputs-2026-11-11.log` |
| C5 | Page breaks and sections match the COM compile: 6 breaks and 1 `sectPr` for Part 03, 34 and 1 for Part 32, in both versions. | Tested | `evidence/validate-outputs-2026-11-11.log`, `evidence/inspect_com_parts.py`, `evidence/inspect-com-parts-2026-11-11.log` |
| C6 | The XML join takes 0.50 s for Part 03 and 1.65 s for Part 32. An earlier run at commit b075311 gave 0.4293 s and 1.6106 s. | Tested | `evidence/run_prototype_225.py`; console output quoted in `evidence/ticket-comments.md`, comments 4 and 5 |
| C7 | The COM compile of the same Parts takes 46.52 s and 173.59 s. | Read | Constants in `evidence/run_prototype_225.py` lines 148 and 178, which cite the #232 baseline. Not checked against #232 here. |
| C8 | Word opens the joined file more slowly than the COM-compiled one: Part 03 15.42 s against 11.17 s, Part 32 129.02 s against 45.76 s. | Tested | `evidence/test_word_open_probe.py`; console output quoted in `evidence/ticket-comments.md`, comments 4 and 5 |
| C9 | Word reports the same page counts for both versions (7 and 36) and one paragraph fewer in the joined file (1665 against 1666, 6699 against 6700). | Tested | `evidence/test_word_open_probe.py`; console output quoted in `evidence/ticket-comments.md`, comment 4 |
| C10 | Word opens both joined files with no repair prompt. | Owner-confirmed | The owner's answer to the converting agent on 2026-11-11, from opening both files by hand in Word. The owner's own comment on #225 is still to be posted and linked here. The automated probe cannot show this, because it sets `DisplayAlerts = 0` in its own Word instance. |
| C11 | Every FLIR viewer in both joined files loads and can be edited, changed and saved. | Owner-confirmed | The owner's answer to the converting agent on 2026-11-11. The owner's own comment on #225 is still to be posted and linked here. |
| C12 | No FLIR Crosstalk in either joined file, including after save, close and reopen. | Owner-confirmed | The owner's answer to the converting agent on 2026-11-11. The owner's own comment on #225 is still to be posted and linked here. |
| C13 | Word's PDF export of joined Part 03 and of COM-compiled Part 03 both give 7 pages and 26 embedded images (418,932 and 418,972 bytes). | Tested | `evidence/test_pdf_export_compare.py`; both PDFs hashed in `evidence/live-data-sha256.txt` |
| C14 | The joined files match the COM-compiled ones through the Stage 2 disconnected export of ADR 0011, compared with the #212 tools. | Assumed | none. C13 used `ExportAsFixedFormat` on Part 03 and counted pages and images. Settled by running the #212 comparison on both Parts through the Stage 2 export. |
| C15 | Leaving the first source un-rekeyed caused a first-open crosstalk flicker when both Parts were open in one Word session, because it kept the template Instance GUID `56a0ddda-5a37-4fd2-bb25-c99b89db71ba`. Rekeying it removed the flicker. | Assumed | none. Reported in `evidence/ticket-comments.md`, comment 5, with no output kept. Settled by joining without base rekeying and opening both files together. |
| C16 | In both joined files the `Sp1`, `Sp2`, `Ar1` and `Dt` fields do not link properly to the IR viewer. Comment 5 describes it as the table values not following a moved spot. | Owner-confirmed | The owner's answer to the converting agent on 2026-11-11. The owner's own comment on #225 is still to be posted and linked here. Comment 5 is in `evidence/ticket-comments.md`. |
| C17 | The engine rekeys every source, the first included: fresh Session and Instance GUIDs, fresh Measurement GUIDs and fresh `_Fd` names, written to the binary, `document.xml` and `settings.xml` together. | Read | `evidence/prototype_join_engine.py`, `rekey_activex_bin` (lines 49 to 107) and `join_multiple_documents_in_xml` (from line 109) |
| C18 | In joined Part 03, no `_Fd` name equals the number stored in its field archive (0 of 28), and all seven viewers hold the same four stored numbers. In the COM-compiled Part 03 they are equal in 28 of 28 fields. | Tested | `docs/research/223-flir-xml-join/evidence/answer/check_bookmark_sync.py`, `docs/research/223-flir-xml-join/evidence/answer/check-bookmark-sync-2026-11-11.log` |

## Detail

### Inputs

| Part | Sources | Viewers | Where the sources came from |
|------|---------|---------|-----------------------------|
| Part 03, Panel 1 (33kV SPARE) | 7 | 7 | `sources_part03/015` to `021` in the old prototype worktree |
| Part 32, TX and Condition | 28 | 26 | `rendered/201` to `228` of the #232 run |

The ticket first asked for the Talapia Part with 27 controls. Comment 3 replaced it with these two Parts, which are the real compile inputs of the #232 run.

### What the engine does

As described in comment 5 and visible in `evidence/prototype_join_engine.py`:

1. Adds the `bin` default and an override for every appended `activeX{N}.xml` to `[Content_Types].xml`.
2. Keeps singleton parts (styles, settings, web settings, font table, theme, numbering) from the first source and remaps the other sources' relationships to them.
3. Deduplicates repeated media by SHA-256.
4. Allocates VML shape IDs in sequence from `_x0000_i1025` and renumbers DrawingML `docPr` IDs.
5. Names controls the way Word does, by appending a counter with no underscore.
6. Rekeys every `activeX{N}.bin` as in C17.

Commit 4c5bed0 added the base-part rekeying, the shape ID floor and the control naming. It also loosened the validator's `_Fd` check from "body fields equal binary fields" to "body fields are a subset of binary fields". On the current outputs the two counts are equal (28 and 28, 101 and 101), so the looser check hides nothing here.

### Timings

| Measure | COM compile | XML join | Source |
|---------|-------------|----------|--------|
| Part 03 join | 46.52 s | 0.50 s | C6, C7 |
| Part 32 join | 173.59 s | 1.65 s | C6, C7 |
| Part 03 Word open | 11.17 s | 15.42 s | C8 |
| Part 32 Word open | 45.76 s | 129.02 s | C8 |
| Part 03 file size | 2,472,593 bytes | 2,278,628 bytes | `evidence/live-data-sha256.txt` |
| Part 32 file size | 17,778,631 bytes | 16,562,503 bytes | `evidence/live-data-sha256.txt` |

For Part 32 the join saves 171.9 s and the slower open costs 83.3 s each time Word opens the file.

### Numbers that differ between comments 4 and 5

| Item | Comment 4 (b075311) | Comment 5 (4c5bed0) | On disk |
|------|---------------------|---------------------|---------|
| Part 03 join time | 0.4293 s | 0.50 s | not kept |
| Part 32 join time | 1.6106 s | 1.65 s | not kept |
| Part 03 output | 2,246,976 bytes | 2,278,628 bytes | 2,278,628 bytes |
| Part 32 output | 16,560,528 bytes | 16,562,503 bytes | 16,562,503 bytes |

The comment 4 outputs were overwritten by the comment 5 run. Every claim above uses the comment 5 figures.

## Open questions

1. **Field linkage in the COM-compiled file.** Do the same four fields link properly there? That check is the control for C16 and has not been reported.
2. **Condition 4.** The comparison the ticket asks for has not been run, and Part 32 has not been compared at all. (C14)
3. **Slower open.** Why does Word open the joined file more slowly, and does the extra time cancel the saving once the Stage 2 export opens the file? Comment 5 suggests 26 in-process ActiveX servers, with no evidence.
4. **Measurement linkage.** Why do the table values not follow the spots (C16)? The leading explanation is C18: the rekey changes each `_Fd` name and leaves the number stored in the compressed field archive, so the two no longer match. See `docs/research/223-flir-xml-join/README.md` C3 to C5 and C8. It is untested. Comment 5 lists four other untested leads: the FLIR Word add-in may not attach its listeners to controls it did not paste; the compressed `TAG_R8_FLD` payload may hold an ID, checksum or length that the rekey left stale; FLIR Tools+ may write to `ActiveDocument.Variables` and need a `Fields.Update`; Word's copy and paste may write binding entries that the join omits.
5. **Part 32 source count.** The run joins 28 sources. Comment 3 and the #221 map say 35.
6. **Part 03 sources.** The seven files in `sources_part03` are about 860 KB each, while `rendered/015` to `021` of the #232 run are about 403 KB each. What produced the larger set is not recorded.
7. **Document variables.** The joined files carry 3,888 and 3,904 `w:docVar` entries for 28 and 101 fields in use.
8. **Baseline source.** The script cites #232 for the COM times. Comments 2 and 3 cite #224.

## How to reproduce

The scripts hold absolute paths to the old prototype worktree and to the #232 run folder. Edit those paths first. The #232 run folder is in the user temp directory and may be gone.

```
python docs/research/225-flir-xml-join-prototype/evidence/run_prototype_225.py
python docs/research/225-flir-xml-join-prototype/evidence/validate_outputs.py <joined Part 03> <joined Part 32>
python docs/research/225-flir-xml-join-prototype/evidence/inspect_com_parts.py
python docs/research/225-flir-xml-join-prototype/evidence/test_word_open_probe.py
python docs/research/225-flir-xml-join-prototype/evidence/test_pdf_export_compare.py
```

- `run_prototype_225.py` needs `lxml` and `olefile`. It rewrites both joined files with new GUIDs, so the files the owner checked in Word are replaced.
- `validate_outputs.py` and `inspect_com_parts.py` only read.
- The last two need Word. `test_pdf_export_compare.py` also needs PyMuPDF.

## Live data read

`<BASE>` is the project base path of the #232 run. `<OLD>` is `scratch/` in the old prototype worktree. Sizes and SHA-256 for all 41 files are in `evidence/live-data-sha256.txt`.

| Path | File | Bytes | SHA-256 | Read on |
|------|------|-------|---------|---------|
| `<BASE>/.temp/full_report/001_PPU APMM 3311kV_07-10-2026/rendered/` | `201_*.docx` to `228_*.docx` (28 files) | 289,289 to 6,971,145 | in the manifest | 2026-11-11 |
| `<OLD>/sources_part03/` | `015_*.docx` to `021_*.docx` (7 files) | 859,806 to 862,572 | in the manifest | 2026-11-11 |
| `<BASE>/FULL REPORT/GEBENG/01. OCTOBER/07-10-2026/` | `01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE).docx` | 2472593 | `97c01c3b1353bfbd1b764399001616f538ffa8ee8b9e07fdd66be20a0c309b39` | 2026-11-11 |
| `<BASE>/FULL REPORT/GEBENG/01. OCTOBER/07-10-2026/` | `01. PPU APMM 3311kV - Part 32 - TX and Condition.docx` | 17778631 | `5623636a19fc3d0f7df1408480354639e0c2b91574aeaced0e3dd81374be592a` | 2026-11-11 |
| `<OLD>/output/` | `01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE) [XML-JOINED].docx` | 2278628 | `f45e035bf44fb11a958e2ad78fb122fb63c03ca78d007ee031cd8c0e0a25dce0` | 2026-11-11 |
| `<OLD>/output/` | `01. PPU APMM 3311kV - Part 32 - TX and Condition [XML-JOINED].docx` | 16562503 | `6c102342593271e5961a1d04078f5cb5e005e6752df2df19d540d693b16acc8f` | 2026-11-11 |
| `<OLD>/output/` | `part03_com.pdf` | 418972 | `671a800702c084e98526347ebc7dd53714c3e3c8426ea81f621643bc30086b7c` | 2026-11-11 |
| `<OLD>/output/` | `part03_xml.pdf` | 418932 | `585ae6835d8a85d13942add134e151f988e635e083be2d6198fae5c713a68a2a` | 2026-11-11 |

The two joined files are the ones the owner checked in Word. They exist only in the old prototype worktree.

## Change log

- 2026-11-11: C10 and C16 relabelled Owner-confirmed on the owner's answers. The owner named Antigravity as the agent behind the original work (Claude Code).
- 2026-11-11: converted to the Ticket Folder layout from the original prototype branch (commits b075311 and 4c5bed0, never on the Integration Branch) and the five ticket comments. The structural validator and `inspect_com_parts.py` were rerun read-only to capture logs. Console output of the original runs was never saved, so C6, C8 and C9 rest on the output quoted in the ticket comments (Claude Code).
