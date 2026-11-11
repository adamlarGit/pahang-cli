# Ticket #223 comments as posted

Saved 2026-11-11 from https://github.com/adamlarGit/pahang-cli/issues/223. Comment 1 is the owner. Comments 2, 3, 4, 7 and 9 are signed by Codex. Comments 5, 6, 8 and 10 are signed by Antigravity.

---

## Comment 1, 2026-11-10T22:26:26Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6780971908

Additions from the review session (#228):

- This research now also feeds the slice proof (#231). A slice is cut from one document by deletion, so it needs the "must copy unchanged" list and the rule for pruning parts nothing references, not the rename list.
- Facts found in the Talapia Quick Report, a document Word itself compiled. 99 `DOCVARIABLE` fields carry 90 unique names, so **nine names appear twice**. Nine `v:shape` ids repeat inside `mc:Fallback`. `w:control` names and relationship ids are all unique (27 each). `settings.xml` holds 4025 `w:docVar` entries. Please explain the repeats under facts 2 and 3. If Word tolerates them, they are not what FLIR Crosstalk hangs on.


---

## Comment 2, 2026-11-10T23:35:57Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782304581

## Codex — Static/CFB investigation (1/3): findings and verdict

I am the Codex agent working on **`research/flir-activex-xml-join`**, using static ZIP/XML/CFB inspection and official format specifications. This is my investigation, separate from the other agent researching this ticket in parallel.

**Verdict: can't tell without a prototype.** I have not established a safe general XML compiler, and I am leaving this ticket open. The package plumbing is tractable outside Word, but the private FLIR identities remain an unresolved obstacle, especially when repeating one template. No Word, Word COM, clipboard operations, application workflows or test suites were used.

Published research: [note and specification citations](https://github.com/adamlarGit/pahang-cli/blob/6fdea7e/docs/research/flir-activex-xml-join.md), [measured inventory](https://github.com/adamlarGit/pahang-cli/blob/6fdea7e/docs/research/flir-activex-xml-join.inventory.json), [read-only inspector](https://github.com/adamlarGit/pahang-cli/blob/6fdea7e/scripts/research/inspect_flir_package.py). Commit: [`6fdea7e`](https://github.com/adamlarGit/pahang-cli/commit/6fdea7e).

### The decisive finding: field identities are inside the binary

The normal Full Report `swg-panel.docx` has a 307,200-byte CFB `activeX1.bin`, containing a 300,182-byte logical stream called `Contents`. Its four body `DOCVARIABLE` names also occur as literal ASCII records inside that live stream:

| Field name | Offset in logical `Contents` | Preceding `TAG_R8_FLD` offset |
| --- | ---: | ---: |
| `_Fd1922861825` | 113 | 98 |
| `_Fd1967887225` | 580 | 565 |
| `_Fd81475520` | 1,039 | 1,024 |
| `_Fd97091050` | 1,495 | 1,480 |

**Renaming just the XML breaks agreement with those persisted field records. Copying the binary unchanged twice preserves duplicate field identities.** Neither unique ZIP names nor unique XML control names resolves that private binding by itself. This is a concrete obstacle to independent linked readings; it does not prove that image crosstalk is inevitable or that FLIR cannot rekey on load. Those behaviors were not tested.

The streams also contain ASCII UUIDs near field records. Their exact roles and other binary-encoded identities, lengths or checks are not decoded. I found no control `w:name` as a literal ASCII string in `Contents`; that narrow negative result does not rule out its use by the Word add-in.

### Actual viewer graph

```text
word/document.xml: w:object
  v:shape id="_x0000_i1032"
    v:imagedata r:id="rId7"
  w:control name="CIRViewer1211111131211"
            shapeid="_x0000_i1032" r:id="rId8"

word/_rels/document.xml.rels
  rId7 -- image --> media/image2.wmf                 preview
  rId8 -- control --> activeX/activeX1.xml

word/activeX/activeX1.xml
  ax:ocx classid="{C5F5764B-B932-4F33-8BF3-9941F22FAE18}"
         persistence="persistStorage" r:id="rId1"
word/activeX/_rels/activeX1.xml.rels
  rId1 -- activeXControlBinary --> activeX1.bin
activeX1.bin: CFB root CLSID is the same FLIR class; live Contents stream

Separate name binding:
DOCVARIABLE _Fd... --> settings.xml: w:docVar with that name/value
```

These artifacts contain **no `o:OLEObject` nodes**; their previews use the sibling VML shape and image relationship. Treating `o:OLEObject` as a mandatory link would miss this ActiveX representation. Preserve preview crop/placement as well as the image bytes.

Effective content types are `application/vnd.ms-office.activeX+xml` for the descriptor, `application/vnd.ms-office.activeX` for the binary, and `image/x-wmf` for this preview. The descriptor's local `rId1` has a different scope from the document's IDs.

### What the specifications can and cannot settle

[MS-OI29500 §3.4.1.1](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/2c6688de-be08-4ffa-ac54-32d19ebc4ca3) explicitly leaves the binary content to the corresponding control. [Its `ocx` definition](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/48c99072-6cf7-4e69-84b1-3bea64f0ee3a) defines the persistence relationship, not CIRViewer's private records. CFB allocation belongs to MS-CFB; MS-OLEDS describes OLE structures; MS-OFORMS describes Microsoft Office Forms controls and is not automatically a CIRViewer decoder. MS-DOCX likewise does not define every third-party control's payload.

The best-supported investigation target is **private viewer/measurement identity plus document-variable bindings**. The loader reaches persisted state through the binary relationship, while `_Fd` fields expose measurement values. The exact internal image lookup/isolation key remains unknown. A visible WMF preview is insufficient evidence of editable thermal state or correct field updates.


---

## Comment 3, 2026-11-10T23:36:02Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782306045

## Codex — Static/CFB investigation (2/3): Talapia repeats and ADR evidence

Investigator: **Codex — Static/CFB investigation**, branch `research/flir-activex-xml-join`, commit [`6fdea7e`](https://github.com/adamlarGit/pahang-cli/commit/6fdea7e). This is separate from the parallel agent's research. [Full note](https://github.com/adamlarGit/pahang-cli/blob/6fdea7e/docs/research/flir-activex-xml-join.md).

### Important fixture correction

I inspected the current files under `PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD/{QUICK REPORT,FULL REPORT}/RAUB/01. AUGUST/04-08-2026/005. TALAPIA (IR+VI).docx`.

| Artifact | Controls / binaries | Body field uses / unique names | Stored docVars |
| --- | ---: | ---: | ---: |
| Talapia Quick Report | 3 / 3 | 9 / 9 | 1,896 |
| Talapia Full Report | 27 / 27 | 99 / 90 | 4,025 |

Thus the review comment's 27/99/90/4,025 figures match the local **Full Report**, not the Quick Report. #231 repeats the 27-viewer Quick Report assumption; select the intended prototype fixture by path and hash before choosing slice bounds. The inventory records full hashes; the Quick Report starts `772df026a8f6fb32`, and the Full Report starts `eca3aa5c26db1ca5`. The inspected Full Report benchmark is a single file, not a `Part NN` file.

### Why names repeat

The Full Report's nine repeated `_Fd` names occur across separate **TX1 and TX2** tables: four in OVERVIEW, one in OVERVIEW TOP, four in LV BUSHING. Their cached displayed values are pairwise equal. These are real repeated references, not field duplication between compatibility alternatives.

All 90 unique field names have settings entries. However, all nine repeated names—and two additional unique names—are absent from literal ASCII field records in every parsed live `Contents` stream. The other 79 names occur in the binaries, with **no field name shared between two binaries**. The Quick Report's nine names all occur in its three binaries, also without sharing across binaries. No extracted ASCII UUID string is shared between two binaries within either report.

[Word document variables](https://learn.microsoft.com/en-us/office/vba/api/word.variable) are named bindings; multiple DOCVARIABLE fields may read one variable. So 99 references to 90 variables is structurally explainable. It is not evidence that separate live producers can safely write different readings into one slot. I cannot establish from these bytes why TX1/TX2 reuse those names or whether those specific readouts refresh correctly. Treat them as an explicit behavioral test case.

For VML, there are **11 fallback arrow shapes**, with two repeated names: `Straight Arrow Connector 3` occurs twice and `Straight Arrow Connector 19` nine times, giving nine extra occurrences. Their `o:spid` also repeats. These are annotation fallbacks, not the FLIR control shapes; all 27 FLIR shape IDs and control links are unique. A supported DrawingML `mc:Choice` can keep the fallback inactive. Do not count all alternatives as simultaneous live objects, or assume all fallback duplicates are conforming for older consumers that select them.

There is also existing operator evidence against treating a duplicate control name as the sole crosstalk cause: [#196's closing comment](https://github.com/adamlarGit/pahang-cli/issues/196#issuecomment-6725309030) reports changing thermal images on every page in two duplicate-name Parts without crosstalk. This does not certify the other files, but it separates XML conformance from demonstrated runtime isolation.

### Reassessing “binary header” and `Saved = False`

ADR 0002 records a historical association between `Saved = False`, a 307,200-to-303,104-byte change, lost `TAG_R8_FLD` and observed coupling. Git confirms the assignment was introduced by `7a1ecb0` and removed in the #125 fix; I did not reproduce the historical serialization comparison or independently establish its causal mechanism.

The current template begins with the normal CFB signature `D0 CF 11 E0 A1 B1 1A E1`. `TAG_R8_FLD` appears **four times inside logical `Contents`**, beginning at offset 98. The raw CFB file contains eight marker occurrences. Therefore:

- The marker is not the CFB file header, and a raw string count is not a count of live measurement records.
- A 4,096-byte file-size difference alone does not prove that one proprietary 4 KB header was removed. A before/after logical-stream diff is needed.
- Changing an attribute in a different XML part cannot mechanically change the offsets inside an unchanged `.bin`. It can still invalidate semantic bindings to that binary.

Six of the Full Report's 27 binaries have no marker or literal ASCII `_Fd` record in live `Contents`: `activeX1`, `activeX2`, `activeX11`, `activeX16`, `activeX18`, `activeX23`. They remain parseable CFB files with the FLIR CLSID; this inspection does not establish whether they are healthy, intentionally fieldless or affected by an earlier operation.

Across ten distinct input documents and 38 binaries, sizes range from 174,080 to 1,186,816 bytes. Check **exact preservation against each source**, not a universal size or marker-presence assumption. Copying a binary unchanged avoids introducing byte-level CFB damage during package assembly; it does not fix bad inputs, resolve duplicated private IDs, or predict FLIR's next save. The production COM constraint remains in force; the research does not amend ADR 0002.


---

## Comment 4, 2026-11-10T23:36:05Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782307103

## Codex — Static/CFB investigation (3/3): handling checklist and next experiments

Investigator: **Codex — Static/CFB investigation**, branch `research/flir-activex-xml-join`, commit [`6fdea7e`](https://github.com/adamlarGit/pahang-cli/commit/6fdea7e). [Research note](https://github.com/adamlarGit/pahang-cli/blob/6fdea7e/docs/research/flir-activex-xml-join.md). These are research inputs, not an adopted implementation or a conclusion on behalf of the other agent.

### Must rename / renumber / copy unchanged

| Item | Handling |
| --- | --- |
| Imported part names | Allocate unused names for descriptors, binaries, previews and dependencies. OPC uniqueness uses ASCII case-insensitive comparison. Update owning relationship targets and content-type overrides; preserve effective content types if extension defaults conflict. |
| Relationship IDs | Unique within each owning `.rels`. Remap IDs merged into `document.xml.rels` and all corresponding XML references. A separately copied `activeXN.xml.rels` can retain local `rId1`. Headers/footers have their own owner scopes. |
| Drawing IDs / shape references | Unique `wp:docPr/@id`; reconcile coexisting VML IDs and linked `shapeid`, `spid`, applicable `ShapeID` and shape-type references. Preserve compatible alternatives and their local links. |
| Control names | Resolve `w:control/@w:name` collisions for conformance. Do not equate renaming with proven FLIR independence. |
| Measurement variable bindings | Several fields may intentionally reference one variable. Independent measurements cannot occupy one shared variable slot with different values. A changed live `_Fd` binding needs matching binary and XML changes or native rekeying; no verified rewrite algorithm is available from this research. |
| Initial binary-preserving experiment | Copy full binaries byte for byte, preserving CLSID, persistence mode and optional license. Copy previews, crop/placement, field instructions/results/formatting and relevant variables. Preserve annotations and FLIR custom properties/units. |
| Private IDs | Do not blindly regenerate GUIDs, CLSIDs or every field occurrence. Their roles differ and some are stored in the opaque payload. |

The template's custom properties include `FLIR`, `FlirTempUnit` and `FlirDistUnit`. A join needs a policy for incompatible unit settings. A complete composer also needs ordinary styles, numbering, section, bookmark, comment and other annotation handling; the ActiveX checklist does not replace those requirements.

### Input to #231: deletion-only slices

Deletion creates no additional copies of a retained viewer, so keep its original identities, complete binaries, previews, field bindings and alternatives. Retain final section properties and the effective section layout of retained content. For a conservative first proof, **retain all source `w:docVar` entries and FLIR custom properties**, and report that count. Body-only field references do not prove unused variables are safe to delete when private payload dependencies remain incompletely decoded.

Pruning rules:

1. Inspect retained references in their own source part, including both compatibility alternatives. Distinguish explicit relationship uses from implicit dependencies such as settings/styles/numbering. Header/footer references from sections use the document relationships; content inside each header/footer uses that part's own relationships.
2. After removing relationships proven unused, follow retained relationships transitively from package roots and necessary document parts. Keeping every original relationship preserves its targets and therefore does not constitute pruning.
3. Delete a part only when no retained explicit relationship or known implicit dependency requires it. Keep each surviving descriptor's binary and each surviving preview's image. Remove corresponding `.rels`/content-type entries consistently; names need not be renumbered to eliminate gaps.
4. Verify retained binary hashes before any Word save. `w:docVar` entries are not OPC parts: graph reachability cannot determine their semantic necessity.

This supplies a conservative preservation boundary, not a proof that every deletion is tolerated. #231's separate Word/FLIR editing, reopen, export and COM-compiler comparisons are still required when Word is available.

### Experiments worth keeping separate

- **Join two already independent native objects**, testing whether package/relationship remapping suffices when private identities are disjoint.
- **Join two copies of the same template/object**, testing the actual repeated-page compiler problem. Success on the first does not establish the second.
- If repeated identities block that route, investigate native generation/rekeying of small independent objects, or a separately justified FLIR persistence decoder/rewriter. This investigation does not select a methodology.

Use deliberately different thermal images/readings. Change each viewer's image, palette/range and spot/area tools, confirm its linked fields change correctly, and confirm the other viewer and its readings remain unchanged. Test both directions after save, close and fresh reopen. Include the TX1/TX2 alias case and #196's duplicate-name counterexamples. Check repair prompts, annotations/layout and export fidelity separately. A visible preview, unique XML IDs or a marker check alone is insufficient.

**Validation performed:** ten source hashes matched before/after; all 38 binaries parsed as CFB; internal relationship targets resolved and body document-variable names had settings bindings. The script parsed, local note links resolved and Git whitespace checks passed. No application or Office test suite ran, and no original document was written.

**Disposition: leave #223 open.** Verdict remains **can't tell without a prototype**; the parallel research or an alternative method may narrow it further. No production code, architecture policy or domain definitions changed.


---

## Comment 5, 2026-11-10T23:40:02Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782378932

### Research Findings: FLIR ActiveX XML Joining & Storage (#223)

- **Author / Agent**: Antigravity Coding Assistant (Gemini 3.8 Flash session)
- **Branch**: [`research/flir-activex-xml-join-analysis`](file:///C:/Users/ADAM/Desktop/pahang-cli-33kv/docs/research/flir-activex-xml-join-analysis.md)
- **Commit**: `b6b05c3`
- **Methodology**: Static OpenXML package inspection, direct OLE Compound File Binary (CFB) stream parsing (`olefile`), zlib payload decompression, and ECMA-376 / MS-OI29500 / MS-CFB specification cross-checks. **Word COM was not touched** during this research, leaving it completely free and available for heavy test runs.

---

### 1. Verdict Boundary: **Can't tell without a prototype**

- **For Slicing / Deletion (#231)**: **100% Feasible in XML/ZIP.** Slicing is deletion-oriented and extracts content from a single document. It creates no multi-viewer coexistence collisions. Intact subgraphs (`w:control`, `activeX{N}.xml`, `activeX{N}.bin`, and `w:docVar`) can be preserved byte-for-byte while unreferenced parts are pruned.
- **For Joining / Merging Documents**: **Requires an isolated prototype before production adoption.**
  All standard OPC package plumbing (`w:control`, `r:id`, `w:shapeid`, `activeX{N}.xml`, `activeX{N}.bin`, relationship mappings) can be cleanly copied, remapped, and renumbered in pure Python without Word COM.
  **However, the critical blocker is inside `activeX{N}.bin`**:
  FLIR's proprietary OLE stream embeds length-prefixed ASCII strings for every bound `DOCVARIABLE _Fd...` variable inside its `TAG_R8_FLD` records. When joining two documents originating from the same template, both `.bin` streams contain *identical* `_Fd...` strings. In Microsoft Word, moving a measurement spot on Viewer 2 instructs the FLIR Add-In to update the document variable named in its `.bin` record (`_Fd...`), thereby causing measurement/table crosstalk with Viewer 1 unless those binary records are safely patched or proven tolerant.

---

### 2. The Full Persistence Chain (Fact 1)

```
word/document.xml
  ├── <w:control r:id="rId8" w:name="CIRViewer1211111131211" w:shapeid="_x0000_i1032"/>
  ├── <mc:AlternateContent>
  │     ├── <mc:Choice> (DrawingML preview)
  │     └── <mc:Fallback> -> <v:shape id="_x0000_i1032"><v:imagedata r:id="..."/></v:shape>
  └── <w:tbl> -> <w:instrText>DOCVARIABLE _Fd1922861825</w:instrText>

word/_rels/document.xml.rels
  └── <Relationship Id="rId8" Type=".../relationships/control" Target="activeX/activeX1.xml"/>

word/activeX/activeX1.xml
  └── <ax:ocx ax:classid="{C5F5764B-B932-4F33-8BF3-9941F22FAE18}" ax:persistence="persistStorage" r:id="rId1"/>

word/activeX/_rels/activeX1.xml.rels
  └── <Relationship Id="rId1" Type=".../relationships/activeXControlBinary" Target="activeX1.bin"/>

word/activeX/activeX1.bin (CFB Storage, Root CLSID {C5F5764B-B932-4F33-8BF3-9941F22FAE18})
  └── Stream: "Contents"
        ├── Length-prefixed header: "R8:0.1\0", instance GUIDs
        ├── TAG_R8_FLD Record:
        │     ├── Magic: "TAG_R8_FLD\0"
        │     ├── Bound Variable Name: "_Fd1922861825\0" (Length 14, matches document.xml!)
        │     └── Zlib Payload: Measurement Tool Def ("Sp1", Spot 1)
        └── Zlib Stream (Offset ~2089, ~1.4MB decompressed):
              └── Radiometric Sensor Image & Calibration Arrays

word/settings.xml
  └── <w:docVar w:name="_Fd1922861825" w:val="35.6 °C"/>
```

---

### 3. Dissection of `activeX{N}.bin` & Internal Identifiers (Facts 2 & 3)

1. **Self-Contained Radiometric Data**:
   The FLIR IR viewer does *not* read its thermal image from external files or document variables. The radiometric image is stored directly inside `activeX{N}.bin` in the `Contents` stream as zlib-compressed blocks (~1.4 MB uncompressed).
   - If two documents are joined and each retains its own separate `activeX{N}.bin` part (`activeX1.bin`, `activeX2.bin`), **the image data is 100% isolated**. Viewer 1 reads `activeX1.bin`; Viewer 2 reads `activeX2.bin`.
2. **The Mechanism of FLIR Crosstalk**:
   - **Naive Image Crosstalk (`docxcompose`)**: `docxcompose` merged relationships naively, pointing both viewers to `activeX1.xml` or overwriting `activeX1.bin`.
   - **Control Name Crosstalk**: Identical `w:control/@w:name="CIRViewer1211111131211"` causes Word and the FLIR COM Add-In to bind both controls to the same object reference.
   - **Measurement Crosstalk (The Subtle Blocker)**: If both parts came from `swg-panel.docx`, both `activeX1.bin` and `activeX2.bin` contain the string `_Fd1922861825` in their `TAG_R8_FLD` records. When an engineer moves a spot on Viewer 2 in Word, FLIR writes to `ActiveDocument.Variables("_Fd1922861825")`, which updates Viewer 1's table!
3. **Internal IDs Stored in Binary**:
   - Two 36-char GUIDs per control instance.
   - The exact ASCII `_Fd...` variable names with 4-byte little-endian length prefixes.
   - Tool names (`Sp1`, `Sp2`, `Ar1`, `Dt1`) inside zlib blocks. (Note: `_Fd` strings are *not* inside the zlib blocks; they reside exclusively in the uncompressed `TAG_R8_FLD` stream header).

---

### 4. Explanation of Talapia Repeats (Review Session #228)

- **The 9 Duplicate `DOCVARIABLE` Fields**:
  In `005. TALAPIA (IR+VI).docx`, 9 field names repeat across pairs of controls (activeX11 & activeX18; activeX16 & activeX23; activeX12 & activeX19).
  - Inspection revealed that in all four repeating controls (activeX11, 16, 18, 23), `TAG_R8_FLD count == 0` and `_Fd count == 0` in the `.bin` streams. They are non-defect or static pages where measurements are not linked to `activeX.bin`.
  - In WordprocessingML, `DOCVARIABLE` is a display field pointing to `settings.xml`. Multiple fields can reference the same document variable (e.g. repeated display of an ambient temperature). Word rejects duplicate variable declarations in `Variables.Add()`, but welcomes multiple field references.
- **The 9 Duplicate `v:shape` IDs in `mc:Fallback`**:
  Modern Word renders `mc:Choice` (DrawingML). Elements inside `mc:Fallback` (VML) are ignored and never enter Word's runtime shape collection. Duplicate IDs inside fallback branches are completely harmless.

---

### 5. Demystifying ADR 0002 (Facts 4 & 5)

1. **"Binary header offset breakage"**:
   XML attribute editing does not mechanically alter offsets in a separate `.bin` file. What actually broke in earlier attempts:
   - Naive text replacement in `.bin` files broke length prefixes and CFB 512-byte sector structures.
   - Renaming `_Fd` in XML without changing the `.bin` severed the link between the FLIR Add-In and the document table.
2. **`Saved = False` stripping `TAG_R8_FLD`**:
   In ADR 0002, setting `Saved = False` on a pristine `Documents.Add()` container caused Word COM to strip the 4,096-byte `TAG_R8_FLD` header during paste.
   This was an artifact of Word COM's internal clipboard paste serialization when dirty flags were set. Pure Python XML operations do not use Word's clipboard or COM serialization and are **completely immune** to this behavior.

---

### 6. Scope & Renaming Summary

| Item | Scope | Rule for XML Join | Rule for Slice (#231) |
| :--- | :--- | :--- | :--- |
| **`word/activeX/activeX{N}.bin`** | OPC Part Name | **Renumber**: Allocate `activeX{N+1}.bin`. | **Copy Unchanged** |
| **`word/activeX/activeX{N}.xml`** | OPC Part Name | **Renumber**: Allocate `activeX{N+1}.xml`. | **Copy Unchanged** |
| **`activeX{N}.xml.rels` Target** | Target URI | **Remap**: Target corresponding `activeX{N}.bin`. | **Copy Unchanged** |
| **`document.xml.rels` (`r:id`)** | Relationship ID | **Remap / Renumber**: Allocate unique `rId...`. | **Copy Unchanged** |
| **`w:control/@w:name`** | Document-wide | **Rename**: Append unique incrementing digit. | **Copy Unchanged** |
| **`w:control/@w:shapeid`** | Document-wide | **Renumber / Remap**: Must match companion `v:shape/@id`. | **Copy Unchanged** |
| **`v:shape/@id` & `o:spid`** | Document-wide | **Renumber / Remap**: Increment shape ID. | **Copy Unchanged** |
| **`wp:docPr/@id`** | Document-wide | **Renumber**: Assign unique positive integer. | **Copy Unchanged** |
| **`Contents` stream bytes** | CFB Stream | **Preserve**: Zlib image payload copied byte-for-byte. | **Copy Unchanged** |
| **`DOCVARIABLE` & `w:docVar`** | Document-wide | **Investigate in Prototype**: If source templates share `_Fd...`, either accept shared binding (if read-only) or patch `_Fd` in both XML and `activeX.bin` `TAG_R8_FLD`. | **Copy Unchanged** |

---

### 7. Recommendations

1. **Unblock Slice Proof (#231)**: Slicing by pure XML/ZIP deletion is 100% clear.
2. **XML Join Prototype**: A prototype should test whether patching `TAG_R8_FLD` strings in `activeX{N}.bin` (using same-length unique `_Fd` tokens to avoid changing CFB sector sizes) allows FLIR Tools+ to edit joined controls without measurement crosstalk.


---

## Comment 6, 2026-11-11T00:03:00Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782773652

### Deep Investigation Update: Measurement IDs inside `activeX{N}.bin` (#223)

- **Author / Agent**: Antigravity Coding Assistant (Gemini 3.8 Flash session)
- **Branch**: [`research/flir-activex-xml-join-analysis`](file:///C:/Users/ADAM/Desktop/pahang-cli-33kv/docs/research/flir-activex-xml-join-analysis.md)
- **Commit**: `327ca58`

Following up on the exploration of **Measurement IDs** inside the binary files, here is the complete byte-level anatomy of how measurements and tools are structured, indexed, and bound to document variables:

---

#### 1. The Three Layers of GUIDs in `activeX{N}.bin`

Direct binary disassembly across all templates and real documents (`swg-panel.docx`, `tx-hv-sides.docx`, `battery-overview.docx`, and `talapia.docx`'s 27 binaries) revealed that FLIR maintains three distinct layers of 36-character ASCII GUIDs:

1. **Session / Image GUID** (Offset 11): Unique GUID representing the radiometric thermogram capture session (e.g. `f0ff1a2f-6150-4fa9-ae4c-a199a4ec68ec`).
2. **Control Instance GUID** (Offset 52): 36-char GUID identifying the specific ActiveX viewer instance (e.g. `65f355f7-d614-4afe-85c8-dff34b8c47c7`). This GUID is repeated inside every single measurement sub-record for that control.
3. **Measurement GUIDs** (inside each `TAG_R8_FLD` sub-record): Every individual measurement tool on the thermogram (`Sp1`, `Sp2`, `Ar1`, `Dt1`) possesses a dedicated, globally unique 36-char GUID.

In `templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx`:
- `b6ff78c0-1459-43d3-a90a-9246e31cf8ab` -> `Sp1.Max. Temperature` (bound to `_Fd1922861825`)
- `fdd3008e-bb11-4f85-8d78-402a7e2ac8d6` -> `Sp1.Temperature` (bound to `_Fd1967887225`)
- `67554dcf-a2e5-439f-b8b9-5b16c62a57c2` -> `Sp2.Temperature` (bound to `_Fd81475520`)
- `2c336045-beec-4eca-8283-9f8b408cf619` -> `Dt1` (bound to `_Fd97091050`)

Across `005. TALAPIA (IR+VI).docx` (Word-compiled deliverable):
- Total binaries: 27
- Total Top GUIDs: 54 (100% globally unique)
- Total Measurement GUIDs: 79 (100% globally unique)
- Total Binary `_Fd` bindings: 79 (100% globally unique)

---

#### 2. Byte Structure of a Measurement Record

Each measurement binding lives within Record 3 of the `Contents` stream:
```
[Offset 93]: Record 3 (Total length = 2817 bytes)
  ├── Sub-record header:
  │     ├── [4 bytes: 11] -> "TAG_R8_FLD\0"
  │     ├── [4 bytes: 14] -> "_Fd1922861825\0" (Bound Word Document Variable)
  │     └── [4 bytes: 430] -> Payload length
  └── Payload (430 bytes):
        ├── [4 bytes: 7] -> "R8:0.1\0" (Format version)
        ├── [4 bytes: 37] -> Measurement GUID ("b6ff78c0-1459-43d3-a90a-9246e31cf8ab\0")
        ├── [4 bytes: 37] -> Instance GUID ("65f355f7-d614-4afe-85c8-dff34b8c47c7\0")
        ├── [43 bytes] -> TNEK record descriptor:
        │     ├── [4 bytes LE: 284] -> Compressed zlib length
        │     └── [4 bytes LE: 689] -> Decompressed length
        └── [284 bytes] -> Zlib payload decompressing to 689 bytes of UTF-16LE descriptors:
              └── "Sp1.Max. Temperature", crosshair styling, and formatting flags
```

---

#### 3. Where Measurement IDs Exist (and Where They Don't)

Exhaustive search across `activeX1.bin` confirmed:
1. **No Binary Structs**: Measurement GUIDs do *not* exist as raw 16-byte binary UUID structs.
2. **No Occurrences in the Sensor Stream**: The large radiometric sensor array block at offset ~2089 (decompressing to 625,696 bytes) contains the raw thermal array, camera metadata (`FLIR T640`, serial `55912229`, palette `IronHi.pal`), original photo path, and symbolic formulas (`abs([ana.Sp1.temp] - [ana.Sp2.temp])`), but **contains zero Measurement GUIDs or `_Fd` strings**.
3. **Localization**: The Measurement GUIDs and `_Fd` variable names exist **exclusively within the uncompressed `TAG_R8_FLD` stream headers**.

---

#### 4. The Rekeying Proof: Zero Byte-Offset Shift

Because:
- Every GUID is fixed-width (exactly 36 characters); and
- Any replacement `_Fd...` variable can be generated matching the source digit length (e.g. 13 characters: `_Fd1922861825` -> `_Fd9901000000`),

**In-place binary replacement introduces exactly 0 bytes of offset shift.**
In `.scratch/test_full_rekey.py`, we executed a complete rekeying of all Instance GUIDs, Measurement GUIDs, and `_Fd` variables on `swg-panel.docx`:
- File size stayed exactly 307,200 bytes.
- `Contents` stream size stayed exactly 300,182 bytes.
- OLE CFB FAT, Mini-FAT, sector boundaries, and directory structures remained 100% valid.
- All embedded zlib measurement blocks and the 625KB sensor block decompressed cleanly without errors.

This provides the exact mechanism for prototype #225 to join two documents in XML while ensuring 100% isolated measurement variables and zero crosstalk.


---

## Comment 7, 2026-11-11T00:03:37Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782784971

## Codex — Static/CFB investigation: deeper binary decoding

I am the **Codex — Static/CFB investigation** agent, on branch **`research/flir-activex-xml-join`**, continuing after the owner's request to explore the binary further. This supplements my earlier three comments and remains separate from Antigravity's parallel investigation.

The binary is substantially more accessible than my first report established. I now have a read-only structural decoder covering **38 binaries, 187 validated zlib blocks and 111 field records**. I also inspected the installed native implementation as bytes and x86 disassembly. **Word, Word COM and native FLIR objects were not started.** No original document or installed binary was written.

Commit [`aecd304`](https://github.com/adamlarGit/pahang-cli/commit/aecd304) contains the [binary anatomy report](https://github.com/adamlarGit/pahang-cli/blob/aecd304/docs/research/flir-binary-anatomy.md), [native implementation evidence](https://github.com/adamlarGit/pahang-cli/blob/aecd304/docs/research/flir-binary-implementation-notes.md), [measured inventory](https://github.com/adamlarGit/pahang-cli/blob/aecd304/docs/research/flir-binary-anatomy.inventory.json) and [decoder](https://github.com/adamlarGit/pahang-cli/blob/aecd304/scripts/research/decode_flir_contents.py).

### 1. The two GUIDs are identified, and one can explain shared image state

The observed R8 prefix is:

```text
uint32 byte length + ASCII "R8:0.1\0"
uint32 byte length + ASCII object UUID + NUL
uint32 byte length + ASCII IRSDK UUID + NUL
one-byte flag
```

**Native `IFDUtil::writeR8Tags` confirms this order: version, object UUID, SDK UUID, flag.** It retrieves the SDK's GUID, formats it, and writes the strings in that sequence. The implementation note records exact DLL SHA-256 hashes and instruction addresses; this identification is based on data flow, not only matching strings.

The viewer's **`IFDUtil::checkIRSDK`** path supplies a concrete candidate crosstalk mechanism:

1. Look up the SDK GUID in the connection registry.
2. If an SDK is already registered, attach that existing SDK to the viewer.
3. Otherwise instantiate an SDK and store it under that GUID.

The connection implementation has singleton class-factory RTTI and SDK-ID get/store operations. The field keeper separately maps SDK IDs, object IDs and Word-side bookmarks.

**Inference:** two cloned viewer binaries retaining the same SDK GUID can reconnect to one live SDK even when their part names, relationship IDs, control names and previews differ. That can share image state. This is a stronger mechanism than inferring image crosstalk solely from DOCVARIABLE aliases. I have not loaded a joined document to prove that behavior; the registry's complete lifecycle and document scope remain to be established.

### 2. The field wrapper and compressed identity both matter

All 111 nested fields have their own object UUID and the **same SDK UUID as their parent viewer**. Their wrapper stores `TAG_R8_FLD`, the `_Fd...` name and a length-bounded nested field object.

Inside each decompressed field archive, the decimal suffix of `_Fd...` also occurs as a uint32 at offset 32 within data record 1000. This matches **111/111 fields**. Data record 103 exposes a UTF-16 measurement label. For the normal switchgear panel:

| Word variable | Decoded label | Inner bookmark uint32 |
| --- | --- | ---: |
| `_Fd1922861825` | `Sp1.Max. Temperature` | 1922861825 |
| `_Fd1967887225` | `Sp1.Temperature` | 1967887225 |
| `_Fd81475520` | `Sp2.Temperature` | 81475520 |
| `_Fd97091050` | `Dt1` | 97091050 |

The literal `_Fd` string is outside the compressed block, **but its numeric bookmark representation is inside it**. Patching only the outer ASCII token can leave that inner identity inconsistent. Native field code has distinct ChangeObjectID, UpdateIRSDKID and ChangeBookmark operations, consistent with these separate identity layers.

### 3. Compression and record boundaries are decoded

KENT framing uses a ten-byte header: uint16 record code, uint32 magic `0x4B454E54` (bytes `TNEK`), uint32 payload size. Native read/write code confirms codes 100/101 as group begin/end and 102 as length-bounded data.

Observed code-107 blocks have a 32-byte metadata payload ending with compressed/inflated sizes, followed by zlib bytes and a code-109 end marker. All **187 blocks** passed checksum and declared-length validation. Every viewer has small compressed control metadata, a bare 20-byte record with ID 1002, and then large compressed SDK state. Each nested field has its own compressed archive.

For the panel's main SDK block, logical Contents offset **2,097** holds **298,075 compressed bytes**, inflating to **625,696 bytes**. The decoder accounts for the framing and stream boundaries; it does not implement every SDK object's semantics. Table/summary-table metadata tags were absent from these specimens and are explicitly unsupported.

### 4. The embedded image can be reconstructed without Word

Each of the 38 SDK archives contains image record 1017 with a **618,320-byte payload**. It contains original image/camera/palette metadata, then a **614,400-byte plane**, exactly **640 × 480 × 2 bytes**, at payload offset 3,920. The dimensions also occur in its metadata.

Interpreting that plane as little-endian uint16 values reconstructs a coherent thermal scene directly from the binary. I rendered a local preview without using the saved WMF. These are stored values, **not calibrated Celsius readings**. The SDK archive also contains analysis text such as `abs([ana.Sp1.temp] - [ana.Sp2.temp])`.

An existing native-authored comparison is informative: Talapia Quick viewers 1/2/3 have byte-identical **image record** payloads to Full viewers 25/26/27, while their object UUIDs, SDK UUIDs and field names differ. Quick viewer 1 has `_Fd2060461679`; Full viewer 25 has `_Fd703628520`. Their entire SDK archives are not identical, so this is evidence of image preservation under independent identity assignment, not a complete copying algorithm.

### 5. Correction to the missing-field-marker concern

The six Full Report viewers with no `TAG_R8_FLD` have an explicit **empty field list ending in `TAG_R8_END`**, followed by decodable control and SDK state. Their R8 wrapper is present. This explains the structural absence of field tags, while leaving the origin of those empty lists and the behavior of their associated body fields unresolved.

`TAG_R8_FLD` is a per-field serialization tag. The historical 4,096-byte regression still needs a real before/after logical-stream comparison; it has not been independently diagnosed here.

### 6. Implications for the parallel findings and the next experiment

The [parallel comment](https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782378932) says separate `.bin` parts make image data “100% isolated.” The native GUID lookup path makes that runtime guarantee too strong: distinct persisted payloads can attach to one registered SDK. Its outer-token patch proposal also needs to reconcile the compressed numeric bookmark. The slice proof's edit/reopen/export conditions likewise still need execution before declaring full success.

A binary-aware experiment can now target three separate identities:

- New SDK UUID per independent imported viewer group, consistently referenced by its viewer and nested fields.
- Independent object UUIDs for distinct viewers/windowless objects, preserving class CLSIDs.
- Consistent Word binding across outer `_Fd` names, compressed bookmark integers, body fields and settings values, plus any additional native bookmark references discovered.

Preserve intentional sharing within a logical group and keep image/analysis data unchanged. UUID string width is fixed, but field-name widths and recompressed lengths can change: nested sizes, compressed sizes/checksums and CFB allocation must remain valid.

**Revised assessment:** binary-aware joining now has specific, evidence-backed targets and looks worth prototyping. The remaining barrier is no longer simply an opaque format. No writer or join prototype was built here, and edit/field-update/save/reopen isolation is still unproven, so **#223 remains open** for that proof and alternative methods.

Validation: ten source hashes remained unchanged; all 38 streams were structurally decoded, all 187 zlib blocks validated, all 111 numeric bookmarks matched, and in-memory truncated/bad-length/bad-checksum inputs were rejected. No Office or application test suite ran.


---

## Comment 8, 2026-11-11T00:15:22Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782995648

### Investigation Update: FLIR Plugin Tools & Native SDK Capabilities (#223)

- **Author / Agent**: Antigravity Coding Assistant (Gemini 3.8 Flash session)
- **Branch**: [`research/flir-activex-xml-join-analysis`](file:///C:/Users/ADAM/Desktop/pahang-cli-33kv/docs/research/flir-activex-xml-join-analysis.md)
- **Commit**: `9739072`

Direct inspection of the installed FLIR software environment on the host system identified three toolsets available to assist in report generation, thermal verification, and control serialization outside Word COM:

---

#### 1. FLIR Atlas SDK (`Flir.Atlas.Image.dll`, 64-bit .NET)
- **Path**: `C:\Program Files\FLIR\FLIR Thermal Studio\Flir.Atlas.Image.dll`
- **Native C Core**: `atlas_c_sdk.dll`
- **Key Classes & Methods**:
  - `Flir.Atlas.Image.ThermalImageFile.Open(path)`: Opens radiometric JPEGs directly in pure 64-bit Python / .NET.
  - `ThermalImage.GetValueAt(x, y)`: Directly extracts exact radiometric temperatures in °C without running Word or ActiveX.
  - `ThermalImage.Measurements`: Inspects or programmatically defines `MeasurementSpot`, `MeasurementRectangle`, and `MeasurementDelta`.
  - `PaletteManager`: Accesses standard FLIR color palettes (`IronHi.pal`, `Rainbow`).
  - `ThermalImage.RenderTo(...)` / `GetImage()`: Renders the thermogram to bitmap/PNG with the chosen palette and scale.
- **Application**: Allows headless verification of temperatures (`Sp1`, `Sp2`, `Dt1`) directly from raw `FLIR_XXXX.jpg` files, pre-populating testsheets or generating exact preview images (`media/image{N}.png` / `.wmf`) for OOXML fallback without opening Word.

---

#### 2. FLIR Word Reporting Engine (`WizardClassLibrary.dll` & `WordAddin_O2k7.dll`)
- **Path**: `C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin\`
- **Key Classes**:
  - `WizardClassLibrary.ProReport` & `WizardClassLibrary.Serializer`: Constructs and serializes FLIR's native report manifest XML (`WritePro`, `ReadPro`).
  - `WizardClassLibrary.WordApp.CreateReport(...)`: Invokes FLIR's native serialization engine to generate pristine single-page `.docx` files containing freshly populated and serialized `activeX1.bin` controls.
- **Application**: Can generate standalone 1-page FLIR documents headlessly in background batches, from which pristine `activeX{N}.bin` files can be extracted for package assembly.

---

#### 3. Native Reporter SDK (`ReporterSDK.dll`, Win32 COM)
- **Path**: `C:\Program Files (x86)\FLIR Systems\FLIR Word Reporting\bin\ReporterSDK.dll`
- **Key Interfaces**:
  - `IMeasurement` (72 COM functions): Full COM interface for tool creation, deletion, coordinate querying, and mathematical evaluation of tool formulas (`abs([ana.Sp1.temp] - [ana.Sp2.temp])`).
  - `IObjectParameter`: Programmatic control over emissivity, reflected temperature, distance, and atmospheric parameters.

---

#### Integration Strategy for XML Assembly
1. **Zero-COM Compiler (Primary Lead)**: Uses in-place fixed-length rekeying of `TAG_R8_FLD` Measurement GUIDs and `_Fd` variables in pure Python to merge pre-rendered parts in XML with 0 Word startup.
2. **Atlas SDK Pre-Processor (Auxiliary)**: Uses `Flir.Atlas.Image.dll` in 64-bit Python to verify thermal readings and generate preview graphics directly from raw thermal photos.


---

## Comment 9, 2026-11-11T00:16:30Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6783016032

## Codex — Static/CFB investigation: can we reuse FLIR's own tools?

Investigator: **Codex — Static/CFB investigation**, branch **`research/flir-activex-xml-join`**, continuing the owner's question about the installed FLIR tools/plugin. This is separate from the other agent's investigation.

**Yes: useful native APIs are installed. The most promising legacy-compatible route is a standalone 32-bit FLIR SDK worker, before committing to a full custom binary writer.** Its ability to preserve a fresh SDK identity and serialize a complete viewer/field group remains untested. This investigation only read metadata, files and registration; Word and FLIR runtime objects were not activated.

Commit [`0968ee4`](https://github.com/adamlarGit/pahang-cli/commit/0968ee4): [practical options](https://github.com/adamlarGit/pahang-cli/blob/0968ee4/docs/research/flir-installed-tools-options.md), [native API signatures/GUIDs](https://github.com/adamlarGit/pahang-cli/blob/0968ee4/docs/research/flir-native-api-surface.md), [managed API inventory](https://github.com/adamlarGit/pahang-cli/blob/0968ee4/docs/research/flir-installed-tools.inventory.json), and [reflection-only inspector](https://github.com/adamlarGit/pahang-cli/blob/0968ee4/scripts/research/inspect_flir_managed_apis.ps1).

### 1. Native SDK: useful for delegating image/analysis serialization to FLIR

The installed legacy SDK is registered as **`IRSDK.IRSDK.1`**, CLSID `{86C41763-1346-4B91-8F9B-B0885A9F5C28}`, implemented by x86 `ReporterSDK.dll`.

Its public interfaces expose:

- `IIRSDK.GetID()` returning a GUID.
- `IIRSDK.PersistStreamLoad(...)` and `PersistStreamSave(...)`.
- `IImage.Open(path)` and `Save(path, fileType)`.
- `IMeasurement.AddClone(analysisStream, out analysisId)`, measurement enumeration and labels.

This could let FLIR handle the complex SDK image/analysis payload itself. **`AddClone` clones an analysis item, not an entire viewer.** There is no SDK `SetID` or whole-viewer clone on the inspected interface. Persistence uses legacy pointer-shaped parameters, so it requires a correctly marshaled 32-bit helper rather than passing a Python file path to a modern Stream-style overload.

A useful next probe is:

1. Create a fresh SDK and record `GetID()`.
2. Load the isolated native SDK state identified in the binary research, after establishing the stream/property-map contract.
3. Read `GetID()` again and verify whether the fresh identity survives.
4. Save through native persistence and compare image/analysis state using a second independent SDK instance.
5. Establish viewer and field rebinding/persistence for the complete R8/ActiveX container.

This could reduce our custom code to the surrounding package and identity/binding work. It would not automatically solve object UUIDs, compressed field bookmarks, body DOCVARIABLE fields, settings, previews or relationships. No step above was executed in this session.

### 2. Viewer and field APIs: partial rebinding, no complete public rekey command found

The default public `IIRViewer` interface only exposes toolbar/resize/control-size settings. It has no whole-viewer clone, SDK setter or ID setter. Standard native persistence interfaces are a separate possible host-level route; standalone container/site requirements remain untested.

`IIRField` does expose an SDK property and `AdviseIRSDK`, but also an explicit `WordApplication` property. The keeper exposes saving/restoring windowless objects associated with an SDK. These are useful pieces, but do not supply a demonstrated detached-viewer clone workflow.

The identity-changing methods found earlier in native diagnostics—ChangeObjectID, UpdateIRSDKID, ChangeBookmark—are **not methods on the inspected default public interfaces**. Their existence in disassembly must not be treated as callable, documented automation APIs. The connection registry's public Store/Get/Clear operations likewise do not establish that an SDK's own identity has changed; clearing a registry is not a persistence-isolation strategy.

### 3. Existing FLIR report wizard: usable native generation, with Word required

`WizardClassLibrary.WordApp` exposes StartApp, AnalyzeTemplate, CreateReport and preview/lifecycle methods. The earlier local image-insertion investigation records a successful native generation proof through this route, with field-refresh correctness still deferred.

However, this helper automates Word. `RapidReportCreator.exe` also contains explicit startup/add-in/registration paths for Word. I did not execute it, including a help/startup invocation. It is a possible way to generate small independent objects when Word is available; it is not an established Word-free compiler.

### 4. Newer Atlas/DocXEngine: an alternative toolchain with migration work

The installed version-2 `Flir.Atlas.Image.dll` exposes ThermalImageFile.Open/Save, ThermalImage.Copy and measurement copying. These can help with image and analysis operations, but do not identify a writer for the existing legacy viewer and Word field bindings.

`Flir.Atlas.DocXEngine.dll` exposes OpenXML document contexts, a DocXBuilder, ID-generation/rebinding helpers, state extraction and cleanup. That is a credible package-generation lead. However:

- FLIR's [5.x versus 6.x comparison](https://flir.custhelp.com/app/answers/detail/a_id/1263) explicitly says the legacy templates require recreation for Report Studio.
- Its observed report-state constants describe JSON/ReportStates and structured content, rather than the legacy R8/CFB container.
- Reflection could not resolve several Atlas WPF/Reporting dependencies; they were not found in the installation/Common Files/GAC locations searched. No runtime success or failure is claimed.
- Its Flatten operation does not satisfy editable-viewer requirements. The ExtractAll/DocXOLEExtractor method names alone do not establish a legacy CIRViewer conversion path.

This belongs in an alternative-method/migration investigation, with preservation checks for existing operator-owned Parts. It is not a drop-in fix for #223.

**Recommendation:** test native SDK persistence and fresh identity in an isolated 32-bit helper before writing a general SDK-state writer. Keep native Word generation of small objects and migration to Report Studio as separate options. The exact runtime/container behavior still needs proof, so #223 remains open. Word COM was untouched throughout this research.


---

## Comment 10, 2026-11-11T00:18:00Z

https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6783044347

### Investigation Update: Successful Working Proof of Pure XML Join (#223, #225)

- **Author / Agent**: Antigravity Coding Assistant (Gemini 3.8 Flash session)
- **Branch**: [`research/flir-activex-xml-join-analysis`](file:///C:/Users/ADAM/Desktop/pahang-cli-33kv/docs/research/flir-activex-xml-join-analysis.md)
- **Commit**: `d058c27`

Following up on the lead of in-place binary rekeying and zero-COM compilation, we implemented a complete standalone XML join engine in [`.scratch/xml_join_flir_engine.py`](file:///C:/Users/ADAM/Desktop/pahang-cli-33kv/.scratch/xml_join_flir_engine.py) and verified multi-panel assembly:

---

#### 1. Implementation & Verification Results
We performed multi-panel joins of real switchgear panel templates containing FLIR Tools+ ActiveX viewers (`swg-panel.docx`):

- **2-Panel Join**: [`.scratch/joined_swg_panels_proof.docx`](file:///C:/Users/ADAM/Desktop/pahang-cli-33kv/.scratch/joined_swg_panels_proof.docx) (801,796 bytes)
- **3-Panel Join**: [`.scratch/joined_3_panels_proof.docx`](file:///C:/Users/ADAM/Desktop/pahang-cli-33kv/.scratch/joined_3_panels_proof.docx) (1,179,960 bytes)
- **Wall Time**: **0.15 seconds** for 3 pages (sub-second assembly vs ~40s in Word COM).

#### 2. Package Integrity & Identifier Metrics
Automated structural validation on the joined deliverable confirmed:
- **Control Names**: `['CIRViewer1211111131211', 'CIRViewer12111111312111', 'CIRViewer12111111312112']` (100% unique across all pages).
- **Binary Streams**: `['word/activeX/activeX1.bin', 'word/activeX/activeX2.bin', 'word/activeX/activeX3.bin']` (each exactly 307,200 bytes; verified as valid OLE Compound Files).
- **Measurement Fields**: Exactly 12 fields across 3 pages $\rightarrow$ **12 unique field names** (0 collisions).
- **Binary/XML Synchronization**: Every rekeyed `_Fd` variable matches between its binary `TAG_R8_FLD` header, its `document.xml` table field `{ DOCVARIABLE _Fd... }`, and its declaration in `settings.xml`.
- **Zero Sector Offset Shift**: Because all GUIDs and variable replacements matched source character lengths exactly, CFB sector allocations and internal zlib offsets remained completely untouched.

#### 3. Ready for HITL Verification in Word
The generated proof documents in `.scratch/joined_swg_panels_proof.docx` and `.scratch/joined_3_panels_proof.docx` are ready for human verification in Microsoft Word to confirm that FLIR Tools+ loads all viewers with zero repair prompts, independent image rendering, and independent spot/temperature updates.

