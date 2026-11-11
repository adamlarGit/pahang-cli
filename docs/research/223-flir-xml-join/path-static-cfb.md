---
ticket: 223
type: research
map: 221
path: static-cfb
status: open
updated: 2026-11-11
agent: Codex (original work); Claude Code, claude-fable-5-2 (conversion)
---
# What do the package and each viewer's binary hold, and what must change for an XML join?

## Question for this Path

Which parts, relationships and identifiers make up one FLIR viewer in a docx, which of them live inside the binary, and which must be renamed, renumbered or copied unchanged when two documents are joined outside Word?

## Verdict

A join is not ruled out, and it has concrete targets. Each viewer carries three identities that a join has to keep consistent: an object UUID, an SDK UUID and, for every measurement field, a Word bookmark that is stored twice (C9 to C11). The package plumbing around the binary can be copied and remapped by the usual OOXML rules. This Path built no join and ran nothing in Word, so on its own it ends at "can't tell without a prototype".

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | Ten docx files hold 38 viewer binaries. Each binary is a CFB file with one stream named `Contents` and root CLSID `C5F5764B-B932-4F33-8BF3-9941F22FAE18`. | Tested | `evidence/static-cfb/inspect_flir_package.py`, `evidence/static-cfb/flir-activex-xml-join.inventory.json` |
| C2 | A viewer is reached through two relationship hops: `w:control` to `activeXN.xml`, then to `activeXN.bin`. Its preview is a sibling VML shape with its own image relationship. No `o:OLEObject` is involved. | Tested | same script and inventory |
| C3 | In the Full Report `swg-panel.docx`, `Contents` is 300,182 bytes inside a 307,200-byte CFB file and holds four `TAG_R8_FLD` records, with field names at offsets 113, 580, 1039 and 1495. | Tested | same script and inventory |
| C4 | The four body `DOCVARIABLE` names of that template occur as ASCII in `Contents`, and each has a `w:docVar` in `settings.xml`. | Tested | same script and inventory |
| C5 | No control `w:name` occurs as ASCII in its own `Contents`. | Tested | same script and inventory |
| C6 | The Talapia Full Report has 27 controls, 99 `DOCVARIABLE` uses, 90 unique names and 4,025 `w:docVar` entries. The Quick Report has 3, 9, 9 and 1,896. The 27, 99 and 90 figures quoted on the ticket belong to the Full Report. | Tested | same script and inventory |
| C7 | The nine repeated Talapia names sit in the TX1 and TX2 tables (four in OVERVIEW, one in OVERVIEW TOP, four in LV BUSHING) with equal cached values. They are repeated references to one variable, and none of the nine occurs in any binary's field records. | Read | The Talapia Full Report `document.xml`, as described in `evidence/static-cfb/original/flir-activex-xml-join.md`. No command was recorded. |
| C8 | In the Talapia Full Report, 79 of the 90 names occur in binary field records and no name or ASCII UUID is shared between two binaries. | Tested | same script and inventory |
| C9 | Every viewer and every nested field starts with a length-prefixed `R8:0.1`, an object UUID, an SDK UUID and a flag byte, in that order. | Tested | `evidence/static-cfb/decode_flir_contents.py`, `evidence/static-cfb/flir-binary-anatomy.inventory.json` |
| C10 | All 111 nested fields carry the SDK UUID of their parent viewer. In `swg-panel.docx` the object UUID is `f0ff1a2f-6150-4fa9-ae4c-a199a4ec68ec` and the SDK UUID is `65f355f7-d614-4afe-85c8-dff34b8c47c7`. | Tested | same decoder and inventory |
| C11 | The decimal suffix of each `_Fd` name is also stored as a little-endian uint32 inside that field's compressed archive, in 111 of 111 fields. | Tested | same decoder and inventory. `evidence/static-cfb/decompressed-267.bin` is the first field archive of `swg-panel.docx`, inflated, with 1922861825 at offset 52. |
| C12 | The six Talapia viewers with no `TAG_R8_FLD` (1, 2, 11, 16, 18, 23) have an explicit empty field list ending in `TAG_R8_END`. Their R8 wrapper is intact. | Tested | same decoder and inventory |
| C13 | After the wrappers the data uses 10-byte KENT frames, and all 187 zlib blocks pass their checksum and match their declared sizes. | Tested | same decoder and inventory |
| C14 | The viewer's SDK state inflates from 298,075 to 625,696 bytes in `swg-panel.docx`. Its record 1017 holds the original image path, the camera model and a 640 by 480 uint16 image plane. | Tested | same decoder and inventory. `evidence/static-cfb/binary-plane-preview.png` is that plane drawn as an image. |
| C15 | Talapia Quick Report viewers 1 to 3 hold byte-identical image records to Full Report viewers 25 to 27, while their UUIDs and field names differ. | Tested | same decoder and inventory |
| C16 | The native viewer looks up its SDK GUID in a registry. If an SDK is already registered under that GUID it attaches to it, and otherwise it creates one. | Read | Static disassembly at VA `0x1004cc20`, recorded with DLL hashes in `evidence/static-cfb/original/flir-binary-implementation-notes.md`. The code was not executed. |
| C17 | Two viewers that keep one SDK GUID can attach to one live SDK and share image state, whatever their part names, relationship IDs and control names. | Assumed | none. Inferred from C16. Settled by joining two copies of one viewer without changing the SDK GUID and editing one of them. |
| C18 | The `TAG_R8_FLD` marker is a per-field tag and the file starts with the CFB signature. The raw file holds eight marker strings where the live stream holds four. | Tested | `evidence/static-cfb/inspect_flir_package.py` and inventory |
| C19 | ADR 0002's `Saved = False` regression went with a size change from 307,200 to 303,104 bytes and the loss of `TAG_R8_FLD`. | Read | `docs/adr/0002-word-com-activex-report-compilation.md`. The comparison was not rerun. |
| C20 | The closing comment on #196 reports editing every page of two Parts with duplicate control names and seeing no crosstalk. | Read | https://github.com/adamlarGit/pahang-cli/issues/196#issuecomment-6725309030 |

