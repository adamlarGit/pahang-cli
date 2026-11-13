---
ticket: 235
type: research
map: 221
status: answered
updated: 2026-11-13
agent: Claude Code, claude-opus-5-5
---
# Can the IR table values be read from a saved FLIR image without Word?

## Verdict

Yes, under stated conditions, for the two FLIR cameras in use, the T640 and the T440. A short pure-Python reader, using numpy and Pillow from `uv.lock`, computes `Sp1`, `Sp2`, the area average and `Dt` from an image saved in FLIR Tools+ or by the Word viewer, with neither Word nor FLIR software running (C3, C10). It matches all 40 readings the owner took after an edit, to the digit (C3), and equals FLIR's own Atlas SDK on 86 of 87 values (C5). The one exception is a stretched ellipse, 0.009 °C below Atlas.

The file holds no readings. It holds the raw thermal plane, the calibration and the tool positions, and every value is computed from those (C1, C2). `Dt` is the first member minus the second, by tool number (C2).

A delivered report can be read with Word closed too. In the Talapia Full Report each viewer field keeps its last result as plain text, and computing from each viewer's stored state reproduces all 79 viewer-backed fields (C14, C15). Twenty table cells show values no viewer in the file holds, so nothing can check them (C18).

Atlas works as well, but it is the weaker route. It runs only in a 32-bit process, needs FLIR Tools installed, has no absolute `Dt`, cannot read a delivered report, and its licence for pipeline use is not settled (C11 to C13, C17). Its value to this ticket was as FLIR's reference: it is how the reader's atmosphere model and ellipse rules were found (C7).

The conditions on the pure reader:

- **The pipeline applies `abs()` to `Dt`.** The absolute tick is a Word formula option and is not saved into the image (C9). A delivered report's viewer does store it (C16).
- **Every report image is saved first**, even one nobody edited. A camera original's burned-in panel can be up to 3.5 °C away from FLIR's desktop figure on the T440 (C6).
- **Tools are matched by label** and the spot-to-spot difference is used (C20).
- **A stretched ellipse is close, not exact**, about 0.01 °C. Boxes, polygons and circles give FLIR's exact figure (C5).

