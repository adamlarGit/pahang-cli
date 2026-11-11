---
ticket: 223
type: research
map: 221
status: open
updated: 2026-11-11
agent: Claude Code, claude-fable-5-2
---
# Can FLIR controls be joined at the XML level without crosstalk?

## Verdict

A join looks feasible, with one known gap in how it has been done so far.

The package side is ordinary OOXML work with a known list of renames and renumbers (C1, C9). The risk sits inside each viewer's binary, which carries three identities: an object UUID, an SDK UUID and a Word bookmark per measurement field (C2). The suspected cause of image crosstalk is two viewers sharing one SDK UUID and attaching to the same live SDK (C6). The #225 prototype gave every viewer fresh UUIDs, and the owner then saw every viewer load with no crosstalk in two real Parts (C7).

The gap is the Word bookmark. It is stored twice in the binary: as the `_Fd` name and as a number inside a compressed archive. Word's own compile keeps the two equal. The XML join changes only the name (C3, C4), and it can pick a name too large to be stored as that number (C5). This is the leading explanation for the table values that stop following the spots in #225, and it has not been tested (C8).

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | A viewer is a `w:control` that reaches `activeXN.xml` and then `activeXN.bin` through two relationships, with a separate preview image and a name binding from body fields to `settings.xml`. | Tested | `path-static-cfb.md` C2, C4. `path-rekey-join.md` C1 agrees. |
| C2 | Each viewer binary holds an object UUID and an SDK UUID, and each of its fields holds its own object UUID, the viewer's SDK UUID and a Word bookmark. | Tested | `path-static-cfb.md` C9, C10, C11 |
| C3 | In the committed `swg-panel.docx` template and in a COM-compiled Part, every `_Fd` name equals the number stored in its field archive: 4 of 4 and 28 of 28 fields. Word's compile gives each viewer new values and keeps them equal. | Tested | `evidence/answer/check_bookmark_sync.py`, `evidence/answer/check-bookmark-sync-2026-11-11.log` |
| C4 | In XML-joined files the rekeyed `_Fd` names differ from the stored numbers: 4 of 8 fields in the two-panel file and 28 of 28 in the #225 joined Part 03. All seven viewers of joined Part 03 hold the same four stored numbers. | Tested | same script and log |
| C5 | The rekey keeps the digit count of the old name, so it produces names above 4,294,967,295 that cannot be stored as a uint32, such as `_Fd9036535755` in joined Part 03. | Tested | same log; `path-rekey-join.md` open question 3 |
| C6 | Image crosstalk comes from two viewers that share an SDK UUID attaching to one live SDK. | Assumed | `path-static-cfb.md` C16 (Read) and C17 (Assumed). Supported by the first-open flicker reported in `docs/research/225-flir-xml-join-prototype/README.md` C15. Settled by joining two copies of one viewer with the SDK UUID unchanged and editing one. |
| C7 | With fresh UUIDs on every viewer, every viewer in two real joined Parts loads and edits, with no crosstalk after save, close and reopen. | Owner-confirmed | `docs/research/225-flir-xml-join-prototype/README.md` C11, C12 |
| C8 | The mismatch of C4 is why moving a spot in a joined file does not update the Word table values. | Assumed | none direct. It fits what is known: the seven Part 03 sources have equal names and numbers and their fields follow the spots, and the joined file has neither (`docs/research/225-flir-xml-join-prototype/README.md` C16, C19, C20). Settled by writing the new number into the field archive of one viewer and repeating the owner's check. |
| C9 | Replacing the ASCII UUIDs and `_Fd` names with same-length values leaves the binary a valid OLE file of unchanged size. | Tested | `path-rekey-join.md` C6 |
| C10 | FLIR's installed libraries expose no public call that clones a viewer or gives it new identities. | Read | `path-flir-tools.md` C2 to C5 |

## Detail

### What the ticket asked for

| Asked | Where |
|---|---|
| The viewer's part and identifier diagram | `path-static-cfb.md`, "One viewer, with its identifiers" and "Inside `Contents`" |
| Must rename, must renumber, must copy unchanged | `path-static-cfb.md`, "Rename, renumber, copy" |
| The suspected cause of FLIR Crosstalk | C6 for image crosstalk. C4 and C8 for measurement values. |
| A verdict | A join looks feasible. |

### The three identities, and what each attempt changed

| Identity | Stored as | Word COM compile | XML join in #225 |
|---|---|---|---|
| Object UUID of the viewer | ASCII, top of `Contents` | unique per viewer (7 of 7) | unique per viewer (7 of 7) |
| SDK UUID | ASCII, top of `Contents` and in every field | unique per viewer (7 of 7) | unique per viewer (7 of 7) |
| Object UUID of each field | ASCII, in the field record | not checked | unique (28 of 28) |
| Word bookmark, name | ASCII `_Fd` name in the binary, body fields and `settings.xml` | unique (28 of 28) | unique (28 of 28) |
| Word bookmark, number | uint32 inside each compressed field archive | equal to the name (28 of 28) | unchanged: the same four numbers in all seven viewers |