## Detail

### One viewer, with its identifiers

From the Full Report `swg-panel.docx`. Offsets are in the logical `Contents` stream.

```text
word/document.xml
  w:object
    v:shape id="_x0000_i1032" type="#_x0000_t75"
      v:imagedata r:id="rId7"             saved visual preview
    w:control w:name="CIRViewer1211111131211"
              w:shapeid="_x0000_i1032" r:id="rId8"
word/_rels/document.xml.rels
  rId7 -- image --> media/image2.wmf
  rId8 -- control --> activeX/activeX1.xml
word/activeX/activeX1.xml
  ax:ocx classid="{C5F5764B-B932-4F33-8BF3-9941F22FAE18}"
         persistence="persistStorage" r:id="rId1"
word/activeX/_rels/activeX1.xml.rels
  rId1 -- activeXControlBinary --> activeX1.bin
word/activeX/activeX1.bin    CFB file: 307,200 bytes
  Contents stream: 300,182 bytes
    offset   98: TAG_R8_FLD; offset  113: _Fd1922861825
    offset  565: TAG_R8_FLD; offset  580: _Fd1967887225
    offset 1024: TAG_R8_FLD; offset 1039: _Fd81475520
    offset 1480: TAG_R8_FLD; offset 1495: _Fd97091050

Name binding, not a relationship:
word/document.xml: DOCVARIABLE _Fd1967887225 (and the other three)
  --> word/settings.xml: w:docVar with the same w:name and its stored value
```

### Inside `Contents`

```text
length-prefixed "R8:0.1"
length-prefixed object UUID
length-prefixed SDK UUID
one-byte flag
then, per field:
  length-prefixed "TAG_R8_FLD"
  length-prefixed "_Fd<decimal bookmark>"
  uint32 nested-object byte length
  nested R8 field object (own object UUID, the viewer's SDK UUID, one zlib archive)
length-prefixed "TAG_R8_END"
viewer control metadata (zlib), then viewer SDK state (zlib)
```

| `swg-panel.docx` field | Label in the archive | Bookmark uint32 |
|---|---|---:|
| `_Fd1922861825` | `Sp1.Max. Temperature` | 1922861825 |
| `_Fd1967887225` | `Sp1.Temperature` | 1967887225 |
| `_Fd81475520` | `Sp2.Temperature` | 81475520 |
| `_Fd97091050` | `Dt1` | 97091050 |

### Three identities a join must keep consistent

1. **SDK UUID.** One per viewer, repeated in each of its fields. Two copies of one source need different values to be independent.
2. **Object UUID.** One per viewer and one per field. The class CLSID stays as it is.
3. **Word bookmark.** The outer `_Fd` string, the uint32 inside the compressed field archive, every body field instruction and the `settings.xml` entry. Several body fields may share one binding on purpose.