Whether to drop the live viewer is the owner's decision and outside this ticket. ADR 0010 and the map constraint on live viewers are unchanged.

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | A saved image stores the raw thermal plane, the calibration and the tool positions, and no reading. An edit leaves the raw plane unchanged and rewrites the tool positions. | Tested | `path-file-read.md` C1, C2 |
| C2 | `Dt` is not stored. The difference tool references two members, and its value is the first minus the second, by tool number, from unrounded values. Atlas and FLIR Tools+ follow the same sign. | Tested | `path-file-read.md` C6, C7; `path-atlas-sdk.md` C7 |
| C3 | The pure-Python reader matches all 40 values the owner read after an edit, to one decimal: T640 FLIR Tools+ 16, T640 Word 8, T440 FLIR Tools+ 16. Of all 68 values, 62 match. | Tested | `path-file-read.md` C15 |
| C4 | Atlas gives the same result: all 40 after an edit, 62 of 68 overall, with the same six misses. | Tested | `path-atlas-sdk.md` C1, C2 |
| C5 | The reader's unrounded values equal Atlas's within 0.000003 °C on 85 of 87 values from 18 files, and within 0.00022 °C on 86. The stretched Word ellipse is 0.0090 °C below Atlas, because Atlas's pixel rule for a non-circular ellipse is not yet found. | Tested | `path-file-read.md` C13, C19, C23 |
| C6 | The six misses are all in the original column, which the owner read from the panel the camera burned into each picture. FLIR's desktop software does not reproduce the panel. On the T440 the panel's difference was up to 3.5 °C away. | Read | `path-file-read.md` C16 |
| C7 | The reader uses FLIR's one-path atmosphere model, found by comparing against Atlas's `GetValueFromSignal`. It equals Atlas's curve to 0.000001 °C from 11 to 61 °C. | Tested | `path-file-read.md` C14; `path-atlas-sdk.md` C5 |
| C8 | Image-level emissivity and distance changes are stored in CameraInfo, and per-tool parameters in the tool's header. The reader applies both and agrees with Atlas and with the owner. | Tested | `path-file-read.md` C20, C24; `path-atlas-sdk.md` C6 |
| C9 | The absolute-`Dt` tick is not saved in the image. Neither Atlas nor FLIR Tools+ has an absolute delta. The tick belongs to FLIR Word Reporting's formula field. | Tested | `path-file-read.md` C17; `path-atlas-sdk.md` C7 |
| C10 | The reader runs in the project's 64-bit Python with numpy and Pillow, already in `uv.lock`. It needs no FLIR install, no licence, no 32-bit process and no Word. | Tested | `path-file-read.md` C10 |
| C11 | Atlas runs only in a 32-bit process. Loading it from 64-bit PowerShell fails with `BadImageFormatException`. | Tested | `path-atlas-sdk.md` C3 |
| C12 | Atlas is the copy inside FLIR Tools, version 2.0.14266.1000. No separate SDK is installed. | Read | `path-atlas-sdk.md` C4 |
| C13 | A pipeline may call the Atlas copy inside FLIR Tools on the operators' machines. | Assumed | none. Settled by FLIR's licence terms for the Atlas SDK, or by FLIR (`path-atlas-sdk.md` C9). |
| C14 | In a delivered report every viewer field's last result is plain text: all 99 field uses in the Talapia Full Report are `DOCVARIABLE` fields whose cached result equals their `w:docVar`. | Tested | `path-file-read.md` C25 |
| C15 | Each viewer's stored state carries the camera calibration, the raw plane and the tools. Computing from it gives the cached result of all 79 viewer-backed fields to the digit. | Tested | `path-file-read.md` C26, C27 |
| C16 | A delivered report's viewer stores the absolute `Dt` as its delta formula, `abs([ana.Sp1.temp] - [ana.Sp2.temp])` in 18 deltas. | Tested | `path-file-read.md` C29 |
| C17 | The installed Atlas assemblies offer no way to read a viewer in a Word file. | Read | `path-atlas-sdk.md` C8 |
| C18 | Twenty table cells in the Talapia Full Report use eleven field names that belong to no viewer in the file. Their values are only in the `w:docVar`s and cannot be checked. | Tested | `path-file-read.md` C30 |
| C19 | A field's object, not its caption, says what it shows. Nineteen average fields carry a stale `Ar1.Max. Temperature` caption. | Tested | `path-file-read.md` C28 |
| C20 | Spots must be matched by label, since tool numbers and labels can disagree. A FLIR Tools+ edit can leave the camera's `Bx1Mx − Sp1` difference beside the new `Sp1 − Sp2`, and the owner's `Dt` is the spot-to-spot one. | Tested | `path-file-read.md` C7, C21 |

## Detail

### The six facts the ticket asked for

| # | Fact | Answer | Claims |
|---|------|--------|--------|
| 1 | What a saved image holds after an edit | Raw plane, calibration, tool positions and parameters. No readings. Moving a spot rewrites its coordinates. | C1, C8 |
| 2 | Can a program get the four values with no FLIR software | Yes, the pure-Python reader. | C3, C10 |
| 3 | Do they equal what Word shows | Yes, for every reading after an edit. Only the stretched ellipse is not exact against Atlas, and it still rounds to Word's figure. | C3, C5 |
| 4 | How `Dt` is obtained | Computed from two members. Absolute is a Word setting, applied by the pipeline for images and stored in a report's viewer. | C2, C9, C16 |
| 5 | Can the operator's picture be produced without the FLIR Tools+ window | The saved JPEG's main picture is the rendered thermal view with palette, scale and markers. | `path-file-read.md` C9 (Read) |
| 6 | What the route needs unattended | The pure reader: 64-bit Python, numpy and Pillow, nothing else. Atlas: 32-bit, FLIR Tools installed, licence unsettled. | C10 to C13 |

### Values read against values Word shows

The Word-edited rows, from `path-file-read.md` Detail, which also has the FLIR Tools+ and original rows for both cameras.