The counts are for Part 03, from `evidence/answer/check-bookmark-sync-2026-11-11.log` and `docs/research/225-flir-xml-join-prototype/evidence/validate-outputs-2026-11-11.log`. The earlier two-panel file of `path-rekey-join.md` leaves both viewers with one object UUID.

The two Paths use different words for the first two rows. `path-rekey-join.md` says session GUID and instance GUID. `path-static-cfb.md` says object UUID and SDK UUID, taken from the native code. This file uses the second pair.

### What closing the gap takes

For each field: inflate the archive, write the new number at the bookmark offset, deflate, then update the KENT sizes and the R8 nested-object length. The deflated size will usually change, so the `Contents` stream and the CFB allocation change with it. The equal-length shortcut of `path-rekey-join.md` no longer applies to that step. New names must also stay within uint32.

## Disputed

| Topic | `path-static-cfb.md` | `path-rekey-join.md` | State |
|---|---|---|---|
| Why nine Talapia field names repeat | C7: they are repeated references in the TX1 and TX2 tables, and none of the nine is in any binary. | C13: they belong to non-defect or static pages on viewers 11, 16, 18 and 23. | Not settled. C7 rests on the document XML and C13 has no evidence. Both agree that viewers 1, 2, 11, 16, 18 and 23 carry no field records (C12 in each). Whether those fields update has not been checked in Word. |
| Whether separate binaries isolate image data | C16, C17: viewers look up their SDK by GUID and can attach to one that is already live. | C14: image data in separate binaries is fully isolated. | Leans to static-cfb. The #225 flicker with an un-rekeyed first viewer fits it, though that report is itself Assumed. |
| Whether FLIR's tools can replace Word here | `path-flir-tools.md` C11 to C14: possible building blocks, nothing demonstrated, a 32-bit worker untested. | C16, C17: Atlas can replace Word for thermal data, and the wizard creates fresh single-page files. | Not settled. Every claim on both sides is Assumed. |
| Offset of the image block in `swg-panel.docx` | 2,097 | 2,089 in the original write-up | Settled for 2,097. The rekey-join script itself slices from 2,097. |

## Open questions

1. Does matching the stored number to the new name restore the measurement linkage? (C8)
2. How long does the SDK registry live, and is it per document or per Word process? This decides whether fresh SDK UUIDs are always enough.
3. Do the Talapia TX1 and TX2 shared fields update correctly, before and after a join?
4. Does the join hold for record types not seen in these ten documents (`TAG_R8_TBL`, `TAG_R8_STB`)?
5. The constraints for the #231 slice proof are in `evidence/static-cfb/original/flir-activex-xml-join.md` and were not carried into a Path claim.

## How to reproduce

The check behind C3 to C5 reads any docx and writes nothing:

```
python docs/research/223-flir-xml-join/evidence/answer/check_bookmark_sync.py <docx> [<docx> ...]
```

The log was captured on four files: the committed `swg-panel.docx`, `evidence/rekey-join/joined_swg_panels_proof.docx`, and the COM-compiled and XML-joined Part 03 listed below. Each Path file has its own commands.

## Live data read

`<BASE>` is the project base path of the #232 run. `<OLD>` was `scratch/` in the old #225 prototype worktree, which is now removed. On 2026-11-11 its `output/` and `sources_part03/` files were moved unchanged to `scratch/234-flir-field-link/` in the Integration Branch worktree, a folder git ignores.

| Path | File | Bytes | SHA-256 | Read on |
|------|------|-------|---------|---------|
| `<BASE>/FULL REPORT/GEBENG/01. OCTOBER/07-10-2026/` | `01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE).docx` | 2472593 | `97c01c3b1353bfbd1b764399001616f538ffa8ee8b9e07fdd66be20a0c309b39` | 2026-11-11 |
| `<OLD>/output/` | `01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE) [XML-JOINED].docx` | 2278628 | `f45e035bf44fb11a958e2ad78fb122fb63c03ca78d007ee031cd8c0e0a25dce0` | 2026-11-11 |

## Change log

- 2026-11-11: the joined Part 03 listed under Live data read moved to `scratch/234-flir-field-link/` (Claude Code).
- 2026-11-11: C8 now cites the owner's check of the seven Part 03 sources. Its label stays Assumed until the fix is tried (Claude Code).
- 2026-11-11: first version, written from the three Path files after converting the Codex and Antigravity work to this layout. The ten ticket comments are saved in `evidence/answer/ticket-comments.md`. C3 to C5 are new findings from a check written for this answer (Claude Code).
