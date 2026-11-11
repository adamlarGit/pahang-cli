---
ticket: 223
type: research
map: 221
path: rekey-join
status: open
updated: 2026-11-11
agent: Antigravity, Gemini 3.8 Flash (original work); Claude Code, claude-fable-5-2 (conversion)
---
# Can a viewer's identifiers be replaced in place, and does a join built on that produce a valid package?

## Question for this Path

Can the GUIDs and `_Fd` names inside a viewer binary be swapped for fresh values without breaking the binary, and can two or three copies of one template then be joined into a well-formed docx without Word?

## Verdict

Yes for the structure, and unchecked for behaviour. Replacing the ASCII GUIDs and `_Fd` names with values of the same length leaves the binary a valid 307,200-byte OLE file whose image block still inflates (C6). A join engine built on that produces two-panel and three-panel files with unique control names, relationship IDs and field names (C8, C9). Nobody opened those two files in Word, so repair prompts and crosstalk were never checked for them (C10).

The original write-up opened with "Can't tell without a prototype" and closed with "Validated". Only the structural part was validated.

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | A viewer persists through `rId8`, `activeX1.xml`, `activeX1.bin` and its `Contents` stream, with field values held in `settings.xml`. | Read | `templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx` package XML. Agrees with `path-static-cfb.md` C2. |
| C2 | `activeX1.bin` is a valid OLE file with root CLSID `C5F5764B-B932-4F33-8BF3-9941F22FAE18`. | Tested | `evidence/rekey-join/test_patch_measurement_ids.py`, `evidence/rekey-join/test_patch_measurement_ids-2026-11-11.log` |
| C3 | Each of the four measurement GUIDs of `swg-panel.docx` occurs once as ASCII in `Contents` (offsets 146, 613, 1070, 1526), never in binary form, and never inside the image block. | Tested | `evidence/rekey-join/search_measurement_guids.py`, `evidence/rekey-join/search_measurement_guids-2026-11-11.log` |
| C4 | Each field record names its tool. In `swg-panel.docx` they are `Sp1.Max. Temperature`, `Sp1.Temperature`, `Sp2.Temperature` and `Dt1`. | Tested | `evidence/rekey-join/scan_all_template_measurements.py`, `evidence/rekey-join/scan_all_template_measurements-2026-11-11.log` |
| C5 | The image block of `swg-panel.docx` inflates to 625,696 bytes. | Tested | `evidence/rekey-join/test_patch_measurement_ids-2026-11-11.log` |
| C6 | Replacing the second top GUID, the four measurement GUIDs and the four `_Fd` names with same-length values leaves the binary 307,200 bytes, a valid OLE file, with the image block still inflating to 625,696 bytes. | Tested | `evidence/rekey-join/test_full_rekey.py`, `evidence/rekey-join/test_patch_measurement_ids.py` and their logs |
| C7 | After that replacement, every compressed field archive still inflates. | Assumed | none. The scripts inflate only the image block. Settled by inflating each field archive of a patched binary. |
| C8 | Joining `swg-panel.docx` with itself gives a docx with two controls that differ in name, shape ID and relationship ID, two 307,200-byte binaries with different second GUIDs, and eight unique fields, all declared in `settings.xml`. | Tested | `evidence/rekey-join/xml_join_flir_engine.py`, `evidence/rekey-join/joined_swg_panels_proof.docx`, `evidence/rekey-join/verify_joined_proof.py`, `evidence/rekey-join/verify_joined_proof-2026-11-11.log` |
| C9 | Joining the template three times gives a 1,179,960-byte docx. | Tested | `evidence/rekey-join/test_multi_join.py`, `evidence/rekey-join/joined_3_panels_proof.docx` |
| C10 | Word opens the two joined files with no repair prompt, no image crosstalk and no measurement crosstalk. | Assumed | none. The write-up called them "ready for human verification". Settled by opening both in Word and editing one viewer. |
| C11 | The three-panel join takes 0.15 s and yields 12 unique `_Fd` names. | Assumed | none. Quoted in the write-up. No script times the join or checks the three-panel file. |
| C12 | In the Talapia Full Report, viewers 1, 2, 11, 16, 18 and 23 hold no `TAG_R8_FLD` and no `_Fd` string. | Tested | `evidence/rekey-join/check_all_bins.py`, `evidence/rekey-join/check_all_bins-2026-11-11.log` |
| C13 | The nine repeated Talapia names belong to non-defect or static pages on viewers 11, 16, 18 and 23. | Assumed | none. Disputed by `path-static-cfb.md` C7. |
| C14 | Image data in separate `.bin` parts is fully isolated between viewers. | Assumed | none. The stored bytes are separate (C3). The runtime behaviour was not tested, and `path-static-cfb.md` C16 describes a way viewers can share state. |
| C15 | `Flir.Atlas.Image.dll` exposes `ThermalImageFile.Open`, `GetValueAt`, `Measurements`, `PaletteManager` and `RenderTo`. | Read | Reflection listing by `evidence/rekey-join/inspect_atlas.ps1`. Output not kept. Agrees with `path-flir-tools.md` C7. |
| C16 | The Atlas SDK can read spot and delta temperatures with no Word, replacing Word for thermal data. | Assumed | none. No Atlas method was called. |
| C17 | `WizardClassLibrary.WordApp.CreateReport` produces single-page docx files with fresh viewer binaries. | Assumed | none. Inferred from the method name. |
| C18 | `IMeasurement` has 72 COM methods. | Read | Type library, counted by `evidence/rekey-join/check_all_typelibs.py`. Output not kept. |
| C19 | A pure XML join is unaffected by the `Saved = False` regression of ADR 0002. | Assumed | none. Reasoned from the join not calling Word. |
| C20 | Slicing a Part in XML is feasible. | Assumed | none. No slicing code was written. |

