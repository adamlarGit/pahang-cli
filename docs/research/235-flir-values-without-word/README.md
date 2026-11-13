---
ticket: 235
type: research
map: 221
status: open
updated: 2026-11-13
agent: Claude Code, claude-opus-5-5
---
# Can the IR table values be read from a saved FLIR image without Word?

## Verdict

Yes. A short Python reader using only numpy and Pillow, with no FLIR software and no Word, computes `Sp1`, `Sp2`, `Ar1` (average) and `Dt` from an image saved in FLIR Tools+ or by the Word viewer. It matches FLIR's own Atlas SDK within 0.00022 °C on all 36 values (C13). Against the owner's readings it matches to the displayed digit in every one of the 20 values read after an edit, in FLIR Tools+ or in Word (C15).

The file stores the raw thermal plane, the calibration and the tool positions, but no readings. An edit rewrites only the positions (C1, C2). The values are computed with FLIR's one-path atmosphere model (C14).

Three conditions:

- **Absolute `Dt` comes from the pipeline.** The absolute tick is a formula option in FLIR Word Reporting and is not saved into the image (C17). The pipeline must apply `abs(Sp1 − Sp2)` itself.
- **Tools are matched by label.** Match by label (`Sp1`, `Sp2`), not tool number (C7), and handle polygon areas as well as boxes (C8).
- **Unedited images read differently.** For an image nobody edited, the camera's own burned-in values can differ from FLIR's desktop software in the last digit (C16). The reader follows the desktop software.

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | An edit in FLIR Tools+ or in Word's CIRViewer leaves the raw thermal plane identical, and leaves the calibration identical apart from the colour-scale span. It rewrites the MeasurementInfo record, where moved tools get new coordinates: FLIR0011 `Sp1` moved from (320, 222) to (318, 171). | Tested | `evidence/check_edit_preserves_raw.py`, `evidence/check-edit-preserves-raw-2026-11-13.log`, `evidence/check-edit-preserves-raw-2026-11-13b.log`, `evidence/compare-2026-11-13b.log` |
| C2 | No reading is stored in the file's metadata. MeasurementInfo holds tool type, number, coordinates and label only. A scan of every metadata record for the readings as float32 (°C or K) or int16 tenths found three hits, all coincidences: an atmospheric constant, an unaligned offset, and a camera field that no edit changes. | Tested | `evidence/search_stored_values.py`, `evidence/search-stored-values-2026-11-13b.log`, `evidence/check-edit-preserves-raw-2026-11-13.log` |
| C3 | ~~The values computed from the file are within 0.081 °C of the owner's readings in all 36 values; 22 of 36 match to one decimal.~~ | Tested | Superseded by C13 to C15. See Change log. |
| C4 | ~~No tried rule matches every digit.~~ | Tested | Superseded by C14. See Change log. |
| C5 | ~~For the Word-edited FLIR0012, the computed values are within 0.07 °C of Word, 2 of 4 to one decimal.~~ | Tested | Superseded by C15. See Change log. |
| C6 | `Dt` is not stored. The difference tool stores references to two spots. Its value is `Sp1 − Sp2` from the unrounded spots: for the FLIR0011 original FLIR shows 40.4 and 38.4 but `Dt` 1.9. | Read | `evidence/compare-2026-11-13b.log` (difference tool params `[1, 1, 1, 1, 2, 1]`); owner's `IR-readings.csv`, FLIR0011 rows |
| C7 | Tool numbers and labels can disagree. In the FLIR Tools+ edit of FLIR0012, tool 1 is labelled `Sp2` and tool 2 `Sp1`. Matching by label gives the owner's values. Atlas defines that file's delta by tool number, as `Sp2 − Sp1` = +0.086, while the owner recorded −0.1. | Tested | `evidence/compare-2026-11-13b.log`, `evidence/atlas/atlas-values-2026-11-13.log`, both at FLIR0012 FLIR Tools+ edit |
| C8 | Word's CIRViewer saved `Ar1` as a polygon (tool type 10), not a box. The average over the pixels inside it is 36.386 °C. Atlas gives 36.38585 and Word showed 36.4. | Tested | `evidence/compare-2026-11-13b.log`, `evidence/compare-to-atlas-2026-11-13.log` |
| C9 | The main JPEG picture of each file is the rendered thermal view, with palette, scale and tool markers. A FLIR Tools+ save also draws a value panel into it, and the camera draws its own panel at capture. The Word viewer's save draws markers and the scale but no value panel. | Read | Viewed the pictures of `original/FLIR0011.jpg`, `original/FLIR0013.jpg`, `original/FLIR0014.jpg`, `editted/FLIR0011.jpg` and the Word-edited FLIR0012 (see Live data read). The pictures are client images and are not committed. |
| C10 | The reader runs in the project's 64-bit Python with numpy and Pillow, both already in `uv.lock`. It needs no FLIR install, no licence, no 32-bit process and no Word. | Tested | `evidence/runtime-2026-11-13.log` |
| C11 | ~~The "absolute" tick is likely stored in the difference tool's trailing bytes.~~ | Assumed | Disproved by C17. See Change log. |
| C12 | Files from other FLIR cameras or firmware use the same record layout and offsets. | Assumed | none. All nine files come from one FLIR T640. Settled by running `evidence/compare_to_atlas.py` on images from each camera in use. |
| C13 | The reader's unrounded values equal FLIR's Atlas SDK (`Flir.Atlas.Image` 2.0.14266.1000) on all 36 values of the nine files: spots, box and polygon averages and deltas. All are within 0.000002 °C except the Word polygon, at 0.00022 °C. | Tested | `evidence/compare_to_atlas.py`, `evidence/compare-to-atlas-2026-11-13.log`, `evidence/atlas/atlas_values.ps1`, `evidence/atlas/atlas-values-2026-11-13.log` |
| C14 | FLIR computes atmospheric transmission over one path, `exp(−√OD·…)`, giving 0.9916256 for these files, as Atlas reports. With it, the reader's raw-to-temperature curve equals Atlas's `GetValueFromSignal` to 0.000001 °C from 11 to 61 °C. The Thermimage model used in the first version splits the path into two halves of `√(OD/2)`. It gives a lower transmission, and readings 0.01 to 0.09 °C high, which caused C3's last-digit misses. | Tested | `evidence/atlas/atlas_curve.ps1`, `evidence/atlas/atlas-curve-2026-11-13.log`, `evidence/flir_fff.py` `transmission()` |
| C15 | Against the owner's readings, 33 of 36 values match to one decimal, counting the ticked Word `Dt` as `abs()`. All 20 values read after an edit match, in FLIR Tools+ (16) and in Word (4). The 3 misses are all in the original column. All 18 spots match. | Tested | `evidence/compare_readings.py`, `evidence/compare-2026-11-13b.log`, `evidence/hypotheses-2026-11-13b.log` |
| C16 | The owner's original column matches the panel the camera burned into each picture, not FLIR's desktop computation. For FLIR0014 the camera shows `avg 36.4` and Atlas gives 36.299. For FLIR0011 the camera shows `Δ 1.9` and Atlas gives 1.958. | Read | Viewed the camera panels of `original/FLIR0011.jpg` and `original/FLIR0014.jpg`; `evidence/atlas/atlas-values-2026-11-13.log` |
| C17 | The absolute-`Dt` tick is not saved in the image. The difference tool's bytes in the Word-saved FLIR0012 are identical before and after the owner ticked it. FLIR Word Reporting names it "Formula: Show result as an absolute value" in its own resources. FLIR Tools+'s delta model (`DeltaT`: two measurements, `DeltaType`, `ValueMember`) has no absolute member. Its only absolute mode belongs to the frame-subtraction filter. | Tested | `evidence/compare-2026-11-13.log` and `evidence/compare-2026-11-13b.log` (difference tool `extra`, same in both); `evidence/atlas/find_absolute_strings.py`, `evidence/atlas/find-absolute-strings-2026-11-13.log`, `evidence/atlas/reflect_delta_model.ps1`, `evidence/atlas/reflect-delta-model-2026-11-13.log` |
| C18 | FLIR's Atlas SDK opens and measures these files from a 32-bit PowerShell, with no Word and no FLIR Tools+ window. | Tested | `evidence/atlas/atlas_values.ps1`, `evidence/atlas/atlas-values-2026-11-13.log` |

