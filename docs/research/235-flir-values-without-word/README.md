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

Yes, for the two FLIR cameras in use, the T640 and the T440. A short Python reader using only numpy and Pillow, with no FLIR software and no Word, computes `Sp1`, `Sp2`, the area average and `Dt` from an image saved in FLIR Tools+ or by the Word viewer. It equals FLIR's own Atlas SDK within 0.00022 °C on 86 of the 87 values of the 18 files (C13): spots, boxes, polygons and circular ellipses (C8, C19). The exception is a stretched ellipse, whose average is 0.009 °C below Atlas (C23). Against the owner's readings it matches to the displayed digit in every one of the 40 values read after an edit: 24 on the T640, in FLIR Tools+ and Word, and 16 on the T440, in FLIR Tools+ (C15).

The file stores the raw thermal plane, the calibration and the tool positions, but no readings. An edit rewrites the positions. An image-level emissivity or distance change goes into the calibration record (C20), and a per-tool one goes into that tool's header (C24). The reader uses both. The values are computed with FLIR's one-path atmosphere model (C14).

Four conditions:

- **Absolute `Dt` comes from the pipeline.** The absolute tick is a formula option in FLIR Word Reporting and is not saved into the image (C17). The pipeline must apply `abs()` itself. That also removes the sign question of C7, where FLIR Tools+ subtracts by tool number rather than by label.
- **Tools are matched by label, and the right difference tool is picked.** Spots are matched by label (C7). A FLIR Tools+ edit can leave the camera's own `Bx1Mx − Sp1` difference beside the new `Sp1 − Sp2` one, so the reader takes the spot-to-spot difference (C21).
- **Unedited images read differently.** For an image nobody edited, the camera's burned-in panel can differ from FLIR's desktop software. On the T640 it was the last digit. On the T440 the panel's difference was up to 3.5 °C away, and does not even agree with the panel's own max and spot (C16). The reader follows the desktop software, so every image in a report must be saved through FLIR Tools+ or the viewer.
- **Stretched ellipses are close, not exact.** Until Atlas's pixel rule for a non-circular ellipse is found, a box, a polygon or a circle gives FLIR's exact figure. A stretched ellipse can be 0.01 °C off, which can flip the last digit now and then (C23).

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | An edit in FLIR Tools+ or in Word's CIRViewer leaves the raw thermal plane identical on both cameras. It leaves the calibration identical apart from the colour-scale span and any image-level object parameter the operator changed (C20). It rewrites the MeasurementInfo record, where moved tools get new coordinates: FLIR0011 `Sp1` moved from (320, 222) to (318, 171). | Tested | `evidence/check_edit_preserves_raw.py`, `evidence/check-edit-preserves-raw-2026-11-13d.log`, `evidence/compare-2026-11-13d.log` |
| C2 | No reading is stored in the file's metadata, on either camera. MeasurementInfo holds tool type, number, coordinates, label and per-tool parameters only. A scan of every metadata record for the readings as float32 (°C or K) or int16 tenths found only coincidences: atmospheric and emissivity constants, unaligned offsets, the image width, camera fields that the edit leaves unchanged, and colour-table bytes of a palette FLIR Tools+ re-encodes. | Tested | `evidence/search_stored_values.py`, `evidence/search-stored-values-2026-11-13c.log`, `evidence/search-stored-values-2026-11-13d.log`, `evidence/check-edit-preserves-raw-2026-11-13d.log` |
| C3 | ~~The values computed from the file are within 0.081 °C of the owner's readings in all 36 values; 22 of 36 match to one decimal.~~ | Tested | Superseded by C13 to C15. See Change log. |
| C4 | ~~No tried rule matches every digit.~~ | Tested | Superseded by C14. See Change log. |
| C5 | ~~For the Word-edited FLIR0012, the computed values are within 0.07 °C of Word, 2 of 4 to one decimal.~~ | Tested | Superseded by C15. See Change log. |
| C6 | `Dt` is not stored. The difference tool stores references to two members, `[type1, number1, member1, type2, number2, member2]`, and its value is the first minus the second, from unrounded values. For the T640 FLIR0011 original FLIR shows 40.4 and 38.4 but `Dt` 1.9. | Tested | `evidence/compare-2026-11-13d.log` (difference tool params), `evidence/compare-to-atlas-2026-11-13d.log` (every delta equals Atlas) |
| C7 | Tool numbers and labels can disagree. In the FLIR Tools+ edit of FLIR0012, tool 1 is labelled `Sp2` and tool 2 `Sp1`. Matching spots by label gives the owner's spot values. The difference is by tool number: Atlas gives `Sp2 − Sp1` = +0.086, and the owner reports FLIR Tools+ shows 0.1. The sheet's −0.1 was a label-order reading, corrected in `compare_readings.py`. | Tested | `evidence/compare-2026-11-13d.log`, `evidence/atlas/atlas-values-2026-11-13d.log`, both at FLIR0012 FLIR Tools+ edit; owner's reply of 2026-11-13, see Change log |
| C8 | Word's CIRViewer saved `Ar1` as a polygon (tool type 10), not a box. The average over the pixels inside it is 36.386 °C. Atlas gives 36.38585 and Word showed 36.4. | Tested | `evidence/compare-2026-11-13d.log`, `evidence/compare-to-atlas-2026-11-13d.log` |
| C9 | The main JPEG picture of each file is the rendered thermal view, with palette, scale and tool markers. A FLIR Tools+ save also draws a value panel into it, and the camera draws its own panel at capture. The Word viewer's save draws markers and the scale but no value panel. | Read | Viewed the pictures of the T640 `original/FLIR0011.jpg`, `original/FLIR0013.jpg`, `original/FLIR0014.jpg`, `editted/FLIR0011.jpg` and both Word-edited FLIR0012 saves, and the T440 `original/IR_0001.jpg` and `original/IR_0011.jpg` (see Live data read). The pictures are client images and are not committed. |
| C10 | The reader runs in the project's 64-bit Python with numpy and Pillow, both already in `uv.lock`. It needs no FLIR install, no licence, no 32-bit process and no Word. | Tested | `evidence/runtime-2026-11-13.log` |
| C11 | ~~The "absolute" tick is likely stored in the difference tool's trailing bytes.~~ | Assumed | Disproved by C17. See Change log. |
| C12 | Files from the FLIR T440 use the same record layout and field offsets as the T640. The reader needed no camera-specific change. The T440's raw plane is 320 × 240, its originals carry no PiP or GPS record, and FLIR Tools+ writes RawData first in the index. | Tested | `evidence/check-edit-preserves-raw-2026-11-13d.log` (record lists), `evidence/compare-to-atlas-2026-11-13d.log` |
| C13 | The reader's unrounded values equal FLIR's Atlas SDK (`Flir.Atlas.Image` 2.0.14266.1000) on the 87 values of the 18 files from both cameras: spots, box, polygon and ellipse averages, area maxima and deltas. All are within 0.000003 °C except two areas: the Word polygon, 0.00022 °C, and the stretched Word ellipse, 0.0090 °C (C23). | Tested | `evidence/compare_to_atlas.py`, `evidence/compare-to-atlas-2026-11-13d.log`, `evidence/atlas/atlas_values.ps1`, `evidence/atlas/atlas-values-2026-11-13d.log` |
| C14 | FLIR computes atmospheric transmission over one path, `exp(−√OD·…)`, giving 0.9916256 for the T640 files, as Atlas reports. With it, the reader's raw-to-temperature curve equals Atlas's `GetValueFromSignal` to 0.000001 °C from 11 to 61 °C. The Thermimage model used in the first version splits the path into two halves of `√(OD/2)`. It gives a lower transmission, and readings 0.01 to 0.09 °C high, which caused C3's last-digit misses. | Tested | `evidence/atlas/atlas_curve.ps1`, `evidence/atlas/atlas-curve-2026-11-13.log`, `evidence/flir_fff.py` `transmission()` |
| C15 | Against the owner's readings, 62 of 68 values match to one decimal, counting the ticked Word `Dt` as `abs()` and the owner's corrected FLIR0012 `Dt` (C7). All 40 values read after an edit match: T640 FLIR Tools+ 16, T640 Word 8, T440 FLIR Tools+ 16. The 6 misses are all in the original column. | Tested | `evidence/compare_readings.py`, `evidence/compare-2026-11-13d.log` |
| C16 | The owner's original column was read from the panel the camera burned into each picture, not from FLIR's desktop computation. On the T640 the panel differs from Atlas in the last digit: FLIR0014 `avg 36.4` against 36.299, FLIR0011 `Δ 1.9` against 1.958. On the T440 the panel's `Bx1Mx − Sp1` is 9.5, 6.8 and 5.4 for IR_0001, IR_0011 and IR_0023, against 7.904, 3.259 and 5.045 from Atlas. The IR_0001 panel shows Max 39.7 and Spot 31.8, so its 9.5 does not follow from its own figures. | Read | Viewed the camera panels of the T640 `original/FLIR0011.jpg` and `original/FLIR0014.jpg` and the T440 `original/IR_0001.jpg` and `original/IR_0011.jpg`; `evidence/atlas/atlas-values-2026-11-13d.log`; owner's reply of 2026-11-13, see Change log |
| C17 | The absolute-`Dt` tick is not saved in the image. The difference tool's bytes in the Word-saved FLIR0012 are identical before and after the owner ticked it. FLIR Word Reporting names it "Formula: Show result as an absolute value" in its own resources. FLIR Tools+'s delta model (`DeltaT`: two measurements, `DeltaType`, `ValueMember`) has no absolute member. Its only absolute mode belongs to the frame-subtraction filter. | Tested | `evidence/compare-2026-11-13.log` and `evidence/compare-2026-11-13b.log` (difference tool `extra`, same in both); `evidence/atlas/find_absolute_strings.py`, `evidence/atlas/find-absolute-strings-2026-11-13.log`, `evidence/atlas/reflect_delta_model.ps1`, `evidence/atlas/reflect-delta-model-2026-11-13.log` |
| C18 | FLIR's Atlas SDK opens and measures these files from a 32-bit PowerShell, with no Word and no FLIR Tools+ window. | Tested | `evidence/atlas/atlas_values.ps1`, `evidence/atlas/atlas-values-2026-11-13d.log` |
| C19 | An ellipse tool (type 3) has two copies of its rectangle, and Atlas picks one by a flag. Its trailing bytes may hold, after the 24-byte common block, int16 tag 5, length 12, then x, y, w, h. Atlas uses that block when the common block's second uint16 is 24, as in the two FLIR Tools+ saves. When it is 0, as in the Word viewer's save, Atlas takes the int16 params, a centre and two axis ends, as (cx − rx, cy − ry, 2rx, 2ry). The two copies disagree by a pixel in all three files. For the two T440 circles the pixels are the filled integer midpoint ellipse with semi-axes w/2 and h/2 about (x + w/2, y + h/2), and equal Atlas's `GetValues()`, 8317 and 29821 of them, in Atlas's order. | Tested | `evidence/flir_fff.py` `ellipse_rect()` and `ellipse_mask()`, `evidence/check_ellipse_mask.py`, `evidence/check-ellipse-mask-2026-11-13d.log`, `evidence/atlas/atlas_ellipse_pixels.ps1`, `evidence/atlas/atlas-ellipse-pixels-2026-11-13d.log` |
| C20 | An image-level emissivity or distance change in FLIR Tools+ is written into CameraInfo, not into the tools. T440 IR_0011's emissivity went from 0.95 to 0.8 at offset 0x20, and IR_0017's distance from 1 to 5 m at 0x24. The spots' trailing bytes are the same as in an edit with no change. With those values the reader matches the owner and Atlas. | Tested | `evidence/check-edit-preserves-raw-2026-11-13d.log`, `evidence/compare-2026-11-13d.log` (tool `extra`), `evidence/compare-to-atlas-2026-11-13d.log`; the owner's notes column in the T440 `IR-readings.csv` |
| C21 | A difference tool can reference an area member: the T440 camera writes `Bx1Mx − Sp1`, params `[2, 1, 2, 1, 1, 1]`, where member 2 of a box is its maximum and member 1 of a spot its value. A FLIR Tools+ edit of IR_0011 and IR_0017 kept that unlabelled tool beside the new `Dt2` = `Sp1 − Sp2`. The owner's `Dt` after the edit is the spot-to-spot one. | Tested | `evidence/compare-2026-11-13d.log`, `evidence/compare-to-atlas-2026-11-13d.log` |
| C22 | ~~Cameras in use other than the T640 and the T440 share the layout.~~ | Assumed | Moot. The owner says these are the only FLIR models in use, and the rare Fluke camera is out of scope. See Change log. |
| C23 | A stretched ellipse does not follow C19's midpoint rule. For the Word ellipse of FLIR0012, rectangle (78, 54, 402, 200), Atlas measures 63022 pixels over rows 55 to 253 and columns 78 to 479. The midpoint rule gives 63611 pixels, 589 of them different, and an average 0.0090 °C below Atlas. No tried midpoint or analytic rule fits exactly. The closest, an analytic ellipse about (277.5, 154) with semi-axes 200.5 and 100, is 98 pixels off. Both averages round to Word's 36.2. | Tested | `evidence/check-ellipse-mask-2026-11-13d.log`, `evidence/compare-to-atlas-2026-11-13d.log`, `evidence/compare-2026-11-13d.log` |
| C24 | A per-tool emissivity, FLIR's "local parameters", is stored in that tool's 36-byte header. The flag word at header byte 22 goes from 0x0080 to 0x0087, and bytes 24, 28 and 32 hold float32 emissivity 0.8, distance 1.0 m and reflected temperature 293.15 K. Atlas reports the same three for both spots, with `UseCustomObjectParameters` True. With them the reader gives `Sp1` 40.901 and `Sp2` 41.347, equal to Atlas and to the owner's 40.9 and 41.3. Only the emissivity differed from the image's values, so which flag bit belongs to which parameter is not settled. | Tested | `evidence/flir_fff.py` `measurement_tools()`, `evidence/compare-2026-11-13d.log`, `evidence/compare-to-atlas-2026-11-13d.log` |
| C25 | A delivered Part's Word fields that show `Sp1`, `Sp2`, `Ar1` and `Dt` keep their last displayed results as text in the `.docx`, readable without Word. | Assumed | none. Settled by reading `word/document.xml` of a Part whose IR table uses the viewer's fields and comparing the cached results with the viewer. |

