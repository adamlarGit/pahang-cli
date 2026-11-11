# FLIR ActiveX XML joining: research for #223

Date: 2026-11-11. Scope: static package inspection and primary format specifications. Word COM and interactive FLIR behavior were not exercised. This note informs an experiment; it does not replace ADR 0002.

Investigation identity: **Codex — Static/CFB investigation**, branch `research/flir-activex-xml-join`. A separate agent is investigating in parallel; these findings should remain distinguishable from its results. Ticket: [#223](https://github.com/adamlarGit/pahang-cli/issues/223).

**Later continuation:** [FLIR binary anatomy](flir-binary-anatomy.md) decodes the R8/KENT layers, 187 compressed blocks and 111 field records. Static native-code inspection identifies object/SDK UUIDs and a GUID-based SDK reuse path. Read that addendum for the stronger mechanism and concrete rewrite targets; the earlier uncertainty below records the first research pass.

## Verdict boundary

**Can't tell without a prototype.** The standard package plumbing can be copied and remapped outside Word. The harder question is whether FLIR's private persisted identities can safely coexist or be regenerated. Microsoft explicitly assigns the content of an ActiveX persistence binary to the control itself, rather than defining a universal serialization format. A valid OPC package therefore cannot establish editable, independent viewers or correct measurement-field updates. [MS-OI29500 §3.4.1.1](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/2c6688de-be08-4ffa-ac54-32d19ebc4ca3)

**The decisive local finding:** `_Fd…` measurement identifiers occur in the live `Contents` stream inside the CFB binary, matching the body fields. Renaming just the XML cannot keep those bindings consistent. Copying the same template twice without changing its binaries preserves duplicate private identifiers. That is a concrete unresolved obstacle to independent readings, even if control names, part names and shape IDs are made unique. It does not prove image crosstalk is inevitable, or that FLIR cannot reassign identities on load. Neither behavior was tested.

The result leaves at least three routes open: package-copy joins of already independent native objects; a researched, format-aware binary rewrite; or native FLIR generation/rekeying of small independent objects before package assembly. None is adopted here. The existing Word compiler and ADR 0002 remain the production policy.

## Local evidence and reproducibility

Read-only inspection covered ten distinct DOCX files and 38 ActiveX binaries: the seven Full Report `NORMAL IR US TEV` templates, Quick Report `DEFECT IR/swg-panel.docx`, and Talapia's Quick and Full Reports. Every binary was parsed as CFB, with one live stream named `Contents` and root CLSID `C5F5764B-B932-4F33-8BF3-9941F22FAE18`. Source hashes before and immediately after inspection matched. No Word, COM, clipboard operations, application workflows or test suites were used.

The inventory helper is [inspect_flir_package.py](../../scripts/research/inspect_flir_package.py). It uses `zipfile`, `lxml` and `olefile`, imports no application code, and writes JSON to standard output. The observed environment had lxml 6.1.1 and olefile 0.47. For a standalone invocation without changing the dependency lock:

```powershell
uv run --frozen --with olefile==0.47 python scripts/research/inspect_flir_package.py 'templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx'
```

The committed [inventory](flir-activex-xml-join.inventory.json) records source hashes, binary hashes, logical-stream hashes, field IDs, UUID strings and the count discrepancies. Full XML dumps remain in ignored scratch files; the source documents are not copied into Git. The inspector concatenates field instruction text to handle split runs; it inventories literal ASCII `_Fd`/UUID records rather than implementing a FLIR binary decoder or a general Word field evaluator.

| Inspected artifact | Controls / binaries | Body `DOCVARIABLE` uses / unique names | `w:docVar` entries |
| --- | ---: | ---: | ---: |
| Full Report normal `swg-panel.docx` | 1 / 1 | 4 / 4 | 3,855 |
| Quick Report defect IR `swg-panel.docx` | 1 / 1 | 4 / 4 | 3,790 |
| Talapia **Quick Report** | 3 / 3 | 9 / 9 | 1,896 |
| Talapia **Full Report** | 27 / 27 | 99 / 90 | 4,025 |

The Talapia documents are under `PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD/{QUICK REPORT,FULL REPORT}/RAUB/01. AUGUST/04-08-2026/005. TALAPIA (IR+VI).docx`. The checked benchmark is a single Full Report file, rather than a `Part NN` file. In these local inputs, the 27/99/90/4,025 figures in #223's review comment identify the **Full Report**, despite its Quick Report label. [#231](https://github.com/adamlarGit/pahang-cli/issues/231) repeats the 27-viewer Quick Report assumption; a prototype must select its source by path and hash before choosing bounds.

### One viewer, with its actual identifiers

The normal Full Report `swg-panel.docx` contains this graph:

```text
word/document.xml
  w:object
    v:shape id="_x0000_i1032" type="#_x0000_t75"
      v:imagedata r:id="rId7"             saved visual preview
    w:control w:name="CIRViewer1211111131211"
              w:shapeid="_x0000_i1032" r:id="rId8"
    (rId7 and rId8 resolve through the following owner-local relationships)
word/_rels/document.xml.rels
  rId7 -- image --> media/image2.wmf
  rId8 -- control --> activeX/activeX1.xml
                           |
word/activeX/activeX1.xml
  ax:ocx classid="{C5F5764B-B932-4F33-8BF3-9941F22FAE18}"
         persistence="persistStorage" r:id="rId1"
                           |
word/activeX/_rels/activeX1.xml.rels
  rId1 -- activeXControlBinary --> activeX1.bin
                           |
word/activeX/activeX1.bin    CFB file: 307,200 bytes
  root CLSID: same FLIR class
  Contents stream: 300,182 bytes, proprietary persisted viewer state
    offset   98: TAG_R8_FLD; offset  113: _Fd1922861825
    offset  565: TAG_R8_FLD; offset  580: _Fd1967887225
    offset 1024: TAG_R8_FLD; offset 1039: _Fd81475520
    offset 1480: TAG_R8_FLD; offset 1495: _Fd97091050

Separate name binding, not an OPC relationship:
word/document.xml: DOCVARIABLE _Fd1967887225 (and the other three names)
  --> word/settings.xml: w:docVar with the same w:name and its stored value
```

Offsets above are in the **logical `Contents` stream**, not raw CFB file offsets. The body has no `o:OLEObject` in any of the four main inspected artifacts: for these controls, the preview is the sibling VML shape and image relationship. An OLEObject-specific importer alone would miss this chain.

`[Content_Types].xml` gives `/word/activeX/activeX1.xml` the override `application/vnd.ms-office.activeX+xml`; the binary has effective type `application/vnd.ms-office.activeX` through the `bin` default; the preview uses `image/x-wmf`. A join must preserve the effective type of each imported part, using per-part overrides when extension defaults conflict. The XML has the two distinct relationship types shown above; those types must be preserved rather than guessed from filenames.

### Binary identity and image lookup

All four template fields match literal `_Fd` records inside `Contents`. The seven normal Full Report templates have mutually disjoint extracted field-name sets, but a second instance of **any one** template necessarily starts with its same field-name set. Their other ASCII UUID strings also survive a byte-for-byte copy. In the field-bearing template streams, UUID strings occur near field records; their exact roles, binary-encoded identifiers, length fields and possible integrity checks are not decoded. No control `w:name` was found as a literal ASCII string in its `Contents`; that narrow negative result does not prove the control name is irrelevant to the add-in.

For the Talapia Quick Report, all nine body field names occur in the three live binaries, with no field name shared between binaries. In the Full Report, 79 of the 90 unique body names occur in live binary field records, again with no name shared between binaries. No extracted ASCII UUID string is shared between two binaries within either report. These observations make binary field/owner identity a stronger investigation target than globally renumbering every field occurrence.

**Suspected mechanism, not a proven root cause:** the private viewer state supplies measurement identities, and Word fields read the named document-variable values. An accidental shared producer identity or shared variable binding could couple viewers or their readings. The external WMF is a saved preview; copying it is insufficient to establish editable thermal state. The documented ActiveX loader obtains persisted state from the binary relationship, but the precise way CIRViewer/add-in locates and distinguishes its internal radiometric image and measurement objects remains unknown. These specifications do not establish whether private UUIDs, control names or another runtime key determines image crosstalk. A byte-preserving join avoids rewriting its payload, but cannot by itself prove isolation.

### Explaining the Talapia repeats

The nine repeated field names occur in separate TX1 and TX2 tables: four in OVERVIEW, one in OVERVIEW TOP and four in LV BUSHING. Their cached displayed values are pairwise equal. They are real repeated references, rather than duplicate `mc:Choice`/`mc:Fallback` encodings of a field. All nine names are absent from the literal ASCII field records in **every** parsed live `Contents` stream. Two more unique body names are also absent. All 90 unique names do have entries in `settings.xml`.

This explains why 99 fields can resolve to 90 stored bindings. It does **not** establish why the author reused those bindings across TX1/TX2, whether they update correctly, or whether metadata was intentionally removed. Treat these tables as an explicit prototype test case, rather than evidence that independent viewers may safely share a live producer binding.

There are 11 fallback VML arrow shapes: `Straight Arrow Connector 3` occurs twice and `Straight Arrow Connector 19` nine times, giving nine extra occurrences across two repeated names. They also repeat `o:spid="_x0000_s1026"`. These are annotation fallback shapes; they are not the 27 FLIR control shapes, whose IDs and control references are unique. Current Word can choose supported DrawingML `mc:Choice` branches instead. A legacy consumer selecting all these fallbacks may still encounter repeated IDs; compatibility markup does not make every repeated ID conforming. Preserve annotation alternatives and their local links when investigating a join.

There is also direct operator evidence against equating a repeated control name with observed crosstalk: [#196's closure](https://github.com/adamlarGit/pahang-cli/issues/196#issuecomment-6725309030) reports editing thermal images on every page of two duplicate-name Parts without crosstalk. That does not prove all duplicate-name cases safe, but it means uniqueness is a conformance/checking rule, not a demonstrated sole runtime isolation key.

### What the ADR's binary-header claim establishes

ADR 0002 records a regression correlated with `Saved = False`, a 307,200-to-303,104-byte size change and loss of `TAG_R8_FLD`. Git confirms that [7a1ecb0](https://github.com/adamlarGit/pahang-cli/commit/7a1ecb08b85e42e00f937fa346cca2ed016afc84) added the `Saved` assignment and [3b98d0f](https://github.com/adamlarGit/pahang-cli/commit/3b98d0f17201c015cda965a620c6ad81275b95ff) left it removed while restoring the original `Documents.Add()` order. This research did not rerun that historical comparison or independently establish its causal serialization mechanism.

The measured marker is **not the CFB file header**: the file begins with `D0 CF 11 E0 A1 B1 1A E1`, and its logical `Contents` includes four separate `TAG_R8_FLD` records at the offsets above. The raw file has eight marker occurrences while the live stream has four, so counting raw marker strings is not even a count of live measurement records. A 4,096-byte file-size delta does not independently prove that a single proprietary 4 KB header was removed. That interpretation needs a before/after logical-stream diff and interactive behavior evidence.

Further, six Full Report benchmark binaries have no `TAG_R8_FLD` or literal ASCII `_Fd` record in their live stream: `activeX1`, `activeX2`, `activeX11`, `activeX16`, `activeX18` and `activeX23`. They remain parseable CFB files with the FLIR CLSID. No conclusion about their interactive health follows from that observation. Across all ten inputs, binary sizes range from 174,080 to 1,186,816 bytes. The correct preservation check is against each source's exact bytes/hash, not a universal size or an assumption that every viewer must contain field records. [ADR 0002's dated update](../adr/0002-word-com-activex-report-compilation.md), [#179 diagnosis and correction](https://github.com/adamlarGit/pahang-cli/issues/179)

Copying `.bin` parts unchanged avoids **introducing byte-level CFB damage during assembly**; it cannot cure damaged source state, resolve duplicated private identities or guarantee what Word/FLIR will serialize on the next save. The historical `Saved = False` constraint still governs the production COM path. It is not a direct operation in a ZIP/XML join, and does not by itself forbid that research route.

## Copy / rename / renumber checklist

| Action | Required handling |
| --- | --- |
| Rename imported parts when names collide | ActiveX XML, ActiveX binary and preview parts; map every owning relationship target and content-type override. Copy complete dependency graphs, not just `document.xml` fragments. |
| Renumber merged relationships | Allocate unused IDs within each merged owner. `document.xml` and `activeXN.xml` have different ID scopes; copied persistence XML can keep its local `rId1`. Update `r:id`, `r:embed`, `r:link` and other applicable references in all imported stories and compatibility branches. |
| Renumber drawings / shape links | Unique `wp:docPr/@id`; resolve coexisting VML identity collisions while maintaining `w:shapeid`, `o:spid`, applicable `ShapeID` and shape-type references. Handle matching alternatives together. |
| Rename control names for conformance | Resolve `w:control/@w:name` collisions, but do not claim that this alone creates native FLIR independence. |
| Keep each variable binding consistent | Multiple occurrences can share one binding intentionally. Independent producers cannot use one document-variable slot for different readings. Changing a live `_Fd` binding requires coordinated binary and XML changes or a native rekey mechanism; no verified algorithm is supplied here. |
| Copy unchanged in the initial experiment | Entire binary byte sequences, CLSID, persistence mode, optional license, previews and crop/placement metadata, field instructions/results/formatting and referenced variable values, annotation alternatives and their dependencies. Preserve FLIR custom properties and units. |
| Do not blindly renumber | Private UUIDs, binary field IDs, constants, CLSIDs, every `DOCVARIABLE` occurrence or all `w:docVar` entries. Their semantics and cross-references differ. |

The template custom properties are `FLIR`, `FlirTempUnit` and `FlirDistUnit`. Two source documents with incompatible unit settings require an explicit policy or rejection; taking the destination properties silently is not evidence of preserved measurements. A complete report join also needs the usual styles/numbering, sections, headers/footers, bookmarks, comments and other annotation mappings. This checklist identifies the ActiveX obstacle; it is not a complete general DOCX composer design.

## What the specifications establish

### Package and display chain

`w:control/@r:id` locates the embedded control's persistence part using the relationships owned by its containing story part, normally `word/document.xml`. Its `w:shapeid` associates the visible shape with the control. When the control cannot run, a saved display representation is used. The ActiveX persistence XML contains `ax:ocx`: `ax:classid` selects the COM class, `ax:persistence` identifies the persistence interface, and its own `r:id` locates the binary through a second relationships file. The relationship types are respectively `.../relationships/control` and `http://schemas.microsoft.com/office/2006/relationships/activeXControlBinary`. [WordprocessingML Control](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.control?view=openxml-3.0.1), [MS-OI29500 §3.6.1.2](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/48c99072-6cf7-4e69-84b1-3bea64f0ee3a)

`persistStorage` means `IPersistStorage`; `persistStream` and `persistStreamInit` select their corresponding interfaces. `persistPropertyBag` uses child properties instead of a referenced persistence binary. Neither the persistence interface name nor a `.bin` suffix specifies FLIR's private record layout. [MS-OI29500 §3.6.2.1](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/6b964c2d-eff6-40fc-becc-6116a4ad1458)

An `o:OLEObject` is another embedded-object representation with its own relationship to object data and `ShapeID` pointing to the VML placeholder. It should be inspected when present, rather than assumed to be a mandatory additional link in every ActiveX `w:control` chain. [ECMA-376 Part 4 §19.2.2.20](https://ecma-international.org/wp-content/uploads/ECMA-376-4_5th_edition_december_2016.zip)

### Identifier scopes and remapping

| Item | Scope / rule | Consequence for an XML join |
| --- | --- | --- |
| OPC part name | Unique within the package; ASCII case-insensitive comparison. | Allocate unused names for imported ActiveX XML, binaries, previews and other dependent parts. Rebase relationship targets and content-type overrides. |
| Relationship `Id` | Unique within its owning Relationships part. | Remap relationships merged into `document.xml.rels`; a copied `activeXN.xml.rels` may retain `rId1`, because it has a different owner. Preserve every XML reference that uses the mapped ID. |
| `w:control/@w:name` | Unique across controls in the document. | Resolve collisions across imported controls, with any FLIR references investigated before treating renaming as sufficient. |
| `wp:docPr/@id` | Unique within the document. | Assign a positive unused number. Word rejects 0 and values above 2147483646. Do not confuse the drawing's `name` with the ActiveX control's `w:name`. |
| VML `id`, `o:spid`, control `w:shapeid`, OLE `ShapeID` | Shape identity and references to it, with separate fallback representations possible. | Keep all links for each logical shape consistent. Reassign collisions in shapes that coexist after compatibility processing; preserve the corresponding alternative representations. |
| `DOCVARIABLE` argument / `w:docVar/@w:name` | An argument names a document variable in the document settings. Multiple fields can deliberately display one variable. | Rename a colliding *variable binding* consistently, rather than assigning a different name to every field occurrence. If the producer persists that binding inside its binary, XML-only rewriting is incomplete. |
| `ax:classid` and license | Class selection / licensing, rather than a universal per-instance ID. | Preserve these values; do not invent a new CLSID for each viewer. |
| FLIR private field IDs / GUIDs | Not assigned a meaning or uniqueness rule by these OOXML specifications. | Discover their semantics before changing them; preserve opaque bytes in the initial package-copy experiment and explicitly test duplicate identities. |

Sources: [ECMA-376 Part 2 §§6.2.2 and 6.5.3](https://ecma-international.org/wp-content/uploads/ECMA-376-2_5th_edition_december_2021.zip), [PackageRelationship.Id](https://learn.microsoft.com/en-us/dotnet/api/system.io.packaging.packagerelationship.id?view=windowsdesktop-9.0), [ECMA-376 Part 1 §§17.3.3.3, 17.16.5.15 and 20.4.2.5](https://ecma-international.org/wp-content/uploads/ECMA-376-1_5th_edition_december_2016.zip), [Word docPr restrictions](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/e7d7aeab-16eb-4963-9338-39953b8fee37), [VML ID](https://learn.microsoft.com/en-us/windows/win32/vml/id-attribute--vml), [MS-OI29500 ocx](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/48c99072-6cf7-4e69-84b1-3bea64f0ee3a).

### Why repeated names are not all collisions

`DOCVARIABLE` displays the value assigned to its named document variable. Repeated field uses are allowed by that model; they are references to one binding, not duplicate declarations. Word's Variables collection rejects a second declaration with an existing name. Consequently, the reported 99 fields with 90 names do not alone imply corruption. What matters is whether a name is accidentally shared by independent producers. [ECMA-376 Part 1 §17.16.5.15](https://ecma-international.org/wp-content/uploads/ECMA-376-1_5th_edition_december_2016.zip), [Variables.Add](https://learn.microsoft.com/en-us/office/vba/api/word.variables.add), [DocumentVariable](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.documentvariable?view=openxml-3.0.1)

Markup compatibility chooses the first supported `mc:Choice`, or `mc:Fallback` when no Choice applies. Only the selected representation enters the processed document. A raw count traversing all branches can therefore count alternatives together. This explains why a duplicate in fallback markup is not automatically a duplicate active object; actual ancestry and the applicable branch must still be checked. The mere presence of `mc:Fallback` is not a blanket exemption for repeated IDs across different active objects. [ECMA-376 Part 3 §§9.3–9.4](https://ecma-international.org/wp-content/uploads/ECMA-376-3_5th_edition_december_2015.zip)

### Which binary specification applies

CFB provides storage directories, streams and allocation tables. MS-OLEDS describes OLE object data structures. MS-OFORMS defines Microsoft Office Forms control persistence. Those are different layers: discovering a CFB container or an ActiveX part does not establish that its application-specific stream uses Office Forms records. MS-DOCX documents Word's XML extensions, not the complete private persistence format of every third-party control. [MS-CFB Introduction](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-cfb/50708a61-81d9-49c8-ab9c-43c98a795242), [MS-OLEDS Introduction](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-oleds/554a69b6-497a-4fef-a0fe-792d0dcf50fb), [MS-OFORMS](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-oforms/9c79701a-8c3e-4429-a139-b60ac3a1d50a), [MS-DOCX](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/b839fe1f-e1ca-4fa6-8c26-5954d0abbccd)

**Inference:** copying an intact `.bin` part under a new ZIP entry name leaves its internal CFB offsets and bytes intact. Changing XML attributes in another part cannot mechanically alter those internal offsets. It can still invalidate the control's semantic binding to the surrounding document, including private field IDs. ADR 0002's observed corruption therefore remains evidence to investigate, while its explanation that XML renaming itself breaks binary offsets is not established by the file-format model.

## Constraints for a future slice experiment

A deletion-only slice can retain the source identifiers and opaque binaries, since it creates no new coexistence collisions. Keep the complete subgraph needed by retained content, including both compatibility alternatives, and keep its relevant document-variable bindings. Delete a relationship/part only after proving no retained package source or retained implicit-format dependency still needs it. Reachability from body `r:id` attributes alone is insufficient: settings, styles, numbering, headers, footers and other parts also participate. Treat arbitrary custom properties and FLIR data conservatively until their semantics are understood.

This is an experiment-design inference, not a guarantee that FLIR tolerates every deletion. A slice still needs reopen/edit/save validation, and an assembly of slices again needs collision analysis.

For #231, the conservative first proof should:

1. Copy the package and delete only out-of-bounds body blocks, retaining the final `w:sectPr` and namespace/compatibility declarations. Preserve the effective section properties of retained content too: in a document with multiple sections, keeping only the original last `sectPr` can apply the wrong layout. Retain identifiers for surviving objects rather than inventing a new identity space.
2. Keep the relevant document-level parts and implicit dependencies. Remove an unused *explicit* relationship only after checking every retained use in its owning part, including both compatibility representations. Header/footer references from section properties use the document's relationships; content inside each retained header/footer has its own relationship scope, which also needs inspection. Merely keeping all original relationships makes their parts appear reachable even when the body no longer uses them, so that is preservation rather than pruning.
3. Follow the retained relationships transitively from package roots and necessary document parts. Delete a candidate part only when neither a retained explicit relationship nor a known implicit-format dependency requires it. Prune its relationships file and content-type override consistently. A retained ActiveX XML keeps its binary; a retained preview shape keeps its image. No requirement exists for the old numbering of surviving part names to be contiguous.
4. Keep **all source `w:docVar` entries and FLIR custom properties for the initial proof**, and report their retained count. Body-only name matching is insufficient justification for deleting variables when binary records and private add-in dependencies are not fully decoded. An unused variable binding is not an OPC part; graph pruning cannot decide whether it is safe to delete.
5. Compare each retained binary, preview and measurement binding with its source and record hashes before any Word save. Then perform #231's separate Word/FLIR, export and COM-compiler comparisons when Word is available. A package inventory pass cannot substitute for any of those behavior checks.

## Questions that a later prototype must discriminate

Keep separate experiments for **two independently persisted objects** and **two copies of the same template/object**. Success on the first cannot establish a compiler for repeated switchgear pages. For the repeated-object case, name the private-identity strategy before claiming a fix: retain-and-test possible native reassignment, native object generation/rekeying, or a separately justified binary decoder/rewriter.

Use deliberately distinct thermal images and readings. Change one viewer's image, palette/range and spot/area tools; confirm its linked temperature fields update and the other viewer and its readings remain unchanged. Repeat in both directions after save, close and fresh reopen. Include the Talapia TX1/TX2 repeated-field case and the two #196 duplicate-control-name counterexamples when interpreting results. Check repair prompts, annotation/layout preservation and export fidelity separately. The marker's presence, unique XML names, equal cached readings or a visible preview alone cannot certify success.

No prototype or binary mutation was performed in this investigation. The ticket should remain open for the parallel research and whichever experiment or alternative methodology the owner chooses next. No new ADR or domain term is introduced: no production architecture decision has been made.
