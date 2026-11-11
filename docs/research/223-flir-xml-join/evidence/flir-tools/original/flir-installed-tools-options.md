# Using the installed FLIR tools for #223

Date: 2026-11-11. Investigator: **Codex — Static/CFB investigation**, branch `research/flir-activex-xml-join`. This continues the owner's question about using FLIR's own tools instead of implementing the entire binary format. Word and native FLIR objects were not activated; inspection used assembly/type-library metadata, files, read-only registration queries and first-party documentation.

## Practical assessment

**Yes, FLIR's own libraries provide useful building blocks.** The strongest next experiment for the existing CIRViewer templates is a standalone, 32-bit native SDK worker that lets FLIR load/save its own image and analysis state. The full legacy viewer wrapper and Word field bindings still require separate handling; no complete public clone/rekey method was found. The SDK experiment is proposed here, not executed.

| Installed route | Useful capability | Remaining boundary |
| --- | --- | --- |
| Legacy `ReporterSDK.dll` / `IRSDK.IRSDK.1` | Native image/measurement operations, SDK GUID retrieval and stream persistence. | No public full-viewer clone or SDK-ID setter found. Prove fresh identity survives native loading, then handle the R8 wrapper and fields. |
| Legacy viewer / field / keeper objects | Control persistence may be available through standard COM interfaces; fields expose SDK association. | Their published default interfaces do not expose the private identity-change operations found in disassembly. Field methods can explicitly require a Word application. |
| `WizardClassLibrary.dll` / `RapidReportCreator.exe` | Native report generation and template analysis; prior local notes record a successful image-insertion proof. | This route starts/automates Word. It consumes Word availability and does not establish a Word-free compiler. |
| `Flir.Atlas.Image.dll` | `ThermalImageFile.Open/Save`, thermal-image copying and measurement copying. | Useful for image/analysis work; it does not by itself serialize legacy CIRViewer containers or their linked Word fields. |
| `Flir.Atlas.DocXEngine.dll` / Report Studio | OpenXML document contexts, report building, object IDs, state extraction and cleanup. | This is a newer report/template system. FLIR documents legacy templates as incompatible; local metadata also has unresolved dependencies. Treat it as a migration investigation. |

The native interfaces, GUIDs, signatures and registration evidence are recorded in [the native API inventory](flir-native-api-surface.md). The managed assembly facts below are reproducible with [the reflection-only inspector](../../scripts/research/inspect_flir_managed_apis.ps1) and summarized in [the installed-tools inventory](flir-installed-tools.inventory.json). Method presence establishes an API surface, not tested behavior or a supported automation contract for internal shipping assemblies.

## Native SDK: the candidate that preserves the existing format

The registered SDK is **32-bit**, ProgID `IRSDK.IRSDK.1`, CLSID `{86C41763-1346-4B91-8F9B-B0885A9F5C28}`. `IIRSDK` exposes `GetID`, `PersistStreamLoad` and `PersistStreamSave`. Its image and measurement interfaces include image opening and analysis-item cloning. `IMeasurement.AddClone` clones an analysis item, not an entire viewer/document. The raw persistence signatures use legacy pointer-shaped parameters; a helper must marshal those correctly rather than treating them as a modern managed Stream overload. [Native API inventory](flir-native-api-surface.md)

A useful future probe would create a fresh SDK, record its GUID, load the isolated SDK archive identified in [the binary anatomy report](flir-binary-anatomy.md), record the GUID again, and save it to a new memory stream. Check image/analysis state and identity behavior with a second independent SDK instance. This could delegate the complex SDK-state format to FLIR while limiting custom code to the outer package, R8 identities and Word bindings.

That probe must first establish which exact stream framing and property-map parameters native persistence expects. It must also establish whether loading retains a fresh SDK identity; `GetID` alone does not prove it. Even a successful SDK round trip would not establish independent viewer/field behavior inside Word. No runtime probe is performed while the owner is using Word for heavy testing.

## The existing reporting helper uses Word

Reflection-only inspection finds these overloads on `WizardClassLibrary.WordApp`:

```text
StartApp()
AnalyzeTemplate(string templateFile, string infoFile, out bool wordAddinFound)
CreateReport(string reportFile, out bool wordAddinFound)
CreateTemplatePreview(string templateFile, string previewFile, out bool wordAddinFound)
CloseWordApp()
KillWordApp()
```