| Image | Save | | Sp1 | Sp2 | Area avg | Dt |
|---|---|---|---|---|---|---|
| FLIR0012 | Word, polygon, absolute `Dt` | computed | 37.8 | 38.2 | 36.4 | 0.4 |
| | | Word | 37.8 | 38.2 | 36.4 | 0.4 |
| FLIR0012 | Word, stretched ellipse, spot emissivity 0.8, absolute `Dt` | computed | 40.9 | 41.3 | 36.2 | 0.4 |
| | | Word | 40.9 | 41.3 | 36.2 | 0.4 |

| Set | Values | Match to one decimal |
|---|---|---|
| After an edit, T640 FLIR Tools+ | 16 | 16 |
| After an edit, T640 Word | 8 | 8 |
| After an edit, T440 FLIR Tools+ | 16 | 16 |
| Originals, camera panel | 28 | 22 |
| Talapia Full Report, viewer-backed fields | 79 | 79 |

### What the pipeline needs from the operator

1. Edit the spots and area in FLIR Tools+ or the Word viewer, and save the image (C1).
2. Save every image that goes into a report, even one with no changes (C6).
3. Keep the labels `Sp1`, `Sp2` and one area (C20).
4. Prefer a box, a polygon or a circular ellipse for the area. A stretched ellipse reads within about 0.01 °C (C5).

The pipeline itself applies `abs()` to `Dt` (C9).

### Route comparison

| | Pure-Python reader | Atlas SDK |
|---|---|---|
| Process | the project's 64-bit Python | 32-bit only |
| Install | none beyond `uv.lock` | FLIR Tools |
| Licence | none needed | not settled |
| Saved images | all 40 edited readings | all 40 edited readings |
| Stretched ellipse | 0.009 °C off | FLIR's own figure |
| Delivered report | yes | no |

## Disputed

None. The two Paths make no conflicting claim. These overlapping claims were compared and agree:

| Topic | file-read | atlas-sdk | Agreement |
|---|---|---|---|
| Reader against Atlas | C13: within 0.00022 °C on 86 of 87 | Verdict: within 0.000003 °C on 85 of 87 | Same log, `evidence/file-read/compare-to-atlas-2026-11-13d.log`. The two thresholds count the Word polygon differently. |
| Against the owner's readings | C15: 62 of 68, 40 of 40 after an edit | C2: 62 of 68, 40 of 40 after an edit | Same six misses in both logs |
| Sign and absolute `Dt` | C7, C17 | C7 | Both: by tool number, no absolute mode in the image |
| Runtime | C10: no licence, no 32-bit | C3, C9 | Both describe different routes |
| Delivered report | C25 to C27: readable | C8: not by Atlas | Both describe different routes |

## Open questions

1. May a pipeline call the Atlas copy inside FLIR Tools, and does Atlas need FLIR Tools+'s licence to be active? (`path-atlas-sdk.md` open questions 1 and 2)
2. Where did the 20 unbacked cells of the Talapia Full Report get their values? (`path-file-read.md` C30, open question 6)
3. What pixel rule does Atlas use for a stretched ellipse? (`path-file-read.md` open question 8)
4. Do delivered reports with ellipses, T440 images or per-tool parameters read the same way? Talapia has none of them. (`path-file-read.md` open question 6)
5. Which flag bit in a tool's header marks which local parameter, and how is an IR window handled? (`path-file-read.md` open question 2)
6. What is the 8-byte `0x29` record a FLIR Tools+ save adds? (`path-file-read.md` open question 5)
7. Why does the T440 panel's difference disagree with its own max and spot? It does not affect saved images. (`path-file-read.md` open question 7)

## How to reproduce

No command was run for this README. Each Path's commands are in its own How to reproduce section: `path-file-read.md` for the reader and the Talapia report, `path-atlas-sdk.md` for the Atlas runs.

## Live data read

No live file was read for this README. The Paths' reads are in `path-file-read.md` Live data read. `path-atlas-sdk.md` read the same samples and no other live file.

## Change log

- 2026-11-13: answer written from `path-file-read.md` and `path-atlas-sdk.md`, both landed at da06595 (Claude Code). No claim is disputed. Status set to answered in the README and both Path files.
- 2026-11-13: the single-Path write-up moved to `path-file-read.md` when the owner reinstated the `atlas-sdk` Path. Its history is in that file's Change log.
