---
ticket: 235
type: research
map: 221
path: atlas-sdk
status: open
updated: 2026-11-13
agent: Claude Code, claude-opus-5-5
---
# Can the IR table values be read from a saved FLIR image without Word?

## Question for this Path

Can the four values be read by FLIR's Atlas SDK from the saved image, and do they match the values Word shows?

## Verdict

Yes, with heavy runtime conditions. The Atlas image library installed with FLIR Tools opens every one of the 18 saved images from both cameras, with no Word and no FLIR Tools+ window (C1). Its values match the owner's readings to the digit in all 40 values read after an edit, in FLIR Tools+ and in Word (C2). That includes per-tool emissivity, image-level emissivity and distance changes, boxes, polygons and ellipses. The six misses are the camera's burned-in original figures, which FLIR's desktop software does not reproduce either (C2).

The conditions are:

- **32-bit only.** It runs only in a 32-bit process. A 64-bit process cannot load it (C3).
- **FLIR Tools must be installed.** Atlas is not installed on its own (C4).
- **Licence unknown.** The terms for calling Atlas from a pipeline are not settled (C9).
- **No absolute `Dt`.** Atlas has no absolute mode, so the pipeline still applies `abs()` (C7).
- **No delivered reports.** Atlas measures image files, not the viewers in a delivered report (C8).

Atlas and the pure-Python reader of `path-file-read.md` give the same figures to 0.000003 °C on 85 of 87 values (`path-file-read.md` C13). So Atlas's main use here is as FLIR's own reference. It is what found the reader's atmosphere model (C5) and its ellipse rules (C6).

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | `Flir.Atlas.Image.ThermalImageFile` opens all 18 sample files, 4 T440 originals, 4 T440 edits, 4 T640 originals and 6 T640 edits. It returns their spots, rectangles, ellipses, polygons and deltas with values, from a 32-bit PowerShell, with no Word and no FLIR Tools+ window. | Tested | `evidence/atlas-sdk/atlas_values.ps1`, `evidence/atlas-sdk/atlas-values-2026-11-13d.log` |
| C2 | Atlas's values equal the owner's readings to one decimal in 62 of 68 values. That counts the two Word absolute-`Dt` ticks as `abs()` and the owner's corrected FLIR0012 `Dt` (`path-file-read.md` C7). All 40 values read after an edit match. The 6 misses are in the original column, which the owner read from the camera's burned-in panel (`path-file-read.md` C16). They are the same 6 as the reader's. | Tested | `evidence/atlas-sdk/compare_atlas_to_readings.py`, `evidence/atlas-sdk/compare-atlas-to-readings-2026-11-13.log` |
| C3 | Atlas runs only in a 32-bit process. Its assemblies are x86 (PE machine 0x014C, processor architecture X86). Loading `Flir.Atlas.Image.dll` from 64-bit PowerShell fails with `BadImageFormatException`. The project's Python is 64-bit (`path-file-read.md` C10), so a pipeline would have to start a separate 32-bit process. | Tested | `evidence/atlas-sdk/atlas-values-64bit-2026-11-13.log`, `evidence/atlas-sdk/atlas_install.ps1`, `evidence/atlas-sdk/atlas-install-2026-11-13.log` |
| C4 | Atlas is the copy inside FLIR Tools: `Flir.Atlas.Image.dll`, assembly version 2.0.14266.1000, file version 4.1.17018.1001, in `FLIR Tools\bin`. No separate SDK is installed. The scripts load it by path, with an `AssemblyResolve` handler that maps dependency names to that folder and guards against re-entering itself. | Read | `evidence/atlas-sdk/atlas-install-2026-11-13.log`; `evidence/atlas-sdk/atlas_values.ps1` lines 2 to 9 |
| C5 | Atlas's own figures settled the reader's temperature model. Its transmission is the one-path model, and its `GetValueFromSignal` curve is what the reader now reproduces to 0.000001 °C. | Tested | `path-file-read.md` C14; `evidence/atlas-sdk/atlas_curve.ps1`, `evidence/atlas-sdk/atlas-curve-2026-11-13.log` |
| C6 | Atlas exposes each measurement's pixels and parameters, which settled the reader's ellipse and per-tool rules. `MeasurementEllipse.GetValues()` lists an ellipse's pixel values in its own order. `ThermalParameters` on a measurement reports `UseCustomObjectParameters` True, with emissivity 0.8, for the two spots of the Word ellipse save. On the T440 emissivity and distance edits it reports False, with the image's new values. | Tested | `evidence/atlas-sdk/atlas_ellipse_pixels.ps1`, `evidence/atlas-sdk/atlas-ellipse-pixels-2026-11-13d.log`, `evidence/atlas-sdk/atlas_tool_params.ps1`, `evidence/atlas-sdk/atlas-tool-params-2026-11-13.log`; `path-file-read.md` C19, C23, C24 |
| C7 | Atlas's delta has no absolute mode. Its sign follows tool numbers, which FLIR Tools+ shows too: +0.086 for the FLIR0012 edit whose tool 1 is labelled `Sp2`. The absolute tick belongs to FLIR Word Reporting's formula field. | Tested | `path-file-read.md` C7 and C17; `evidence/atlas-sdk/reflect_delta_model.ps1`, `evidence/atlas-sdk/reflect-delta-model-2026-11-13.log`, `evidence/atlas-sdk/find_absolute_strings.py`, `evidence/atlas-sdk/find-absolute-strings-2026-11-13.log` |
| C8 | The Atlas assemblies installed offer no way to read a viewer in a Word file. `Flir.Atlas.DocXEngine.dll` exports no public types. `Flir.Atlas.DocXEngine.ProxyObjects.dll` holds report-template objects (`Spot`, `Delta`, `IR`, `Photo.CopyFromIR(ThermalImageFile)`) for building a report from image files. A delivered report is read by the file-read route (`path-file-read.md` C25 to C27). | Read | `evidence/atlas-sdk/reflect_docx_engine.ps1`, `evidence/atlas-sdk/reflect-docx-engine-2026-11-13.log` |
| C9 | A pipeline may call the Atlas copy inside FLIR Tools on the operators' machines. | Assumed | none. The install holds no Atlas licence. `licenses.html` covers third-party components only and does not mention Atlas, and FLIR Tools carries its own `Flir.LicenseCheck.exe` (`evidence/atlas-sdk/atlas-install-2026-11-13.log`). Settled by FLIR's licence terms for the Atlas SDK, or by FLIR. |

