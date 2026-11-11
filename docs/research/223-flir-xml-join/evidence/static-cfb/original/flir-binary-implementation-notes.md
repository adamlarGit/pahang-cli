# FLIR binary implementation evidence for #223

Date: 2026-11-11. Investigator: **Codex — Static/CFB investigation**, implementation-inspection subtask. All observations below came from reading installed DLL/PDF bytes, static x86 disassembly, and reflection-only managed metadata. No Word, COM object, native FLIR object or application workflow was instantiated. The installed binaries were not changed. These notes complement the document-byte decoder; they are not a production architecture decision.

## Sources and reproducibility

The DLLs are installed under `C:/Program Files (x86)/FLIR Systems/FLIR Word Reporting/bin/`. SHA-256 identifies the exact local primary source; no vendor executable is added to this repository.

| Ref | File | SHA-256 |
| --- | --- | --- |
| S1 | `IRViewer.dll` | `af4646cc09b62afcea57b95d5eaa10fbeafb03c3c01b4920abc6ce32c39745d9` |
| S2 | `IRField.dll` | `a0c9b938ba95e552909d593fa7510173da0b5be994f5c2467e17276c7b1e904b` |
| S3 | `IRFieldTableKeeper.dll` | `1f978fa8b7e735de39f272a62a0ecf6dc64033b34ca1dcd84af4f410c2156813` |
| S4 | `IRSDKConnection.dll` | `6cff2e6e99918915b727a84473fb122fe0cd5d6341ceaf564fe1c2d833a1a31d` |
| S5 | `WordAddin_O2k7.dll` | `b84186172e0207ae7059efc09239db444d76fcdfc4a34095c64f6c6164648a96` |
| S6 | `Interop.IRSDKLib.dll` | `1197a4c07edbb4cabc1127e880cb2e8ea9c0956fdbb668fa443f0aa99bcbf4ec` |
| S7 | `ReporterSDK.dll` | `dc679a918aac9d79b1c82e68faabb70c525fc21ce7cc508d75926ebb1d5d7227` |

Disassembly used the already installed `C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/Llvm/x64/bin/llvm-objdump.exe`, with `--disassemble --x86-asm-syntax=intel --start-address=... --stop-address=...`. S1's preferred image base is `0x10000000`; the virtual addresses below are static image addresses, not observations from a running process. The disassembler labels broad ranges with the nearest exported symbol, `DllUnregisterServer`; that label is **not** the actual function name for each address. Names below are identified through references to embedded diagnostic strings.

Managed interop metadata was read with `[Reflection.Assembly]::ReflectionOnlyLoadFrom()` and `GetTypes()/GetMethods()`. This reads method declarations; none of the declared methods was called.

## Confirmed: separate shared-SDK and Word-field layers

S1 contains native serialization paths named `CIRViewer::SerializeEx`, `WindowlessIFD::CompoundStreamer::saveAllStates` and `readAllStates`, plus a separate `IPersistStreamInit` path referring to IRSDK stream persistence. The R8 version marker and `TAG_R8_FLD`, `TAG_R8_TBL`, `TAG_R8_STB`, `TAG_R8_END` identifiers are compiled into this native implementation. The tags distinguish field/table/summary-table state and terminate the windowless-object sequence; they are not a universal CFB header. [S1: diagnostic strings around file offsets `0xeb454–0xed230`, tag constants at `0x120d10–0x120d34`.]

S3's diagnostics explicitly describe two registries:

- `Helper Object Map: [SDKID]->(Bookmark, wlessIFD Object)*`, file offset `0x3965c`.
- `Object Map: [Bookmark]->(SDK ID, wlessIFD Object)`, file offset `0x396c4`.

The same DLL has a duplicate-bookmark diagnostic at file offset `0x39374`; methods save/drop windowless objects sharing an IRSDK, map summary tables to SDKs, and restore Word-side objects. Its RTTI includes `CComClassFactorySingleton<CIRFieldTableKeeperObject>`. S2 has separate operations `CIRField::ChangeObjectID`, `CIRField::UpdateIRSDKID` and `CWordField::ChangeBookmark`, plus native DOCVARIABLE field text. Thus object identity, shared SDK identity and Word-side field/bookmark identity are distinct implementation concepts. [S2: file offsets `0x69d78`, `0x6a738`, `0x6b364`, `0x7e298`; S3: method diagnostics `0x390d0–0x39d68`, singleton RTTI `0x43790`.]

S5 contains separate field/table saving policies and clipboard actions handling their Word-side bookmarks. That supports a native copy/paste path doing identity work beyond changing the visible control name. It does not establish that every Word operation always rekeys correctly. [S5: diagnostics `0xe1df0–0xe1ef0`, `0xe4fdc–0xe5044`.]

## Confirmed control flow: a viewer can reconnect to an existing SDK

S1's `IFDUtil::checkIRSDK` function begins at static VA `0x1004cc20`. Its observed control flow is:

1. Obtain the connection object, then call a GUID lookup with an output pointer (`0x1004cd12–0x1004cd34`).
2. Test whether the returned SDK pointer is null (`0x1004cd46–0x1004cd4a`).
3. If non-null, attach that existing SDK to the viewer (`0x1004ce1c–0x1004ce47`), on the path whose diagnostic names `put_IRSDK`.
4. If null, instantiate an SDK (`0x1004ce7a–0x1004cebb`), on the path whose diagnostic names `InstantiateIRSDK`.
5. Store the resulting SDK against the requested GUID (`0x1004cebd–0x1004cef7`), on the `StoreIRSDK` path.

