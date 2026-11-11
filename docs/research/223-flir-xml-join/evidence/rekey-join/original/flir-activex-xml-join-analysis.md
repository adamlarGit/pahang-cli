# FLIR ActiveX XML Joining & Storage Research (#223)

- **Author / Agent**: Antigravity Coding Assistant (Gemini 3.8 Flash session)
- **Branch**: `research/flir-activex-xml-join-analysis`
- **Date**: 2026-11-11
- **Scope**: Static OOXML package inspection, OLE Compound File Binary (CFB) stream dissection, and primary format specification analysis ([MS-OI29500], [MS-DOCX], [MS-CFB], [MS-OLEDS], ECMA-376). Zero Microsoft Word COM automation was invoked during this research.

---

## 1. Executive Summary & Verdict

### Verdict: **Can't tell without a prototype**

- **For Slicing / Deletion (#231)**: **100% Feasible in XML/ZIP.** Slicing cuts content from a single document by deletion without creating multi-viewer collisions. Intact subgraphs (`w:control`, `activeX{N}.xml`, `activeX{N}.bin`, and `w:docVar`) can be preserved byte-for-byte while unreferenced parts are pruned.
- **For Joining / Merging Two Documents**: **Requires an isolated prototype before production adoption.**
  Standard OPC package components (`w:control`, `r:id`, `w:shapeid`, `activeX{N}.xml`, `activeX{N}.bin`, relationship mappings) can be cleanly copied, remapped, and renumbered in pure Python without Word COM.
  **However, the critical blocker is inside `activeX{N}.bin`**:
  FLIR's proprietary OLE stream embeds length-prefixed ASCII strings for every bound `DOCVARIABLE _Fd...` variable inside its `TAG_R8_FLD` records. When joining two documents originating from the same template, both `.bin` streams contain *identical* `_Fd...` strings. In Microsoft Word, moving a measurement spot on Viewer 2 instructs the FLIR Add-In to update the document variable named in its `.bin` record (`_Fd...`), thereby causing measurement/table crosstalk with Viewer 1 unless those binary records are safely patched or proven tolerant.

---

## 2. Complete FLIR ActiveX Persistence Chain

The embedded FLIR Tools+ IR Viewer (`CIRViewer`) is represented across seven distinct OpenXML package layers:

```
word/document.xml
  ├── <w:object> or <w:control>
  │     ├── @r:id="rId8" ──────────────────────────────┐
  │     ├── @w:name="CIRViewer1211111131211"           │
  │     └── @w:shapeid="_x0000_i1032" ───────────┐     │
  ├── <mc:AlternateContent>                      │     │
  │     ├── <mc:Choice> (DrawingML preview)      │     │
  │     └── <mc:Fallback>                        │     │
  │           └── <v:shape id="_x0000_i1032"> ◄──┘     │
  │                 └── <v:imagedata r:id="..."/>      │
  └── <w:tbl> (Measurement Table)                      │
        └── <w:instrText>DOCVARIABLE _Fd1922861825</w:instrText> ──┐
                                                                   │
word/_rels/document.xml.rels ◄─────────────────────────────────────┘
  └── <Relationship Id="rId8"
          Type=".../relationships/control"
          Target="activeX/activeX1.xml"/>
                                │
word/activeX/activeX1.xml ◄─────┘
  └── <ax:ocx ax:classid="{C5F5764B-B932-4F33-8BF3-9941F22FAE18}"
              ax:persistence="persistStorage"
              r:id="rId1"/>
                    │
word/activeX/_rels/activeX1.xml.rels
  └── <Relationship Id="rId1"
          Type=".../relationships/activeXControlBinary"
          Target="activeX1.bin"/>
                                │
word/activeX/activeX1.bin ◄─────┘ (OLE Compound File Binary)
  └── [Root Storage: CLSID {C5F5764B-B932-4F33-8BF3-9941F22FAE18}]
        └── Stream: "Contents"
              ├── Header: "R8:0.1", Instance GUIDs
              ├── TAG_R8_FLD Record:
              │     ├── Magic: "TAG_R8_FLD\0"
              │     ├── Bound Variable Name: "_Fd1922861825\0" ◄─── Matches document.xml!
              │     └── Zlib Payload: Measurement Tool Def ("Sp1", Spot 1)
              └── Zlib Stream (Offset ~2089, ~1.4MB decompressed):
                    └── Radiometric Sensor Image & Temperature Grid
                                                                   ▲
word/settings.xml ◄────────────────────────────────────────────────┘
  └── <w:docVar w:name="_Fd1922861825" w:val="35.6 °C"/>
```

---

## 3. Dissection of the Binary Stream (`activeX{N}.bin`)

Direct binary examination of `templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx` and `005. TALAPIA (IR+VI).docx` revealed:

1. **CFB Container**: `activeX{N}.bin` is a valid OLE Compound File (`olefile.isOleFile() == True`) with root CLSID `{C5F5764B-B932-4F33-8BF3-9941F22FAE18}`.
2. **Stream Structure**: The container holds a single stream named `Contents`.
3. **Record Layout in `Contents`**:
   - `Offset 0..10`: Length-prefixed version tag `07 00 00 00` -> `R8:0.1\0`.
   - `Offset 11..51`: Length-prefixed GUID `25 00 00 00` -> Session / Image GUID (e.g. `f0ff1a2f-6150-4fa9-ae4c-a199a4ec68ec\0`).
   - `Offset 52..92`: Length-prefixed GUID `25 00 00 00` -> Control Instance GUID (e.g. `65f355f7-d614-4afe-85c8-dff34b8c47c7\0`).
   - `Offset 93..`: `TAG_R8_FLD` blocks:
     - `0b 00 00 00` -> `TAG_R8_FLD\0`
     - `0e 00 00 00` -> `_Fd1922861825\0` (Exact length prefix = 14 bytes)
     - `ae 01 00 00` -> 430-byte payload containing zlib-compressed tool parameters (`Sp1`, `Sp2`, `Ar1`, `Dt1`).
4. **Radiometric Image Data**:
   - Starts at offset ~2089 as a raw zlib stream (`78 9c ...`).
   - Decompresses to **625,696 to 1,400,256 bytes** of uncompressed radiometric thermal sensor arrays and calibration data.
   - **Crucial Fact**: The image data is self-contained within each `.bin` stream. It is *not* referenced by external paths or document variables.

### 3.1 Deep Dissection of Measurement IDs & In-Place Rekeying

Detailed byte extraction revealed the exact internal structure of the `TAG_R8_FLD` measurement records:

1. **The Three Distinct ID Layers**:
   - **Top Session/Image GUID** (Offset 11): Identifies the radiometric capture session.
   - **Control Instance GUID** (Offset 52): 36-char GUID identifying the specific ActiveX viewer instance (e.g., `65f355f7-d614-4afe-85c8-dff34b8c47c7`). Repeated in each measurement sub-record.
   - **Measurement GUIDs** (inside each `TAG_R8_FLD` payload): Every measurement tool on the thermogram has its own dedicated 36-character GUID:
     - `b6ff78c0-1459-43d3-a90a-9246e31cf8ab` -> `Sp1.Max. Temperature`
     - `fdd3008e-bb11-4f85-8d78-402a7e2ac8d6` -> `Sp1.Temperature`
     - `67554dcf-a2e5-439f-b8b9-5b16c62a57c2` -> `Sp2.Temperature`
     - `2c336045-beec-4eca-8283-9f8b408cf619` -> `Dt1` (`abs([ana.Sp1.temp] - [ana.Sp2.temp])`)
2. **Single-Occurrence Localization**:
   - The Measurement GUIDs occur **exactly once** in the entire binary stream as ASCII strings within the `TAG_R8_FLD` header.
   - They do **not** occur as raw 16-byte binary UUID structs, nor do they appear in the decompressed sensor image block.
   - The `_Fd...` variable names occur **exactly once** in the stream header, directly preceding the measurement payload.
3. **Payload Structure of a Measurement Record**:
   ```
   [4 bytes LE length: 430]
     ├── [4 bytes: 7] -> "R8:0.1\0"
     ├── [4 bytes: 37] -> Measurement GUID: "b6ff78c0-1459-43d3-a90a-9246e31cf8ab\0"
     ├── [4 bytes: 37] -> Instance GUID: "65f355f7-d614-4afe-85c8-dff34b8c47c7\0"
     ├── [43 bytes] -> TNEK record header containing:
     │     ├── [4 bytes: 284] -> Compressed zlib length
     │     └── [4 bytes: 689] -> Decompressed length
     └── [284 bytes] -> Zlib payload decompressing to 689 bytes of UTF-16LE tool descriptors
   ```
4. **In-Place Fixed-Length Rekeying Proof**:
   - Because UUIDs are strictly 36 characters and `_Fd` variables can be generated matching the source digit length (e.g. 13 characters: `_Fd1922861825` -> `_Fd9901000000`), in-place binary substitution causes **zero byte offset shift**.
   - Verified in `.scratch/test_full_rekey.py`: When all Instance GUIDs, Measurement GUIDs, and `_Fd` variable names in `swg-panel.docx` were rekeyed with fresh random values of identical string length:
     - Total file size stayed exactly 307,200 bytes.
     - `Contents` stream size stayed exactly 300,182 bytes.
     - OLE CFB FAT, Mini-FAT, sector boundaries, and directory structures remained 100% valid (`olefile.isOleFile() == True`).
     - All embedded zlib measurement blocks and the 625KB sensor block decompressed with zero errors.
   - This provides the concrete mathematical foundation for prototype #225 to eliminate Measurement Crosstalk entirely.

---

## 4. The Anatomy of FLIR Crosstalk

### Why Naive Joins (`docxcompose` / `python-docx`) Failed
1. **Relationship and Part Collisions**: `docxcompose` does not understand ActiveX relationships. When merging Document 2 into Document 1, it either collided relationship targets to point both viewers to `word/activeX/activeX1.xml` or overwrote `activeX1.bin`. As a result, both viewers pointed to the same binary file.
2. **Control Name Collisions**: Both pages retained `w:control/@w:name="CIRViewer1211111131211"`. In Microsoft Word's COM object model and the FLIR Tools+ Add-In, controls are resolved by name. Identical names cause Word to collapse both controls into a single object reference.

### The Subtle Measurement Crosstalk
Even when `activeX{N}.bin` is cloned to `activeX2.bin` and given a unique `w:control/@w:name`:
- If both documents were compiled from the same template, `activeX1.bin` and `activeX2.bin` contain identical `_Fd...` strings inside their `TAG_R8_FLD` headers.
- When an engineer adjusts Spot 1 on Viewer 2 in Word, FLIR Tools+ writes the new temperature to `ActiveDocument.Variables("_Fd1922861825").Value`.
- Because Viewer 1's table also displays `DOCVARIABLE _Fd1922861825`, **Viewer 1's displayed temperature changes to match Viewer 2**.

---

## 5. Explaining the Talapia Repeats (Ticket #223 Comment Analysis)

Ticket #223 noted:
> *Talapia Quick Report compiled by Word: 99 DOCVARIABLE fields carry 90 unique names (9 names appear twice). Nine v:shape ids repeat inside mc:Fallback. w:control names and relationship ids are unique (27 each). settings.xml holds 4025 w:docVar entries.*

Our byte-level inspection confirmed the exact reason:
1. **The 9 Duplicate `DOCVARIABLE` Fields**:
   - Exactly 9 field names repeat:
     - 4 fields in `CIRViewer1211111131` repeated identically in `CIRViewer12111111314` (activeX11 & activeX18)
     - 4 fields in `CIRViewer121111113111` repeated identically in `CIRViewer1211111131114` (activeX16 & activeX23)
     - 1 field (`_Fd912557116`) repeated across activeX12 and activeX19.
   - **Binary Inspection**: In all four repeating controls (activeX11, 16, 18, 23), `TAG_R8_FLD count == 0` and `_Fd count == 0` in the `.bin` streams. They are non-defect or static templates where measurements were not dynamically linked to `activeX.bin`.
   - **Why Word Tolerates Them**: `DOCVARIABLE` is simply a read-only presentation field pointing to a variable in `settings.xml`. In Word's specification, multiple fields can reference the same document variable. Word rejects duplicate variable *declarations* in `Variables.Add()`, but welcomes multiple field *usages*.
2. **The 9 Duplicate `v:shape` IDs in `mc:Fallback`**:
   - Under ECMA-376 Part 3 (Markup Compatibility), Word only evaluates the active choice (`mc:Choice`). Elements inside `mc:Fallback` are ignored by modern Word and never enter the live shape collection. Collisions between fallback shapes across merged pages do not cause runtime conflicts.

---

## 6. FLIR Plugin Tools & Native SDK Ecosystem

Inspection of the host system's installed FLIR environment revealed three distinct toolsets available for exploitation without Word COM:

### 1. FLIR Atlas SDK (`Flir.Atlas.Image.dll`, 64-bit .NET)
- **Location**: `C:\Program Files\FLIR\FLIR Thermal Studio\Flir.Atlas.Image.dll`
- **Capabilities**:
  - `ThermalImageFile.Open(path)`: Loads radiometric thermal JPEGs directly.
  - `ThermalImage.GetValueAt(x, y)`: Directly computes exact radiometric temperature in °C at any pixel without Office.
  - `ThermalImage.Measurements`: Inspects or programmatically defines spots, rectangles, deltas (`MeasurementSpot`, `MeasurementDelta`).
  - `PaletteManager` & `RenderTo(...)`: Renders thermal images with accurate palettes (`IronHi.pal`, `Rainbow`) to static bitmap/PNG previews.
- **Application**: Allows extracting radiometric temperature ground truths (`Sp1`, `Sp2`, `Dt1`) directly from raw photos in pure Python, eliminating reliance on Word for thermal data extraction.

### 2. FLIR Word Reporting Engine (`WizardClassLibrary.dll` & `WordAddin_O2k7.dll`)
- **Location**: `C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin\`
- **Capabilities**:
  - `WizardClassLibrary.ProReport` & `Serializer`: Creates and parses native report manifests.
  - `WizardClassLibrary.WordApp.CreateReport(...)`: Invokes FLIR's native serialization engine to generate pristine single-page `.docx` files containing freshly serialized `activeX1.bin` controls.

### 3. Native Reporter SDK (`ReporterSDK.dll`, Win32 COM)
- **Location**: `C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin\ReporterSDK.dll`
- **Capabilities**:
  - Exposes `IMeasurement` (72 COM methods) and `IObjectParameter` for camera emissivity and mathematical evaluation of tool formulas (`abs([ana.Sp1.temp] - [ana.Sp2.temp])`).

---

## 7. Identifier Scopes: Rename vs Renumber vs Copy Unchanged

| Identifier | Scope | Rule for XML Join | Rule for Slice / Deletion |
| :--- | :--- | :--- | :--- |
| **`word/activeX/activeX{N}.bin`** | OPC Part Name | **Renumber / Rename**: Allocate `activeX{N+1}.bin` for imported controls. | **Copy Unchanged**: Keep existing part name; delete orphaned parts. |
| **`word/activeX/activeX{N}.xml`** | OPC Part Name | **Renumber / Rename**: Allocate `activeX{N+1}.xml`. | **Copy Unchanged**. |
| **`activeX{N}.xml.rels` Target** | Target URI | **Remap**: Update target to corresponding `activeX{N}.bin`. | **Copy Unchanged**. |
| **`document.xml.rels` (`r:id`)** | Relationship ID | **Remap / Renumber**: Allocate unique `rId...` within `document.xml.rels`. | **Copy Unchanged** for retained parts. |
| **`w:control/@w:name`** | Document-wide | **Rename**: Append unique incrementing digit suffix (`...1`, `...2`). | **Copy Unchanged**. |
| **`w:control/@w:shapeid`** | Document-wide | **Renumber / Remap**: Must match companion `v:shape/@id`. | **Copy Unchanged**. |
| **`v:shape/@id` & `o:spid`** | Document-wide | **Renumber / Remap**: Increment shape ID to avoid collisions in `mc:Choice`. | **Copy Unchanged**. |
| **`wp:docPr/@id`** | Document-wide | **Renumber**: Assign unique positive integer (1..2147483646). | **Copy Unchanged**. |
| **`ax:classid` & `persistence`** | Control Type | **Copy Unchanged**: Must stay `{C5F5764B-B932-4F33-8BF3-9941F22FAE18}` and `persistStorage`. | **Copy Unchanged**. |
| **`Contents` stream bytes** | CFB Stream | **Preserve**: Zlib image payload and sensor data must be copied byte-for-byte. | **Copy Unchanged**. |
| **`DOCVARIABLE` & `w:docVar`** | Document-wide | **Investigate in Prototype**: If source templates share `_Fd...`, either accept shared binding (if read-only) or patch `_Fd` in both XML and `activeX.bin` `TAG_R8_FLD`. | **Copy Unchanged**. |

---

## 8. Demystifying ADR 0002

1. **"Binary Header Offset Breakage"**:
   ADR 0002 asserted that renaming control attributes in XML breaks binary offsets in `activeX{N}.bin`.
   *Finding*: XML attribute edits cannot mechanically alter byte offsets in an independent binary part. What actually happened:
   - Naive text replacement inside `.bin` files broke length prefixes and CFB 512-byte sector structures.
   - Renaming `_Fd` in XML without changing the `.bin` severed the link between the FLIR Add-In and the document table.
2. **`Saved = False` stripping `TAG_R8_FLD`**:
   ADR 0002 noted that calling `main_doc.Saved = False` after `Documents.Add()` stripped the 4KB header during COM paste.
   *Finding*: This is an internal quirk of Microsoft Word's COM OLE serialization pipeline when a container document is flagged as dirty during clipboard pasting. A pure Python XML join does not interact with Word's clipboard or COM serialization, and is completely unaffected by this bug.

---

## 9. Recommendations for Next Steps

1. **Slice Proof (#231)**: Proceed with pure XML/ZIP deletion. Since slicing extracts a subset of a single document, all identifiers and binary streams remain unaltered. No renaming is necessary.
2. **XML Join Prototype (#225)**: Validated in scratch proof (`.scratch/xml_join_flir_engine.py`). Successfully joined multi-page FLIR documents with 100% unique control names, isolated `.bin` parts, unique measurement GUIDs, and rekeyed `_Fd` variables in sub-second execution without Word COM. Ready for human verification in Microsoft Word.

---

## 10. Prototype Proof of Pure XML Join

In `.scratch/xml_join_flir_engine.py` and `.scratch/test_multi_join.py`, we implemented and validated the complete pure-Python XML join engine:

1. **Multi-Panel Assembly Results**:
   - Joined 3 consecutive switchgear panel pages from `swg-panel.docx` in **0.15 seconds**.
   - Generated **3 unique control names**: `CIRViewer1211111131211`, `CIRViewer12111111312111`, `CIRViewer12111111312112`.
   - Created **3 separate OLE binary parts**: `activeX1.bin`, `activeX2.bin`, `activeX3.bin` (each exactly 307,200 bytes, valid OLE Compound Files).
   - Generated **12 globally unique `_Fd` measurement variables** across the 3 pages, simultaneously rekeyed in both XML tables and binary `TAG_R8_FLD` headers.
   - Synchronized all 12 variables in `word/settings.xml`.
2. **Artifacts Generated for User Inspection**:
   - 2-Panel Join: `.scratch/joined_swg_panels_proof.docx` (801,796 bytes)
   - 3-Panel Join: `.scratch/joined_3_panels_proof.docx` (1,179,960 bytes)
   - Both artifacts are ready for the user to open in Microsoft Word to confirm that FLIR Tools+ loads all viewers with zero repair prompts, zero image crosstalk, and zero measurement crosstalk.
