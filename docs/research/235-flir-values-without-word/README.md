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

Yes, under conditions. A short Python reader using only numpy and Pillow, with no FLIR software and no Word, computed `Sp1`, `Sp2`, `Ar1` (average) and `Dt` for all nine sample files. Every value is within 0.081 °C of what FLIR Tools+ or the Word viewer showed (C3, C5). The file does not store the readings. It stores the raw thermal plane, the calibration and the tool positions, and an edit in FLIR Tools+ or in Word rewrites only the positions (C1, C2). So the values are computed the same way FLIR computes them.

The condition is the last digit. Only 22 of the 36 values equal FLIR's figure to one decimal. The other 14 differ by 0.1, and no simple rule closes that gap (C4). If the report must show exactly the digits FLIR shows, this route does not give them yet. If the owner accepts ±0.1 °C, it works today. A FLIR Tools+ save also draws its own values onto the picture (C9), which may be a source of FLIR's exact digits; this is untested.

The pipeline must match tools by label rather than tool number (C7) and must handle polygon areas as well as boxes (C8). `Dt` is computed as `Sp1 − Sp2` from the unrounded spots and is not stored (C6).

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | An edit in FLIR Tools+ or in Word's CIRViewer leaves the raw thermal plane identical, and leaves the calibration identical apart from the colour-scale span. It rewrites the MeasurementInfo record, where moved tools get new coordinates: FLIR0011 `Sp1` moved from (320, 222) to (318, 171). | Tested | `evidence/check_edit_preserves_raw.py`, `evidence/check-edit-preserves-raw-2026-11-13.log`, `evidence/compare-2026-11-13.log` |
| C2 | No reading is stored in the file's metadata. MeasurementInfo holds tool type, number, coordinates and label only. A scan of every metadata record for the readings as float32 (°C or K) or int16 tenths found three hits, all coincidences: an atmospheric constant, an unaligned offset, and a camera field that no edit changes. | Tested | `evidence/search_stored_values.py`, `evidence/search-stored-values-2026-11-13.log`, `evidence/check-edit-preserves-raw-2026-11-13.log` |
| C3 | The values computed from the file (Planck and atmosphere model, spot at its stored pixel, box average over x..x+w−1, y..y+h−1) are within 0.081 °C of the owner's FLIR Tools+ and Word readings in all 36 values. 22 of 36 match to one decimal. | Tested | `evidence/compare_readings.py`, `evidence/compare-2026-11-13.log` |
| C4 | No tried rule matches every digit: rounding, truncation, pixel offsets of ±1, 3×3 and 5×5 spot means, three box edge rules, or dropping the atmosphere correction. The plain rule of C3 has the smallest worst-case error. | Tested | `evidence/hypotheses.py`, `evidence/hypotheses-2026-11-13.log` |
| C5 | For the one image edited in Word (FLIR0012), the values computed from the image saved by the Word viewer are within 0.07 °C of what Word showed. 2 of 4 match to one decimal. | Tested | `evidence/compare-2026-11-13.log`, block "FLIR0012, Word CIRViewer edit" |
| C6 | `Dt` is not stored. The difference tool stores references to spot 1 and spot 2. FLIR computes `Dt` from the unrounded spots: for the FLIR0011 original it shows 40.4 and 38.4 but `Dt` 1.9. | Read | `evidence/compare-2026-11-13.log` (difference tool params `[1, 1, 1, 1, 2, 1]`); owner's `IR-readings.csv`, FLIR0011 rows |
| C7 | Tool numbers and labels can disagree. In the FLIR Tools+ edit of FLIR0012, tool 1 is labelled `Sp2` and tool 2 `Sp1`. Matching by label gives the owner's values, and matching by number swaps them and flips the sign of `Dt`. | Tested | `evidence/compare-2026-11-13.log`, block "FLIR0012, FLIR Tools+ edit" |
| C8 | Word's CIRViewer saved `Ar1` as an 11-point polygon (tool type 10), not a box. The average over the pixels inside it is 36.405 °C, and Word showed 36.4. | Tested | `evidence/compare-2026-11-13.log`, block "FLIR0012, Word CIRViewer edit" |
| C9 | The main JPEG picture of each file is the rendered thermal view, with palette, scale and tool markers. A FLIR Tools+ save also draws a value panel into it. For FLIR0011 that panel reads `Sp1 42.5`, `Sp2 38.4`, `Average 39.3`, `Sp1-Sp2 4.1`, the owner's figures. The Word viewer's save draws markers and the scale but no value panel. | Read | Viewed the pictures of `original/FLIR0011.jpg`, `editted/FLIR0011.jpg` and the Word-edited FLIR0012 (see Live data read). The pictures are client images and are not committed. |
| C10 | The reader runs in the project's 64-bit Python with numpy and Pillow, both already in `uv.lock`. It needs no FLIR install, no licence, no 32-bit process and no Word. | Tested | `evidence/runtime-2026-11-13.log`; `evidence/compare_readings.py` run with `uv run --frozen` gives the same summary line |
| C11 | An absolute `Dt` is `abs(Sp1 − Sp2)`. The "absolute" tick is likely stored in the difference tool's trailing bytes. | Assumed | none. No sample has the tick set. Settled by saving one image with the tick set and comparing its MeasurementInfo with C7's. |
| C12 | Files from other FLIR cameras or firmware use the same record layout and offsets. | Assumed | none. All nine files come from one FLIR T640. Settled by running `flir_fff.py` on images from each camera in use. |

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
| `Sp1`, `Sp2` | spot tool, pixel (x, y) | temperature of that pixel |
| `Ar1` | box tool (x, y, w, h), or polygon tool (type 10, list of points) | mean temperature over the pixels inside |
| `Dt` | difference tool referencing spot 1 and spot 2 | `Sp1 − Sp2` from unrounded spots (C6). The absolute form is `abs()` of that (C11). |