## Detail

### What a saved file holds

A FLIR radiometric JPEG carries a FLIR file (FFF) split across APP1 segments. Its index lists these records, in the layout ExifTool documents ([FLIR tags](https://exiftool.org/TagNames/FLIR.html)):

| Record | Holds | Changed by an edit? |
|---|---|---|
| RawData | 640 × 480 uint16 sensor values, as a PNG | no (C1) |
| CameraInfo | emissivity, distance, reflected and atmospheric temperature, humidity, Planck constants, atmosphere constants, colour-scale span | only the colour-scale span (C1) |
| MeasurementInfo | per tool: type, number, coordinates, label | yes, rewritten (C1) |
| PaletteInfo | the colour palette | no |
| EmbeddedImage | the visual-camera photo | re-encoded |
| `0x29` | 8 bytes, new after a FLIR Tools+ save | added. Purpose unknown. |

The JPEG's own picture is the rendered thermal view (C9).

### How each value is obtained

| Value | Stored as | Computed as |
|---|---|---|
| `Sp1`, `Sp2` | spot tool, pixel (x, y), matched by label | temperature of that pixel |
| `Ar1` | box tool (x, y, w, h), or polygon tool (type 10, list of points) | mean temperature over the pixels inside, x..x+w−1 and y..y+h−1 for a box |
| `Dt` | difference tool referencing two spots | `Sp1 − Sp2` from unrounded spots (C6). For the client report, `abs()` of that, applied by the pipeline (C17). |

Temperature per pixel inverts `S = E·τ·S_obj + (1−E)·τ·S_refl + (1−τ)·S_atm` with the Planck constants from CameraInfo. τ is the one-path transmission of C14.

### Values read against values shown

Computed is from the file, rounded to one decimal. Shown is the owner's reading: from FLIR Tools+ for the original and FLIR Tools+ edit rows, from Word for the Word edit row. A `*` marks a mismatch.

| Image | State | | Sp1 | Sp2 | Ar1 avg | Dt |
|---|---|---|---|---|---|---|
| FLIR0011 | original | computed | 40.4 | 38.4 | 39.9 | 2.0 |
| | | shown | 40.4 | 38.4 | 39.9 | 1.9 * |
| FLIR0011 | FLIR Tools+ edit | computed | 42.5 | 38.4 | 39.3 | 4.1 |
| | | shown | 42.5 | 38.4 | 39.3 | 4.1 |
| FLIR0012 | original | computed | 38.0 | 34.9 | 36.7 | 3.1 |
| | | shown | 38.0 | 34.9 | 36.7 | 3.1 |
| FLIR0012 | FLIR Tools+ edit | computed | 37.8 | 37.9 | 36.7 | −0.1 |
| | | shown | 37.8 | 37.9 | 36.7 | −0.1 |
| FLIR0012 | Word edit, absolute Dt | computed | 37.8 | 38.2 | 36.4 | 0.4 |
| | | shown | 37.8 | 38.2 | 36.4 | 0.4 |
| FLIR0013 | original | computed | 34.0 | 34.0 | 33.9 | 0.1 |
| | | shown | 34.0 | 34.0 | 33.9 | 0.0 * |
| FLIR0013 | FLIR Tools+ edit | computed | 34.0 | 34.3 | 34.1 | −0.3 |
| | | shown | 34.0 | 34.3 | 34.1 | −0.3 |
| FLIR0014 | original | computed | 37.0 | 38.9 | 36.3 | −2.0 |
| | | shown | 37.0 | 38.9 | 36.4 * | −2.0 |
| FLIR0014 | FLIR Tools+ edit | computed | 40.1 | 39.4 | 36.4 | 0.7 |
| | | shown | 40.1 | 39.4 | 36.4 | 0.7 |

Unrounded values are in `evidence/compare-2026-11-13b.log`. The three misses are camera-computed values (C16). FLIR's desktop SDK gives the same figures as the reader for them (C13).

### Absolute `Dt`

The tick is a setting of the Word formula field that displays `Dt` (C17). Saving the image from the viewer does not carry it. FLIR Tools+ has no such option for a delta. A pipeline that drops the live viewer has to apply `abs()` when it writes the table, just as the operator ticks it today.

### What the pipeline would need from the operator

1. Edit the spots and area in FLIR Tools+ or the Word viewer, and save the image, so that its MeasurementInfo holds the final positions (C1).
2. Keep the labels `Sp1`, `Sp2` and one area. The reader matches by label (C7).
3. Use a box or a polygon for the area. Ellipse areas are not covered by these samples.
4. Save every image that goes into a report, even one with no changes. An unsaved camera original carries the camera's own figures in its panel, and those can differ from the computed ones by 0.1 (C16).

## Disputed

None. One Path.

## Open questions

1. Do other cameras in use share the layout (C12)?
2. Does a per-tool emissivity or distance set in FLIR Tools+ live in the tools' trailing bytes, and does it change the values? The samples use the global parameters only, and an IR window (transmission below 1) is not handled.
3. Which way does FLIR Tools+ display `Dt` when tool numbers and labels disagree (C7)? Atlas says `Sp2 − Sp1`, the owner recorded `Sp1 − Sp2`. With absolute `Dt` this does not change the report.
4. Where did the owner read the original column: the camera panel in the picture, or FLIR Tools+ opening the unedited file? C16 suggests the panel.
5. What is the 8-byte `0x29` record that a FLIR Tools+ save adds?
6. Can a delivered Part's live viewer be read the same way? Its own copy of the image is in the viewer's binary (`223-flir-xml-join` `path-static-cfb.md` C14), not in a saved file.

## How to reproduce

From a clean worktree, with the samples folder below in place:

```
S=<Integration Branch worktree>/scratch/235-flir-values-without-word/samples
E=docs/research/235-flir-values-without-word/evidence
uv run --frozen python -I $E/compare_readings.py "$S"
uv run --frozen python -I $E/hypotheses.py "$S"
uv run --frozen python -I $E/search_stored_values.py "$S"
uv run --frozen python -I $E/check_edit_preserves_raw.py "$S"
```

The FLIR SDK reference runs in 32-bit PowerShell and needs FLIR Tools installed:

```
PS32=C:/Windows/SysWOW64/WindowsPowerShell/v1.0/powershell.exe
$PS32 -NoProfile -ExecutionPolicy Bypass -File $E/atlas/atlas_values.ps1 -samples "$S" > atlas-values.log
$PS32 -NoProfile -ExecutionPolicy Bypass -File $E/atlas/atlas_curve.ps1 -file "$S/original/FLIR0011.jpg"
$PS32 -NoProfile -ExecutionPolicy Bypass -File $E/atlas/reflect_delta_model.ps1
uv run --frozen python -I $E/atlas/find_absolute_strings.py "C:/Program Files (x86)/FLIR Systems"
uv run --frozen python -I $E/compare_to_atlas.py "$S" atlas-values.log
```

The logs in `evidence/` were captured with the system Python 3.13.1, numpy 2.3.2 and Pillow 11.3.0. Logs ending in `-2026-11-13.log` without `b` hold the first version's runs. `compare-2026-11-13.log` keeps the difference-tool bytes from before the absolute tick that C17 compares against.

## Live data read

`<SAMPLES>` is `scratch/235-flir-values-without-word/samples/` in the Integration Branch worktree, a folder git ignores. The owner placed the files there on 2026-11-13. The first `IR-readings.csv` was an Excel workbook despite its extension. At 18:08 to 18:09 the owner replaced it with a real CSV and re-saved the Word-edited FLIR0012 with absolute `Dt` ticked.

| Path | File | Bytes | SHA-256 | Read on |
|------|------|-------|---------|---------|
| `<SAMPLES>/original/` | `FLIR0011.jpg` | 1296458 | `388b17dc65edf3ad01a5e04bcf49568fec0929479f933289cf247a172bd28e00` | 2026-11-13 |
| `<SAMPLES>/original/` | `FLIR0012.jpg` | 1564246 | `08ce5a7362d70ce11f0f9a6731ce07d470c87632dae0db8203a9674ad0f66a9c` | 2026-11-13 |
| `<SAMPLES>/original/` | `FLIR0013.jpg` | 914461 | `3ea10ae5c331043849a8bc2ee3bc0d061a3366c517f445ae35a58923f914eac2` | 2026-11-13 |
| `<SAMPLES>/original/` | `FLIR0014.jpg` | 1788758 | `fde4c4b26722a3479b94d5cbdc20c73df7425de56acfa9c14503c946a2933eca` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0011.jpg` | 1296458 | `ee18948e9f83c80970562b0f6aa936138e5a5cef61edd1d6f89dac5cd6eab828` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0012-editted-from-Software-FlirTools+-directly.jpg` | 944147 | `225adcfb82fdfdf9dbb9e4f758e3867d6d6d26448fd4682a49b7266146e6c617` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0012-editted-in-word-using-FlirTools+-CIRViewer.jpg`, first save, `Dt` not absolute | 891086 | `dcf611c71e9597cdb19ad14a7973297fc85c10d52da9105844e03da02b9533d7` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0012-editted-in-word-using-FlirTools+-CIRViewer.jpg`, second save, absolute `Dt` | 894838 | `64c879f4632b9942163f501015f99e07e3f2c17874c5cc44c98c11b768ebd79a` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0013.jpg` | 914461 | `e411a41636fcd856736bd26166d467df6e449c8acbc9e9f7bb538c7bb6b1117c` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0014.jpg` | 1788758 | `b81dac1169250e8b9325650e1da0b93ffa5f7b9e531ecf601603f490d2a3ed7b` | 2026-11-13 |
| `<SAMPLES>/` | `IR-readings.csv`, first version, an xlsx | 9125 | `9061d32effa57dab6e40448e453991c4425e1fa2a39b2648a7c1ced3acbfbe1e` | 2026-11-13 |
| `<SAMPLES>/` | `IR-readings.csv`, second version, CSV | 540 | `3bd39a70a5804a5b86e2a7076e559bd5960245ce51176b01870c95a1bf6e219b` | 2026-11-13 |

## Change log

- 2026-11-13: second version (Claude Code). Prompted by the owner's absolute-`Dt` sample and the suggestion to inspect FLIR's SDK. Used as a reference, Atlas showed that the first version's transmission model was wrong (C14). The reader now matches Atlas (C13) and every edited reading (C15). C3, C4 and C5 are struck because their figures came from the old model. C8 is rewritten with the new figure. C11 is struck because C17 disproves it. New: C13 to C18. The verdict no longer carries the ±0.1 °C condition. The Atlas SDK is used only as a reference; the dropped `atlas-sdk` Path is not reopened.
- 2026-11-13: first version (Claude Code).
