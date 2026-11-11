---
ticket: 223
type: research
map: 221
path: flir-tools
status: open
updated: 2026-11-11
agent: Codex (original work); Claude Code, claude-fable-5-2 (conversion)
---
# Can FLIR's own installed tools or SDK clone or rekey a viewer?

## Question for this Path

Does any FLIR library installed on this machine expose a way to create an independent copy of a viewer, or to give an existing one new identities, without going through Word?

## Verdict

No public one-call clone or rekey was found (C2 to C5). The libraries do hold useful building blocks: SDK persistence, thermal image copy and a docx engine (C2, C7, C8). Using them would need a 32-bit worker process, and that experiment has not been run (C11).

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | `ReporterSDK.dll` is `IRSDK.IRSDK.1`, CLSID `{86C41763-1346-4B91-8F9B-B0885A9F5C28}`. All five native servers are x86 and registered only in the 32-bit registry view. | Read | The DLLs' type libraries and HKCR, as recorded in `evidence/flir-tools/original/flir-native-api-surface.md`. The reader script was not kept. |
| C2 | `IIRSDK` exposes `GetID`, `PersistStreamLoad` and `PersistStreamSave`. It has no `SetID`, `NewID` or whole-object `Clone`. | Read | same type-library record |
| C3 | `IIRViewer` exposes only resize, toolbar and control-size settings. | Read | same type-library record |
| C4 | `ChangeObjectID`, `UpdateIRSDKID` and `ChangeBookmark` exist in native code and are not on the default public interfaces. | Read | Static disassembly and the type libraries, recorded in `evidence/static-cfb/original/flir-binary-implementation-notes.md` and `evidence/flir-tools/original/flir-native-api-surface.md` |
| C5 | `IWordAddin` exposes `AnalyzeTemplate`, `CreateReport`, `CreatePreview`, `StartCreatingReport` and `EndCreatingReport`. It has no page duplicate or viewer clone. | Read | same type-library record |
| C6 | `WizardClassLibrary.WordApp` has `StartApp`, `AnalyzeTemplate`, `CreateReport`, `CreateTemplatePreview`, `CloseWordApp` and `KillWordApp`. | Tested | `evidence/flir-tools/inspect_flir_managed_apis.ps1`, `evidence/flir-tools/flir-installed-tools.inventory.json` |
| C7 | `Flir.Atlas.Image` 2.0.14266.1000 exposes `ThermalImageFile` open and save, `ThermalImage.Copy` and measurement copy. | Tested | same script and inventory |
| C8 | `Flir.Atlas.DocXEngine` exposes `DocXContext`, `DocXBuilder`, `IdHelpers`, `DocXOLEExtractor`, `ReportProcessing.Flatten` and `Cleanup`, and references no Office interop assembly. | Tested | same script and inventory |
| C9 | The Atlas WPF and Reporting assemblies could not be loaded for inspection. | Tested | the `Errors` key of the same inventory |
| C10 | The Reporter manual, sections 7.1.5 and 15.7, says a field connects to a chosen viewer and shows its values. It documents no private bytes. | Read | `Reporter-9.en-us.pdf` in the FLIR Word Reporting install, SHA-256 `eeded0fa986cf5f649e289ca221d34f46f5c9ddd504b2947d9964ade50ed98d8` |
| C11 | A standalone 32-bit worker that loads a viewer's SDK archive, takes a fresh `GetID` and saves it could yield an independent SDK state. | Assumed | none. The original calls it "a hypothesis to test". Settled by building that worker and comparing the saved archive. |
| C12 | Native SDK persistence would not regenerate the outer object UUID, the field UUIDs, the compressed bookmarks, the body fields, the settings, the previews or the relationships. | Assumed | none. Inferred from C2 and the layout in `path-static-cfb.md`. |
| C13 | The Word-driving wizard of C6 needs Word to run. | Assumed | none. Inferred from diagnostic strings in the assembly. |
| C14 | `Flir.Atlas.Image` cannot by itself write a viewer container. | Assumed | none. Inferred from the absence of such a method in C7. |

## Detail

The interface listings, with every method signature, are in `evidence/flir-tools/original/flir-native-api-surface.md`. The assessment of each tool as an option is in `evidence/flir-tools/original/flir-installed-tools-options.md`.

| Library | What it offers | What it lacks |
|---|---|---|
| `ReporterSDK.dll` (`IIRSDK`) | Read the SDK ID, load and save SDK state through a stream pointer | Set a new ID, clone |
| `IRViewer` control | Display settings | Clone, ID setter |
| FLIR Word add-in (`IWordAddin`) | Template analysis and report creation through Word | Page or viewer duplicate |
| `WizardClassLibrary` | Report creation by driving Word | Any path without Word |
| `Flir.Atlas.Image` | Open, copy and save thermal images and measurements | Writing a viewer container |
| `Flir.Atlas.DocXEngine` | Docx building blocks, OLE extraction, flatten and cleanup | A demonstrated viewer clone. Flatten removes the editable viewer. |

## Open questions

1. Does the SDK object need an ActiveX site or a running Word to save its state?
2. Are there licence checks on the SDK outside Word?
3. Would a fresh SDK ID from `GetID` be accepted by a viewer whose other identities were set by hand?

## How to reproduce

```
powershell -File docs/research/223-flir-xml-join/evidence/flir-tools/inspect_flir_managed_apis.ps1 -AssemblyPath <dll> -OutputPath <json>
```

It reflects over one managed assembly without calling it and writes JSON. The inventory is that output for the installed FLIR assemblies. The type-library reads behind C1 to C5 used a `LoadTypeLibEx` reader that was not kept, so they cannot be rerun from this folder.

## Live data read

None. The inputs are the FLIR programs installed under `Program Files (x86)\FLIR Systems\`, with their paths and hashes in the inventory.

## Change log

- 2026-11-11: converted from the two Codex write-ups, kept unchanged in `evidence/flir-tools/original/` (Claude Code).