Temperature per pixel is the Planck inverse with emissivity, reflected-temperature and two-band atmosphere correction. This is the `raw2temp` model of the Thermimage R package, which ExifTool's FLIR notes also point to. All inputs come from CameraInfo.

### Values read against values shown

Computed is from the file. FLIR Tools+ is the owner's reading in FLIR Tools+. Word is the owner's reading in the Word viewer. A `*` marks a last-digit mismatch.

| Image | State | | Sp1 | Sp2 | Ar1 avg | Dt |
|---|---|---|---|---|---|---|
| FLIR0011 | original | computed | 40.435 | 38.471 | 39.908 | 1.964 |
| | | FLIR Tools+ | 40.4 | 38.4 * | 39.9 | 1.9 * |
| FLIR0011 | FLIR Tools+ edit | computed | 42.557 | 38.471 | 39.363 | 4.086 |
| | | FLIR Tools+ | 42.5 * | 38.4 * | 39.3 * | 4.1 |
| FLIR0012 | original | computed | 38.073 | 34.934 | 36.769 | 3.138 |
| | | FLIR Tools+ | 38.0 * | 34.9 | 36.7 * | 3.1 |
| FLIR0012 | FLIR Tools+ edit | computed | 37.796 | 37.882 | 36.687 | −0.086 |
| | | FLIR Tools+ | 37.8 | 37.9 | 36.7 | −0.1 |
| FLIR0012 | Word edit | computed | 37.870 | 38.256 | 36.405 | −0.386 |
| | | Word | 37.8 * | 38.2 * | 36.4 | −0.4 |
| FLIR0013 | original | computed | 34.030 | 33.979 | 33.958 | 0.051 |
| | | FLIR Tools+ | 34.0 | 34.0 | 33.9 * | 0.0 * |
| FLIR0013 | FLIR Tools+ edit | computed | 33.967 | 34.290 | 34.098 | −0.323 |
| | | FLIR Tools+ | 34.0 | 34.3 | 34.1 | −0.3 |
| FLIR0014 | original | computed | 36.995 | 38.965 | 36.319 | −1.970 |
| | | FLIR Tools+ | 37.0 | 38.9 * | 36.4 * | −2.0 |
| FLIR0014 | FLIR Tools+ edit | computed | 40.128 | 39.463 | 36.448 | 0.665 |
| | | FLIR Tools+ | 40.1 | 39.4 * | 36.4 | 0.7 |

The mismatches go both ways, from −0.081 to +0.073, so they are not a fixed offset or one rounding convention (C4). The owner notes that FLIR keeps many decimals internally. The likely cause is a detail of FLIR's internal arithmetic that the public model does not reproduce, such as float precision or a lookup table. That cause is not tested.

### What the pipeline would need from the operator