## Detail

### What a saved file holds

A FLIR radiometric JPEG carries a FLIR file (FFF) split across APP1 segments. Its index lists these records, in the layout ExifTool documents ([FLIR tags](https://exiftool.org/TagNames/FLIR.html)):

| Record | Holds | Changed by an edit? |
|---|---|---|
| RawData | uint16 sensor values as a PNG, 640 × 480 on the T640 and 320 × 240 on the T440 | no (C1) |
| CameraInfo | emissivity, distance, reflected and atmospheric temperature, humidity, Planck constants, atmosphere constants, colour-scale span | the colour-scale span, and any image-level parameter the operator changed (C1, C20) |
| MeasurementInfo | per tool: type, number, coordinates, label, local parameters (C24), trailing settings | yes, rewritten (C1) |
| PaletteInfo | the colour palette | T640 no; T440 re-encoded by FLIR Tools+ |
| EmbeddedImage | the visual-camera photo, T640 only | re-encoded |
| `0x29` | 8 bytes, new after a FLIR Tools+ save | added. Purpose unknown. |

The JPEG's own picture is the rendered thermal view (C9). The T440 files also hold a tool of type 7 whose two int16 params read as a float32 of 293.15 K, or 273.15 K after an edit. It does not feed any value in the table and the reader ignores it.

### How each value is obtained

| Value | Stored as | Computed as |
|---|---|---|
| `Sp1`, `Sp2` | spot tool, pixel (x, y), matched by label | temperature of that pixel, with the tool's local parameters if it has them (C24) |
| area average | box (x, y, w, h); polygon, type 10, list of points (C8); or ellipse, rectangle chosen as in C19 | mean over the pixels inside: x..x+w−1 and y..y+h−1 for a box, the filled midpoint ellipse for an ellipse (exact for circles, C19; 0.009 °C off for the one stretched sample, C23) |
| `Dt` | difference tool referencing two members (C6) | first member minus second, in the tool's order. The spot-to-spot tool when there is one (C21). For the client report, `abs()` of that, applied by the pipeline (C17). |

Temperature per pixel inverts `S = E·τ·S_obj + (1−E)·τ·S_refl + (1−τ)·S_atm` with the Planck constants from CameraInfo, and the object parameters from CameraInfo or from the tool (C24). τ is the one-path transmission of C14.

### Values read against values shown

Computed is from the file, rounded to one decimal. Shown is the owner's reading: from the camera panel for the original rows (C16), from FLIR Tools+ for the FLIR Tools+ edit rows, from Word for the Word edit rows. A `*` marks a mismatch. On the T440 originals the area is the camera's box, `Dt` is the camera's `Bx1Mx − Sp1` and there is no `Sp2`.

| Camera | Image | State | | Sp1 | Sp2 | Area avg | Dt |
|---|---|---|---|---|---|---|---|
| T640 | FLIR0011 | original | computed | 40.4 | 38.4 | 39.9 | 2.0 |
| | | | shown | 40.4 | 38.4 | 39.9 | 1.9 * |
| T640 | FLIR0011 | FLIR Tools+ edit | computed | 42.5 | 38.4 | 39.3 | 4.1 |
| | | | shown | 42.5 | 38.4 | 39.3 | 4.1 |
| T640 | FLIR0012 | original | computed | 38.0 | 34.9 | 36.7 | 3.1 |
| | | | shown | 38.0 | 34.9 | 36.7 | 3.1 |
| T640 | FLIR0012 | FLIR Tools+ edit, tool 1 is `Sp2` | computed | 37.8 | 37.9 | 36.7 | 0.1 |
| | | | shown | 37.8 | 37.9 | 36.7 | 0.1, corrected (C7) |
| T640 | FLIR0012 | Word edit, polygon, absolute Dt | computed | 37.8 | 38.2 | 36.4 | 0.4 |
| | | | shown | 37.8 | 38.2 | 36.4 | 0.4 |
| T640 | FLIR0012 | Word edit, stretched ellipse, spot emissivity 0.8, absolute Dt | computed | 40.9 | 41.3 | 36.2 | 0.4 |
| | | | shown | 40.9 | 41.3 | 36.2 | 0.4 |
| T640 | FLIR0013 | original | computed | 34.0 | 34.0 | 33.9 | 0.1 |
| | | | shown | 34.0 | 34.0 | 33.9 | 0.0 * |
| T640 | FLIR0013 | FLIR Tools+ edit | computed | 34.0 | 34.3 | 34.1 | −0.3 |
| | | | shown | 34.0 | 34.3 | 34.1 | −0.3 |
| T640 | FLIR0014 | original | computed | 37.0 | 38.9 | 36.3 | −2.0 |
| | | | shown | 37.0 | 38.9 | 36.4 * | −2.0 |
| T640 | FLIR0014 | FLIR Tools+ edit | computed | 40.1 | 39.4 | 36.4 | 0.7 |
| | | | shown | 40.1 | 39.4 | 36.4 | 0.7 |
| T440 | IR_0001 | original | computed | 31.8 | | 31.0 | 7.9 |
| | | | shown | 31.8 | | 31.0 | 9.5 * |
| T440 | IR_0001 | FLIR Tools+ edit, ellipse | computed | 29.5 | 30.7 | 31.5 | −1.3 |
| | | | shown | 29.5 | 30.7 | 31.5 | −1.3 |
| T440 | IR_0011 | original | computed | 34.6 | | 33.9 | 3.3 |
| | | | shown | 34.6 | | 33.9 | 6.8 * |
| T440 | IR_0011 | FLIR Tools+ edit, emissivity 0.8 | computed | 32.5 | 33.4 | 35.9 | −0.9 |
| | | | shown | 32.5 | 33.4 | 35.9 | −0.9 |
| T440 | IR_0017 | original | computed | 40.0 | | 34.8 | 0.9 |
| | | | shown | 40.0 | | 34.8 | 0.9 |
| T440 | IR_0017 | FLIR Tools+ edit, distance 5 m | computed | 34.8 | 33.5 | 34.9 | 1.3 |
| | | | shown | 34.8 | 33.5 | 34.9 | 1.3 |
| T440 | IR_0023 | original | computed | 32.0 | | 32.2 | 5.0 |
| | | | shown | 32.0 | | 32.2 | 5.4 * |
| T440 | IR_0023 | FLIR Tools+ edit, ellipse | computed | 32.0 | 33.0 | 32.2 | −1.1 |
| | | | shown | 32.0 | 33.0 | 32.2 | −1.1 |

Unrounded values are in `evidence/compare-2026-11-13d.log`. The six misses are camera-computed values (C16). FLIR's desktop SDK gives the same figures as the reader for them (C13).

### Absolute `Dt`

The tick is a setting of the Word formula field that displays `Dt` (C17). Saving the image from the viewer does not carry it. FLIR Tools+ has no such option for a delta. A pipeline that drops the live viewer has to apply `abs()` when it writes the table, just as the operator ticks it today.

### What the pipeline would need from the operator

1. Edit the spots and area in FLIR Tools+ or the Word viewer, and save the image, so that its MeasurementInfo holds the final positions (C1). Image-level and per-tool emissivity, distance and reflected temperature are picked up (C20, C24).
2. Keep the labels `Sp1`, `Sp2` and one area. The reader matches spots by label (C7) and takes the spot-to-spot difference (C21).
3. Use a box, a polygon or a circular ellipse for the area for FLIR's exact figure (C8, C19). A stretched ellipse reads within about 0.01 °C (C23).
4. Save every image that goes into a report, even one with no changes. An unsaved camera original carries the camera's own figures in its panel. On the T440 those were up to 3.5 °C away from the computed ones (C16).

## Disputed

None. One Path.

## Open questions

1. Answered: only the T640 and the T440 are in use among FLIR cameras (C22).
2. Answered: a per-tool emissivity lives in the tool's header (C24). Still open: which flag bit marks which of the three parameters, and an IR window, transmission below 1, which raises `NotImplementedError`.
3. Answered: FLIR Tools+ subtracts by tool number (C7).
4. Answered: the original column was read from the camera panel (C16).
5. What is the 8-byte `0x29` record that a FLIR Tools+ save adds?
6. Can the four values be read from a delivered Part itself, from its `.docx` file with Word closed? The viewer's own copy of the image is in its binary (`223-flir-xml-join` `path-static-cfb.md` C14), not in a saved JPEG. The owner points out that the viewer can insert Word fields for `Sp1`, `Sp2`, `Dt` and `Ar1`, and Word keeps a field's last result as text (C25).
7. Why does the T440 panel's difference disagree with its own max and spot (C16)? It does not affect saved images.
8. What pixel rule does Atlas use for a stretched ellipse (C23)?

## How to reproduce

From a clean worktree, with the samples folder below in place:

```
S=<Integration Branch worktree>/scratch/235-flir-values-without-word/samples
E=docs/research/235-flir-values-without-word/evidence
uv run --frozen python -I $E/compare_readings.py "$S/Flir T640" "$S/Flir T440"
uv run --frozen python -I $E/search_stored_values.py "$S/Flir T640" "$S/Flir T440"
uv run --frozen python -I $E/check_edit_preserves_raw.py "$S/Flir T640" "$S/Flir T440"
uv run --frozen python -I $E/hypotheses.py "$S/Flir T640"
```

The FLIR SDK reference runs in 32-bit PowerShell and needs FLIR Tools installed:

```
PS32=C:/Windows/SysWOW64/WindowsPowerShell/v1.0/powershell.exe
$PS32 -NoProfile -ExecutionPolicy Bypass -File $E/atlas/atlas_values.ps1 -samples "$S" > atlas-values.log
$PS32 -NoProfile -ExecutionPolicy Bypass -File $E/atlas/atlas_ellipse_pixels.ps1 -samples "$S" -out ellipse-values
$PS32 -NoProfile -ExecutionPolicy Bypass -File $E/atlas/atlas_curve.ps1 -file "$S/Flir T640/original/FLIR0011.jpg"
$PS32 -NoProfile -ExecutionPolicy Bypass -File $E/atlas/reflect_delta_model.ps1
uv run --frozen python -I $E/atlas/find_absolute_strings.py "C:/Program Files (x86)/FLIR Systems"
uv run --frozen python -I $E/compare_to_atlas.py "$S" atlas-values.log
uv run --frozen python -I $E/check_ellipse_mask.py "$S" ellipse-values
```

The logs in `evidence/` were captured with the system Python 3.13.1, numpy 2.3.2 and Pillow 11.3.0. Logs ending in `-2026-11-13.log` hold the first version's runs, and `b`, `c` and `d` the later ones. `compare-2026-11-13.log` keeps the difference-tool bytes from before the absolute tick that C17 compares against. The first and `b` runs used the flat samples layout of their day, `<SAMPLES>/original/` rather than `<SAMPLES>/Flir T640/original/`. The `c` logs predate the stretched-ellipse sample and per-tool parameters.

## Live data read

`<SAMPLES>` is `scratch/235-flir-values-without-word/samples/` in the Integration Branch worktree, a folder git ignores. The owner placed the T640 files there on 2026-11-13. The first `IR-readings.csv` was an Excel workbook despite its extension. At 18:08 to 18:09 the owner replaced it with a real CSV and re-saved the Word-edited FLIR0012 with absolute `Dt` ticked. At about 20:27 the owner moved the T640 files into `Flir T640/`, unchanged, and added the T440 set in `Flir T440/`. At 21:04 to 21:07 the owner added a second Word save of FLIR0012, with a stretched ellipse and per-spot emissivity, and its rows to the T640 sheet.

| Path | File | Bytes | SHA-256 | Read on |
|------|------|-------|---------|---------|
| `<SAMPLES>/Flir T640/original/` | `FLIR0011.jpg` | 1296458 | `388b17dc65edf3ad01a5e04bcf49568fec0929479f933289cf247a172bd28e00` | 2026-11-13 |
| `<SAMPLES>/Flir T640/original/` | `FLIR0012.jpg` | 1564246 | `08ce5a7362d70ce11f0f9a6731ce07d470c87632dae0db8203a9674ad0f66a9c` | 2026-11-13 |
| `<SAMPLES>/Flir T640/original/` | `FLIR0013.jpg` | 914461 | `3ea10ae5c331043849a8bc2ee3bc0d061a3366c517f445ae35a58923f914eac2` | 2026-11-13 |
| `<SAMPLES>/Flir T640/original/` | `FLIR0014.jpg` | 1788758 | `fde4c4b26722a3479b94d5cbdc20c73df7425de56acfa9c14503c946a2933eca` | 2026-11-13 |
| `<SAMPLES>/Flir T640/editted/` | `FLIR0011.jpg` | 1296458 | `ee18948e9f83c80970562b0f6aa936138e5a5cef61edd1d6f89dac5cd6eab828` | 2026-11-13 |
| `<SAMPLES>/Flir T640/editted/` | `FLIR0012-editted-from-Software-FlirTools+-directly.jpg` | 944147 | `225adcfb82fdfdf9dbb9e4f758e3867d6d6d26448fd4682a49b7266146e6c617` | 2026-11-13 |
| `<SAMPLES>/Flir T640/editted/` | `FLIR0012-editted-in-word-using-FlirTools+-CIRViewer.jpg`, first save, `Dt` not absolute | 891086 | `dcf611c71e9597cdb19ad14a7973297fc85c10d52da9105844e03da02b9533d7` | 2026-11-13 |
| `<SAMPLES>/Flir T640/editted/` | `FLIR0012-editted-in-word-using-FlirTools+-CIRViewer.jpg`, second save, absolute `Dt` | 894838 | `64c879f4632b9942163f501015f99e07e3f2c17874c5cc44c98c11b768ebd79a` | 2026-11-13 |
| `<SAMPLES>/Flir T640/editted/` | `FLIR0012-editted-in-word-using-FlirTools+-CIRViewer-elips.jpg` | 897892 | `0d4f5ab10cce139e3cd8249f09f10d30ae0abafc8b02401cda456df052e6ae2b` | 2026-11-13 |
| `<SAMPLES>/Flir T640/editted/` | `FLIR0013.jpg` | 914461 | `e411a41636fcd856736bd26166d467df6e449c8acbc9e9f7bb538c7bb6b1117c` | 2026-11-13 |
| `<SAMPLES>/Flir T640/editted/` | `FLIR0014.jpg` | 1788758 | `b81dac1169250e8b9325650e1da0b93ffa5f7b9e531ecf601603f490d2a3ed7b` | 2026-11-13 |
| `<SAMPLES>/Flir T640/` | `IR-readings.csv`, first version, an xlsx | 9125 | `9061d32effa57dab6e40448e453991c4425e1fa2a39b2648a7c1ced3acbfbe1e` | 2026-11-13 |
| `<SAMPLES>/Flir T640/` | `IR-readings.csv`, second version, CSV | 540 | `3bd39a70a5804a5b86e2a7076e559bd5960245ce51176b01870c95a1bf6e219b` | 2026-11-13 |
| `<SAMPLES>/Flir T640/` | `IR-readings.csv`, third version, with the ellipse rows and a notes column | 983 | `b3b1248c8589f2543ef56e0fb5b11f39017d6f7d7e850dc60fab36b1f15a065c` | 2026-11-13 |
| `<SAMPLES>/Flir T440/original/` | `IR_0001.jpg` | 195166 | `952e66df02751841f2de415f5e6dd6e88645c229d1b1d03b50af0f5a7ecd5dd6` | 2026-11-13 |
| `<SAMPLES>/Flir T440/original/` | `IR_0011.jpg` | 189216 | `7d1345cb9fe6d9fc6291f50235da46229cf2e1b621ccbf55a679bdeac2b53f4e` | 2026-11-13 |
| `<SAMPLES>/Flir T440/original/` | `IR_0017.jpg` | 188216 | `b16d5c33ddfb35344c689e52825237c3350b35777cdcfbe028066e3a532df54c` | 2026-11-13 |
| `<SAMPLES>/Flir T440/original/` | `IR_0023.jpg` | 185428 | `de42eb0c678292e2493054e39f7f08ef0e41ca959e1946de37f83163a669a8e3` | 2026-11-13 |
| `<SAMPLES>/Flir T440/editted/` | `IR_0001.jpg` | 241570 | `845cc3bf0963770b46b0840c09383a1ed15a7bddb05f5c15b563fc1b4034149f` | 2026-11-13 |
| `<SAMPLES>/Flir T440/editted/` | `IR_0011.jpg` | 238447 | `797293d0e0f80f4abcbb91406aa47c40b0dc299d8672567de88c78462d0006e8` | 2026-11-13 |
| `<SAMPLES>/Flir T440/editted/` | `IR_0017.jpg` | 237453 | `19e04718178e9e4f6d018521482ede067e79245d39fe9715f8f646872bb35b3b` | 2026-11-13 |
| `<SAMPLES>/Flir T440/editted/` | `IR_0023.jpg` | 236931 | `53010cc9c1f77a9fa7c07131952f90dbe32134d02c04e5e6cb0745574ef9ed9b` | 2026-11-13 |
| `<SAMPLES>/Flir T440/` | `IR-readings.csv` | 886 | `ba12a34c22acf25ac6f4c7f8e2fdc30e832ec8a7e7a1177ff84d49dd4ed40850` | 2026-11-13 |

## Change log

- 2026-11-13: fourth version (Claude Code). Prompted by the owner's Word save of FLIR0012 with a stretched ellipse and per-spot emissivity 0.8, and the owner's statement, given in the agent session, that only the T640 and the T440 are in use among FLIR cameras and that Fluke is out of scope. C22 is struck as moot. C19 is rewritten: Atlas takes an ellipse's rectangle from its params when the trailing block's flag is 0. C23 is rewritten from Assumed to Tested: the stretched ellipse does not follow the midpoint rule, and the reader is 0.009 °C below Atlas on it. New: C24, per-tool parameters in the tool header, and C25, the Word fields of a delivered Part, Assumed. The reader now applies a tool's local parameters. C1, C2, C6 to C9, C12, C13, C15 to C18, C20 and C21 now cite the `d` logs. The verdict gains the stretched-ellipse condition. Open questions 1 and 2 are answered, 6 is reworded around the owner's note on Word fields, and 8 now asks for Atlas's stretched-ellipse rule.
- 2026-11-13: third version (Claude Code). Prompted by the owner's T440 samples and answers to open questions 2 to 5, given in the agent session. The owner said: the original column was read from the camera panel; FLIR Tools+ shows `Dt` as 0.1 for the FLIR Tools+ edit of FLIR0012; the T440 edits change emissivity and distance and add an ellipse. C12 is rewritten from Assumed to Tested for the T440, and other cameras move to the new C22. C7 now records that the difference follows tool numbers, and `compare_readings.py` carries the owner's corrected 0.1. The reader now picks the spot-to-spot difference tool rather than computing `Sp1 − Sp2` by label. That gives the same value on every file except that one. C1, C2, C6, C8, C9, C13, C15, C16 and C18 are updated for both cameras. New: C19 to C23. Open questions 3 and 4 are answered, 2 is narrowed, 7 and 8 are new. The verdict now covers two cameras and ellipse areas. These owner answers are cited from the session. Claims resting on them stay Tested or Read until the owner posts them on the ticket.
- 2026-11-13: second version (Claude Code). Prompted by the owner's absolute-`Dt` sample and the suggestion to inspect FLIR's SDK. Used as a reference, Atlas showed that the first version's transmission model was wrong (C14). The reader now matches Atlas (C13) and every edited reading (C15). C3, C4 and C5 are struck because their figures came from the old model. C8 is rewritten with the new figure. C11 is struck because C17 disproves it. New: C13 to C18. The verdict no longer carries the ±0.1 °C condition. The Atlas SDK is used only as a reference in this version. The `atlas-sdk` Path was not followed here; the owner later reinstated it on the ticket (#235) to be tried.
- 2026-11-13: first version (Claude Code).