A writer that changes the bookmark has to inflate the field archive, change the uint32, deflate it, and update the KENT lengths and the R8 nested-object length. If the stream changes size, the CFB allocation changes too.

### Rename, renumber, copy

| Action | Handling |
|---|---|
| Rename imported parts that collide | ActiveX XML, ActiveX binary and preview parts. Map every owning relationship target and content-type override. Copy whole dependency graphs. |
| Renumber merged relationships | Allocate unused IDs within each merged owner. `document.xml` and `activeXN.xml` have separate ID scopes, so a copied `activeXN.xml.rels` can keep its `rId1`. Update `r:id`, `r:embed` and `r:link` in every imported story and compatibility branch. |
| Renumber drawings and shape links | Unique `wp:docPr/@id`. Resolve VML ID collisions while keeping `w:shapeid`, `o:spid` and `ShapeID` references matched. |
| Rename control names | Resolve `w:control/@w:name` collisions. This alone does not make viewers independent. |
| Keep each variable binding consistent | A changed `_Fd` binding needs matching changes in the binary and the XML. |
| Copy unchanged | The CLSID, persistence mode, licence, previews, crop and placement, field formatting, annotation alternatives, and the FLIR custom properties `FLIR`, `FlirTempUnit` and `FlirDistUnit`. |
| Leave alone unless the meaning is known | Constants, CLSIDs, and `w:docVar` entries not tied to a joined viewer. |

The full versions, with the OOXML sources for each rule and the constraints for the #231 slice proof, are in `evidence/static-cfb/original/flir-activex-xml-join.md`.

## Open questions

1. How long does the SDK registry of C16 live, and is it scoped to a document or to the Word process?
2. Are there other copies of the SDK ID or the bookmark in record types this specimen set did not contain (`TAG_R8_TBL`, `TAG_R8_STB`)?
3. Why do the Talapia TX1 and TX2 tables share bindings, and do those fields update correctly?
4. Did `Saved = False` remove one header, as ADR 0002 says? That needs a before and after diff of the logical stream.

## How to reproduce

```
uv run --frozen --with olefile==0.47 python docs/research/223-flir-xml-join/evidence/static-cfb/inspect_flir_package.py "templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx"
uv run --frozen --with olefile==0.47 python docs/research/223-flir-xml-join/evidence/static-cfb/decode_flir_contents.py "templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx"
```

Both take one or more docx paths, only read them, and print JSON. The two inventories are those outputs for all ten documents, and `evidence/static-cfb/decoded-template.json` is the full decoder output for `swg-panel.docx` alone. The disassembly behind C16 was done with `llvm-objdump` on the installed FLIR DLLs, and its output was not kept.

## Live data read

| Path | File | Bytes | SHA-256 | Read on |
|------|------|-------|---------|---------|
| `<BASE>/QUICK REPORT/RAUB/01. AUGUST/04-08-2026/` | `005. TALAPIA (IR+VI).docx` | not recorded | `772df026a8f6fb32d705fa7aa922a3857385f78ec32034b2a4acc04cc4f3fb5d` | 2026-11-11 |
| `<BASE>/FULL REPORT/RAUB/01. AUGUST/04-08-2026/` | `005. TALAPIA (IR+VI).docx` | 41260522 | `eca3aa5c26db1ca5ef1bacb87baa22b10475ed2aff13ca7551010231a4e7523f` | 2026-11-11 |

`<BASE>` is the `PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD` project folder. The other eight inputs are repo templates under `templates/FULL REPORT/NORMAL IR US TEV/` and `templates/QUICK REPORT/DEFECT IR/`. Both hashes are the ones in `evidence/static-cfb/flir-activex-xml-join.inventory.json`. The Full Report size was measured on the copy the rekey-join Path read, which has the same hash.

## Change log

- 2026-11-11: added three files from Codex's scratch folder: the image drawn from the stored plane, the decoder output for the template and one inflated field archive. The command that drew the image was not kept. Its value range fits the plane in the `swg-panel.docx` binary (Claude Code).
- 2026-11-11: converted from the three Codex write-ups, kept unchanged in `evidence/static-cfb/original/`. The first write-up's verdict was "can't tell without a prototype", and the second revised it to "a binary-aware isolation experiment has concrete targets". C12 replaces the first write-up's statement that six viewers lack field records (Claude Code).