## Detail

### Naming

This Path calls the two top GUIDs of a viewer the session GUID and the instance GUID. `path-static-cfb.md` identifies them from the native code as the object UUID and the SDK UUID. The measurement GUID here is the object UUID of a nested field there.

### What the rekey replaces

`test_full_rekey.py` and the join engine replace ASCII strings of equal length across the raw binary:

| Replaced | With |
|---|---|
| The second top GUID | A new random GUID |
| The first GUID of each field record | A new random GUID |
| Each `_Fd` name | A new name with the same number of digits |

Equal length keeps every offset where it was, so no length field, zlib stream or CFB sector has to change. The uint32 copy of the `_Fd` number inside each compressed field archive (`path-static-cfb.md` C11) is not ASCII and is not replaced.

In the two-panel file the first copy keeps the template's GUIDs and `_Fd` names, and only the second copy is rekeyed (`verify_joined_proof-2026-11-11.log`).

### Corrections to the original write-up

- It places the image block at offset 2,089. Its own script slices from 2,097, which is also the offset in `path-static-cfb.md`.
- Its "upper bound 1,400,256 bytes" has no source in any script or output.
- Its "file size 307,200" is the size of the binary, and that size is specific to this template. Talapia binaries range from 871,936 to 1,186,816 bytes (`check_all_bins-2026-11-11.log`).

## Open questions

1. Do the two joined files open cleanly in Word, and do their viewers stay independent? (C10)
2. Does a viewer still update its Word fields once its `_Fd` names no longer match the numbers stored in its field archives?
3. A new `_Fd` name keeps the digit count of the old one, so a ten-digit name can come out above 4,294,967,295. `test_full_rekey-2026-11-11.log` shows `_Fd9901000000`. Can FLIR store such a bookmark?

## How to reproduce

From the repo root, with `lxml` and `olefile` installed:

```
python docs/research/223-flir-xml-join/evidence/rekey-join/test_full_rekey.py
python docs/research/223-flir-xml-join/evidence/rekey-join/test_patch_measurement_ids.py
python docs/research/223-flir-xml-join/evidence/rekey-join/search_measurement_guids.py
python docs/research/223-flir-xml-join/evidence/rekey-join/scan_all_template_measurements.py
```

These four read the committed templates and write nothing. The logs in this folder were captured against the template at commit 1137b92.

`xml_join_flir_engine.py`, `test_multi_join.py`, `verify_joined_proof.py` and the Talapia scripts hold paths under `.scratch/`. Edit them before running. The engine and `test_multi_join.py` write a new joined file with new random GUIDs each time.

## Live data read

| Path | File | Bytes | SHA-256 | Read on |
|------|------|-------|---------|---------|
| `<BASE>/FULL REPORT/RAUB/01. AUGUST/04-08-2026/` | `005. TALAPIA (IR+VI).docx` | 41260522 | `eca3aa5c26db1ca5ef1bacb87baa22b10475ed2aff13ca7551010231a4e7523f` | 2026-11-11 |

The scripts read a copy of it at `.scratch/prod-proof/data/talapia.docx`. That it came from the path above rests on the matching hash in `evidence/static-cfb/flir-activex-xml-join.inventory.json`.

## Change log

- 2026-11-11: converted from the Antigravity write-up, kept unchanged in `evidence/rekey-join/original/`, and its scripts from `.scratch/`. Six read-only scripts were rerun to capture logs, since no output of the original runs was kept. Absolute wording in the original ("100% isolated", "completely unaffected", "100% feasible") is relabelled Assumed in C14, C19 and C20 (Claude Code).