1. Edit the spots and area in FLIR Tools+ (or the Word viewer) and save the image, so that its MeasurementInfo holds the final positions (C1).
2. Keep the labels `Sp1`, `Sp2` and one area. The reader matches by label (C7).
3. Use a box or a polygon for the area. Ellipse areas are not covered by these samples.
4. Accept ±0.1 °C against FLIR's display, or wait for an answer to open question 1.

## Disputed

None. One Path.

## Open questions

1. Can FLIR's exact displayed digits be obtained? Two candidates: reading the value panel FLIR Tools+ draws into the picture (C9), or finding the arithmetic detail behind C4.
2. Where is the absolute-`Dt` tick stored (C11)?
3. Do other cameras in use share the layout (C12)?
4. Does a per-tool emissivity or distance set in FLIR Tools+ live in the tools' trailing bytes, and does it change the values? The samples use the global parameters only.
5. What is the 8-byte `0x29` record that a FLIR Tools+ save adds?
6. How was the Word-edited FLIR0012 image saved out of the viewer? The answer decides whether a delivered Part's viewer state can be read the same way.

## How to reproduce

From a clean worktree, with the samples folder below in place:

```
S=<Integration Branch worktree>/scratch/235-flir-values-without-word/samples
E=docs/research/235-flir-values-without-word/evidence
uv run --frozen python -I $E/compare_readings.py "$S"
uv run --frozen python -I $E/hypotheses.py "$S"
uv run --frozen python -I $E/search_stored_values.py "$S"
uv run --frozen python -I $E/check_edit_preserves_raw.py "$S"
uv run --frozen python -I $E/flir_fff.py "$S/original/FLIR0011.jpg"
```

The logs in `evidence/` were captured with the system Python 3.13.1, numpy 2.3.2 and Pillow 11.3.0. `compare_readings.py` under `uv run --frozen` (numpy 2.5.1, Pillow 12.3.0) prints the same summary line.

## Live data read

`<SAMPLES>` is `scratch/235-flir-values-without-word/samples/` in the Integration Branch worktree, a folder git ignores. The owner placed the files there on 2026-11-13. `IR-readings.csv` is an Excel workbook despite its extension.

| Path | File | Bytes | SHA-256 | Read on |
|------|------|-------|---------|---------|
| `<SAMPLES>/original/` | `FLIR0011.jpg` | 1296458 | `388b17dc65edf3ad01a5e04bcf49568fec0929479f933289cf247a172bd28e00` | 2026-11-13 |
| `<SAMPLES>/original/` | `FLIR0012.jpg` | 1564246 | `08ce5a7362d70ce11f0f9a6731ce07d470c87632dae0db8203a9674ad0f66a9c` | 2026-11-13 |
| `<SAMPLES>/original/` | `FLIR0013.jpg` | 914461 | `3ea10ae5c331043849a8bc2ee3bc0d061a3366c517f445ae35a58923f914eac2` | 2026-11-13 |
| `<SAMPLES>/original/` | `FLIR0014.jpg` | 1788758 | `fde4c4b26722a3479b94d5cbdc20c73df7425de56acfa9c14503c946a2933eca` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0011.jpg` | 1296458 | `ee18948e9f83c80970562b0f6aa936138e5a5cef61edd1d6f89dac5cd6eab828` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0012-editted-from-Software-FlirTools+-directly.jpg` | 944147 | `225adcfb82fdfdf9dbb9e4f758e3867d6d6d26448fd4682a49b7266146e6c617` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0012-editted-in-word-using-FlirTools+-CIRViewer.jpg` | 891086 | `dcf611c71e9597cdb19ad14a7973297fc85c10d52da9105844e03da02b9533d7` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0013.jpg` | 914461 | `e411a41636fcd856736bd26166d467df6e449c8acbc9e9f7bb538c7bb6b1117c` | 2026-11-13 |
| `<SAMPLES>/editted/` | `FLIR0014.jpg` | 1788758 | `b81dac1169250e8b9325650e1da0b93ffa5f7b9e531ecf601603f490d2a3ed7b` | 2026-11-13 |
| `<SAMPLES>/` | `IR-readings.csv` | 9125 | `9061d32effa57dab6e40448e453991c4425e1fa2a39b2648a7c1ced3acbfbe1e` | 2026-11-13 |

## Change log

- 2026-11-13: first version (Claude Code).