The same installed assembly contains `Word.Application`, `winword` and native add-in lookup/registration diagnostics. `RapidReportCreator.exe` contains diagnostics for starting Word, finding `WordAddin_O2k7.dll`, and registration. It was inspected as bytes; even its help/startup path was not executed. FLIR's [reporting-error documentation](https://www.flir.com/support-center/instruments2/why-do-i-get-a-critical-error-when-creating-a-microsoft-word-report-using-flir-tools-or-flir-reporter/) likewise identifies the Word add-in as part of this report-processing route.

The existing local `flir-ir-image-insertion.md` investigation records successful native generation through this helper, but deferred temperature-field correctness and reliable session ownership. That file was already untracked and is not added or modified by this research. The prior proof should not be represented as a complete compiler or field-refresh proof.

## Managed Atlas image APIs

The installed `Flir.Atlas.Image` is version `2.0.14266.1000`. Reflection-only metadata exposes:

```text
ThermalImageFile()
ThermalImageFile(string filename)
ThermalImageFile.Open(string filename)
ThermalImageFile.Save()
ThermalImageFile.Save(string filename)
ThermalImageFile.Save(Stream targetStream, Bitmap overlay)
ThermalImage.Copy(ImageBase source)
MeasurementCollection.Copy(MeasurementCollection source)
MeasurementShape.Copy(MeasurementShape source)
```

These are useful native-library alternatives for radiometric image loading, analysis work and image-file persistence. They do not identify a complete legacy ActiveX-container writer or Word-side variable rebinding API. No image method or constructor was executed in this investigation.

## Newer DocXEngine / Report Studio

The installed `Flir.Atlas.DocXEngine` is also version `2.0.14266.1000`. It references `DocumentFormat.OpenXml`, `OpenXmlPowerTools`, Atlas image/WPF components and JSON libraries. No direct Office/Word interop reference appears in its inspected assembly reference list; that does not by itself prove every execution path is Word-independent.

Recovered APIs include:

```text
DocXContext(string path).Load() / Commit() / Release()
DocXContext.Document : DocumentFormat.OpenXml.Packaging.WordprocessingDocument
DocXBuilder.Build(TemplateAnalysis, List<DataSectionInfo>, string outputPath)
IdHelpers.CreateNewWordId(oldId, fieldNewUniqueId, fieldRefObjUniqueId)
IdHelpers.GenerateNewGuid()
DocXOLEExtractor.ExtractAll(docxPath, outputRoot)
ReportProcessing.Flatten(sourceFilePath, targetFilePath)
ReportProcessing.Cleanup(filePath)
```

`ReportProcessing.Flatten` is not an acceptable substitute for the required editable thermal viewers. The existence of `DocXOLEExtractor` does not establish a legacy CIRViewer importer: its compatibility has not been exercised or established from these signatures.

Its constants describe `FLIR_REPORTSTATE`, `ReportStates`, `Report.json`, `Container.json`, `FLIR_DOCUMENT_ID` and structured repeat/first/last sections. Those differ from the inspected legacy R8/CFB representation. More decisively, FLIR's [Tools+ 5.x versus 6.x comparison](https://flir.custhelp.com/app/answers/detail/a_id/1263) says the old Word templates require recreation for Report Studio. The [Report Studio manual](https://support.flir.com/docdownload/assets/web/27eh/en-us/) distinguishes radiometric editable reports from compressed/flat output. Those distinctions must be preserved when considering an alternative toolchain.

Reflection could not resolve `Flir.Atlas.Wpf`, `Flir.Atlas.Wpf.UI`, `Flir.Reporting.Common` and related types for all inspected methods. Those files were not found in the FLIR installation, Common Files or GAC locations searched. This is a concrete dependency uncertainty, not a runtime failure claim: no report generator was started. A working newer engine would still need template/content migration and behavior comparisons for operator-owned existing Parts.

The current Atlas developer program's [official hub](https://flir.custhelp.com/app/answers/detail/a_id/4680/~/flir-atlas-desktop-sdk---developer-hub) gates detailed resources behind an approved developer account. Current SDK documentation must not be assumed to match these installed version-2 assemblies.

## Recommendation and validation

For #223, investigate the standalone native SDK route first if the goal remains preserving existing legacy viewers and Parts. Treat modern Report Studio/DocXEngine as a separate alternative with explicit migration costs. Native Word-based generation of small objects remains another practical option when Word is available; it can reduce the work done in Word without eliminating it.

This session verified signatures, assembly versions/hashes, first-party format distinctions and registration without object activation. No report, template, DLL, registry entry or Office session was modified. No writer, generation workflow or runtime SDK prototype was implemented; #223 remains open.
