# Installed native FLIR API surface: #223 follow-up

Date: 2026-11-11. Investigator: **Codex — Static/CFB investigation**. This is metadata research in `research/flir-activex-xml-join`, not a native runtime proof. No Word or FLIR class was activated, no SDK/viewer instance was created, and no source document was written.

**Finding:** installed FLIR components expose useful image/analysis persistence and rebinding operations. Those are credible ways to let FLIR serialize its own data. The inspected public APIs do **not** expose a demonstrated one-call clone/rekey operation for a complete legacy viewer, its windowless Word fields and their bindings. A native SDK experiment is worth investigating before writing a general proprietary-format writer; it still needs to establish lifecycle and full legacy-container preservation.

## Method and exact installed sources

Embedded type libraries were read with Windows `oleaut32.LoadTypeLibEx(full_path, REGKIND_NONE=2)` through `ctypes`, then inspected through `ITypeLib` metadata. The installed pywin32 does not expose `LoadTypeLibEx`, so the Windows function was used directly. This disables type-library registration; it does not instantiate any described class. [Microsoft LoadTypeLibEx](https://learn.microsoft.com/en-us/windows/win32/api/oleauto/nf-oleauto-loadtypelibex), [ITypeLib metadata](https://learn.microsoft.com/en-us/windows/win32/api/oaidl/nn-oaidl-itypelib)

The source DLLs and SHA-256 values are recorded in [the implementation evidence](flir-binary-implementation-notes.md#sources-and-reproducibility). Native type-library reading was cross-checked against reflection-only `Interop.IRSDKLib.dll` and `Interop.IRViewer.dll` declarations. Read-only registry inspection checked `HKCR/CLSID` and `HKCR/Interface` in the 32-bit and 64-bit views. A registration is evidence of an installed server, not a successful creation or licensing test.

All five inspected native servers have PE machine `0x014c` (x86), and their relevant CLSIDs are registered only in the inspected 32-bit registry view. They are in-process DLL servers under `C:/Program Files (x86)/FLIR Systems/FLIR Word Reporting/bin/`. A runtime experiment needs an appropriate 32-bit host/helper; the fact that a 64-bit process can read their type libraries does not make it able to load the native servers in-process.

| Server / ProgID | CLSID | Primary interface IID |
| --- | --- | --- |
| `IRSDK.IRSDK.1` / `ReporterSDK.dll` | `{86C41763-1346-4B91-8F9B-B0885A9F5C28}` | `IIRSDK` `{F85B21D1-D2BD-4692-A406-0E87E51FB677}` |
| `IRViewer.IRViewer.1` / `IRViewer.dll` | `{C5F5764B-B932-4F33-8BF3-9941F22FAE18}` | `IIRViewer` `{3287C5C6-E282-400C-B364-3AE92C47662B}` |
| `IRField.IRField.1` / `IRField.dll` | `{4ED60E11-74A9-4EFF-B441-0E4862035794}` | `IIRField` `{7FFF5A42-48FB-4FF9-80C1-3FF58CC4DD00}` |
| `IRFieldTableKeeper.IRFieldTableKeeper.1` / `IRFieldTableKeeper.dll` | `{AE28702B-E0F7-4DA6-827F-45D47652EDBA}` | `IIRFieldTableKeeperObject` `{E056EDFD-B72C-44A6-85EA-FEC0F8BE6C6D}` |
| `IRSDKConnection.IRSDKConnection.1` / `IRSDKConnection.dll` | `{B5027D32-1BB5-4CED-AD22-DFA9F646ED3F}` | `IIRSDKConnection` `{74D2EEC6-A1FC-4C8A-B0D7-4FAA42B8BC15}` |

## Public operations actually found

The following are automation-facing declarations read from the installed type information. `LONG` is 32-bit, `BSTR` is a COM string, `IUnknown*` is an interface pointer. These are declarations, not tested Python call examples.

### Native SDK: useful serialization, no exposed SDK-ID setter

```text
IIRSDK.GetID() -> GUID
IIRSDK.PersistStreamLoad([in] LONG* pStream, [in] LONG* pPropMap) -> LONG
IIRSDK.PersistStreamSave([in] LONG* pStream, [in] LONG fClearDirty,
                        [in] LONG* pPropMap) -> LONG
IIRSDK.GetVersion() -> BSTR
IIRSDK.AnnounceDirty() -> void
IIRSDK.HWNDForUpdates [put LONG]
```

There is no `SetID`, `NewID` or whole-object `Clone` in this inspected `IIRSDK` interface. **The stream parameters are pointer-shaped 32-bit declarations, not filenames or ordinary byte arrays.** Managed interop likewise exposes `Int32 ByRef`. The correct native stream/parameter-map contract must be established in a suitable host; blindly passing an integer or a Python file path would not be a justified invocation.

Other interfaces implemented by the SDK include:

```text
IImage ({3BF8B615-D92E-4FA0-815A-666842421B8C}):
  Open([in] BSTR sPath) -> LONG
  Save([in] BSTR sPath, [in] SHORT nFileType) -> LONG
  Identifier [get LONG]
  GroupID [get BSTR]

IMeasurement ({3F64053A-B5B6-4C13-9223-29F6BFAC726D}):
  AddClone([in] IStream* pANAToClone, [out] LONG* pAnaId) -> LONG
  CreateUniqueLabel([in] MeasurementTypes nType, [out] BSTR* pstrLabel) -> LONG
  GetFirstID([out] LONG* lID) -> LONG
  GetNextID([out] LONG* lID) -> LONG
  GetLabel([in] LONG lID, [out] BSTR* pstrLabel) -> LONG
  SetLabel([in] LONG lID, [in] BSTR strLabel) -> LONG
```

`AddClone` takes an analysis-object stream and returns an analysis ID. Its name is **not evidence of a complete viewer/container clone**, and a unique measurement label is not an independent SDK GUID or Word field binding. `IImage.Identifier` is a read-only numeric image property, distinct from `IIRSDK.GetID()`'s GUID.

### Viewer versus field interface

The published default `IIRViewer` interface only exposes resize, toolbar and control-size settings. It exposes no whole-viewer clone, SDK setter or ID setter. The implementation contains standard `IPersistStorage`/`IPersistStreamInit` support, but those are separate native COM interfaces, not methods on the default automation interface. A custom host could investigate loading/saving through those standard interfaces; this research has not tested their availability or whether a viewer needs a site/container/add-in initialized first.

The published field interface does provide:

```text
IIRField.IRSDK [get/put IUnknown*]
IIRField.WordApplication [put IUnknown*]
IIRField.Add() -> LONG
IIRField.AdviseIRSDK() -> void
IIRField.ShowPopup() -> void
```

This confirms a declared SDK rebinding surface for a field. Its explicit WordApplication property also shows that Word-side operations are part of this API; it does not establish a Word-free field-authoring route. Methods discovered earlier in native diagnostics, such as `ChangeObjectID`, `UpdateIRSDKID` and `ChangeBookmark`, are **not exposed by the inspected default interfaces**. They cannot be promoted to supported automation calls based on diagnostic strings alone.

The private-looking `IIRControl` IID `{59DC16D2-306D-4EFA-A901-F554A091B75C}` occurs in native RTTI, but no definition was found in these inspected type libraries or corresponding 32-bit Interface registration. Reconstructing and calling that vtable would itself be an undocumented-interface experiment.

### Shared registries and field persistence

The connection interface publicly declares GUID lookup/registration:

```text
IIRSDKConnection.StoreIRSDK([in] GUID* pIRSDK_ID,
                           [in] IUnknown* pIRSDK_Instance) -> void
IIRSDKConnection.GetIRSDK([in] GUID* pIRSDK_ID,
                         [out] IUnknown** ppIRSDK_Instance) -> void
IIRSDKConnection.Associate([in] GUID* pIRSDKGUID, [in] IUnknown* pIFD) -> void
IIRSDKConnection.Clear() -> void
```

Those methods manage registry associations; they are not declarations that the SDK object's own persisted ID has changed. Clearing a shared registry is not a substitute for independent persisted identities.

The keeper interface exposes `SaveWindowlessIFDsWithSameIRSDK(BSTR IRSDKID, IUnknown* pStream) -> LONG`, `KeepWindowlessIFD(BSTR objectID, IUnknown* pObject, IUnknown* pIRSDK, IUnknown* pStream, IUnknown* pIIRControl) -> LONG`, `RestoreWindowlessIFDs(LONG final) -> LONG`, and Word/add-in object storage/retrieval. These are relevant to native field persistence but require already meaningful native objects, streams and control/Word relationships. No documented full detached-clone workflow follows merely from the signatures.

### Word add-in surface

`WordAddin_O2k7.dll` exposes `IWordAddin` `{B244D406-6366-433D-8606-92880BFAAF42}` with `AnalyzeTemplate(BSTR TemplateFileName, BSTR ResultFileName)`, `CreateReport(BSTR xmlReport)`, `CreatePreview(BSTR TemplateFileName, BSTR ResultFileName)`, `StartCreatingReport()` and `EndCreatingReport(IUnknown* pDoc)`, plus ribbon callbacks. There is no explicit `DuplicatePage`/whole-viewer clone method in that inspected automation interface. A native duplicate-page action seen in diagnostics is not itself an exposed API contract. This add-in surface belongs to the Word reporting route; it cannot presently be treated as a Word-free helper.

## What to test later, using FLIR itself

A narrowly scoped native candidate is to create a **fresh SDK**, record its native `GetID()`, load a source SDK archive through native persistence, and compare `GetID()` before/after loading. If the fresh ID survives while image/analysis state is restored, FLIR could handle that payload instead of a custom SDK archive writer. That is a hypothesis to test, not an observed result. It must then be possible to bind an independent viewer and its fields to that SDK and save the **complete legacy R8/ActiveX container** with coherent object and Word bookmark identities.

Native SDK persistence alone addresses only one layer. It does not automatically regenerate the outer viewer UUID, child field UUIDs, compressed field bookmarks, DOCVARIABLE instructions/settings, preview/placement, or package relationships. A future experiment must show those are handled by a native container/rebinding workflow or explicitly preserved correctly.

Other unresolved conditions are standalone ActiveX-site requirements, possible Word/add-in dependencies during creation or save, installed component compatibility, license behavior and runtime registry lifecycle. Static registration and metadata do not settle any of these. No runtime probe was conducted because the current scope remains research, Word COM is reserved for the owner's heavy test, and the owner planned any prototype for a separate session.