## Detail

### Atlas against the pure reader

| | Atlas SDK | Pure-Python reader (`path-file-read.md`) |
|---|---|---|
| Needs | FLIR Tools installed, 32-bit process | numpy and Pillow, already locked |
| Process | 32-bit PowerShell or .NET | the project's 64-bit Python |
| Saved images | yes, all 40 edited readings (C2) | yes, all 40 (`path-file-read.md` C15) |
| Stretched ellipse | FLIR's own figure | 0.009 °C off (`path-file-read.md` C23) |
| Delivered report | no (C8) | yes (`path-file-read.md` C25 to C27) |
| Absolute `Dt` | applied by the pipeline (C7) | stored in a report's viewer; applied by the pipeline for an image |
| Licence | not settled (C9) | none needed |

### How the runs were made

Every Atlas script loads `Flir.Atlas.Image.dll` from `FLIR Tools\bin` into 32-bit Windows PowerShell 5.1, opens each image as a `ThermalImageFile`, sets Celsius and reads its `Measurements`. Nothing is written back to the images.

## Open questions

1. May a pipeline call FLIR Tools' Atlas copy (C9)?
2. Does Atlas need FLIR Tools+'s licence to be active? `Flir.LicenseCheck.exe` was not run, and every Atlas call here succeeded on a licensed machine.

## How to reproduce

FLIR Tools must be installed. From a clean worktree, with the samples folder of `path-file-read.md` in place:

```
S=<Integration Branch worktree>/scratch/235-flir-values-without-word/samples
A=docs/research/235-flir-values-without-word/evidence/atlas-sdk
PS32=C:/Windows/SysWOW64/WindowsPowerShell/v1.0/powershell.exe
$PS32 -NoProfile -ExecutionPolicy Bypass -File $A/atlas_values.ps1 -samples "$S" > atlas-values.log
uv run --frozen python -I $A/compare_atlas_to_readings.py "$S" atlas-values.log
$PS32 -NoProfile -ExecutionPolicy Bypass -File $A/atlas_tool_params.ps1 -samples "$S"
$PS32 -NoProfile -ExecutionPolicy Bypass -File $A/atlas_install.ps1
$PS32 -NoProfile -ExecutionPolicy Bypass -File $A/reflect_docx_engine.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $A/atlas_values.ps1 -samples "$S/Flir T640/original"
```

The last line is the 64-bit run of C3, expected to fail. The scripts and logs that the reader comparison uses are listed in `path-file-read.md`.

## Live data read

The sample files and the owner's readings in `path-file-read.md` Live data read, as of its 2026-11-13 21:07 state. No other live file was read.

## Change log

- 2026-11-13: first version (Claude Code). The owner reinstated this Path on 2026-11-13 after first reading "Atlas SDK" as something unrelated to IR. It consolidates the Atlas work that the file-read Path had used as a reference: the scripts and logs moved from `evidence/atlas/` to `evidence/atlas-sdk/`. New runs: Atlas against the owner's readings (C2), the 64-bit load (C3), the install (C4, C9), per-tool parameters (C6) and the DocX engine (C8).