S4 has get/store/associate operations keyed by IRSDK IDs and RTTI for `CComClassFactorySingleton<CIRSDKConnection>`. S6 declares `IIRSDK.GetID()` returning `System.Guid`, and stream-load/save methods. These independently support interpreting the lookup key as SDK identity, rather than a document relationship or shape name. [S4: diagnostic strings `0x2cf70–0x2d2c0`, singleton RTTI `0x35648`; S6: reflected `IRSDKLib.IIRSDK` metadata.]

**Inference supported by that code:** if a join preserves the same SDK GUID on two objects, the second viewer can attach to the first viewer's already registered SDK object even when each viewer has a different ZIP part, XML name and preview. This is a concrete candidate mechanism for shared image state and subsequent crosstalk. It is stronger evidence than assuming DOCVARIABLE sharing alone explains image changes. It remains an inference about joined-document behavior: no viewer was loaded during this investigation.

### Confirmed serialized GUID order

Static data flow through S1's `IFDUtil::writeR8Tags` establishes the prefix order as **version string, object-ID string, SDK-ID string, flag**:

- The caller at VA `0x1004d717–0x1004d738` passes a version string, its object-ID member, its flag member and the stream into the utility at `0x1004c800`.
- The utility obtains the SDK's GUID through the viewer and SDK interface calls at `0x1004c83b–0x1004c8a2`, then formats it into the SDK-ID output string at `0x1004c993–0x1004c9a4`.
- It constructs three by-value string arguments in reverse stack order at `0x1004c9cf–0x1004ca3e`: SDK ID, object ID, version. Three calls to the same stream writer at `0x1004ca47`, `0x1004ca56` and `0x1004ca65` consume version, object ID, SDK ID in that order. The subsequent flag write is at `0x1004ca71–0x1004ca89`.
- The diagnostic-building code at `0x1004cab7–0x1004cad1` independently labels the object-ID and IRSDK-ID string variables.
- The by-value string writer at `0x10038d50` calls `0x10036200`, which adds one to the string length, writes that as a four-byte integer, then writes the characters including their terminating NUL.

This matches the document-byte decoder's two UUIDs and the repeated second UUID across a viewer and its field records. It identifies the second persisted UUID as the SDK key, rather than merely guessing from repetition. It still does not locate every additional SDK-ID copy inside compressed payloads, prove every version uses the same record layout, or establish that rekeying only these visible copies is sufficient for a safe join.

## Confirmed: KENT framing has typed, length-bounded records

S1's parser at VA `0x10050b40` reads a ten-byte header. It checks the little-endian uint32 at header offset 2 against `0x4b454e54`, represented in bytes as `54 4e 45 4b` (`TNEK`). Its uint16 at offset 0 selects the record type. The uint32 at offset 6 is used as the data length for type `0x66`.

| Code | Static behavior |
| --- | --- |
| `0x64` (100) | Opens a nested record group. The skip routine recurses for this code. |
| `0x65` (101) | Closes the group; recursive skipping returns when it encounters this code. |
| `0x66` (102) | Reads a length-bounded data block immediately following the header. |

The paired writer at VA `0x10050d50` emits type `0x64` with zero header length; `0x10050d90` emits type `0x65` likewise; `0x10050dd0` emits type `0x66` and its data. The recursive skip routine is at `0x10050c60`. This structure is established from both reader and writer instructions, rather than merely finding a magic byte sequence. Other nearby paths use types `0x6b` and `0x6d`; their meanings are not established here. The same framing implementation occurs in multiple native FLIR modules and has `CMtxArchiveEx` RTTI. [S1: static VA ranges `0x10050b40–0x10050c90`, `0x10050d50–0x10050e35`; S2 and S7 have the same signature constants/RTTI.]

No implication follows that every `Contents` byte is a KENT record. The parent R8 framing, nested compressed object payloads and embedded image/analysis data remain separate layers.

## First-party manual cross-check

The installed manual `C:/Program Files (x86)/FLIR Systems/FLIR Word Reporting/Resources/en-us/Reporter-9.en-us.pdf`, SHA-256 `eeded0fa986cf5f649e289ca221d34f46f5c9ddd504b2947d9964ade50ed98d8`, is FLIR publication 1558567, revision 3020 (2012-03-29). Section 7.1.5, printed pages 20–21 (PDF pages 30–31), says fields display values/text from an IR image, and creation with multiple viewers requires selecting which viewer the field connects to. Section 15.7, printed pages 55–56 (PDF pages 65–66), describes field contents and refresh. This confirms the domain distinction between a displayed field and its linked viewer. It does not document the private bytes or certify current-version lifecycle behavior.

## Remaining boundary

The native code exposes a credible SDK-GUID lookup mechanism and explicit field/SDK/bookmark maps. It does not yet prove which edits are sufficient for a safe join. A prospective binary rewrite must preserve framing, compressed-block lengths/checksums, all SDK/object references and Word-side bindings. Static decoding and a reversible byte-diff experiment can narrow those requirements without Office; actual edit/save/reopen isolation still needs the later behavior proof. No COM availability was consumed and no production policy was changed.
