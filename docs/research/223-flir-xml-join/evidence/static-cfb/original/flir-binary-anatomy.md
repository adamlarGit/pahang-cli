# FLIR binary anatomy: continuation of #223

Date: 2026-11-11. Investigator: **Codex — Static/CFB investigation**, branch `research/flir-activex-xml-join`. This continues [the first report](flir-activex-xml-join.md), following the owner's request to explore the payload further. It is distinct from the parallel agent's investigation. No Word, Office COM, registered native FLIR object or application workflow was started.

Follow-up: [using the installed FLIR tools](flir-installed-tools-options.md) assesses native SDK persistence, public viewer/field interfaces, the Word-dependent wizard and the newer Atlas/DocXEngine alternative.

## What changed in the findings

The binary is substantially more accessible than the first report established. Static decoding now accounts for the R8 wrappers, field objects, compressed control metadata and compressed SDK state in **38 binaries from ten DOCX files**, validating **187 zlib blocks** and linking **111 field records** to measurement labels and numeric bookmarks. Installed native code identifies the two UUIDs and provides a concrete mechanism by which cloned SDK identities can share image state. The [machine-readable inventory](flir-binary-anatomy.inventory.json) and [decoder](../../scripts/research/decode_flir_contents.py) record the observations.

**Revised assessment:** a binary-aware isolation experiment has concrete targets and looks worth pursuing. The remaining limit is not simply “the format is proprietary.” A general safe join still needs the later Word/FLIR behavior proof; this research does not certify one or close #223. An XML-only join retaining duplicate private SDK identities has a specific unresolved coupling mechanism.

The strongest implementation evidence is [the native-code inspection note](flir-binary-implementation-notes.md), which records DLL hashes, static instruction addresses and first-party manual references. The implementation was inspected as bytes and disassembly; it was not executed.

## R8 envelope and object identities

The observed string format is a little-endian `uint32` byte count followed by that many ASCII bytes, including a terminating NUL. Each viewer and nested field starts:

```text
length-prefixed "R8:0.1"
length-prefixed object UUID
length-prefixed IRSDK UUID
one-byte flag
```

The UUID order is confirmed by native `IFDUtil::writeR8Tags` data flow and its string writer, rather than guessed from repetition. The first UUID identifies the serialized object; the second identifies its SDK. Both are distinct from the FLIR class CLSID. [Native implementation note, “Confirmed serialized GUID order”](flir-binary-implementation-notes.md#confirmed-serialized-guid-order)

In these samples, all 38 viewer wrappers have flag 1, followed by a list of windowless field objects. Their 111 nested field wrappers have flag 0. Each child has its own object UUID, but **111/111 child SDK UUIDs equal their parent viewer's SDK UUID**. This establishes an explicit relationship between viewer state and its field objects.

For the normal Full Report switchgear panel, the outer object UUID is `f0ff1a2f-6150-4fa9-ae4c-a199a4ec68ec`; its SDK UUID is `65f355f7-d614-4afe-85c8-dff34b8c47c7`. That same SDK UUID appears in all four nested fields.

The optional metadata sequence observed here is:

```text
length-prefixed "TAG_R8_FLD"
length-prefixed "_Fd<decimal bookmark>"
uint32 nested-object byte length
nested R8 field object, exactly that length
... further field records ...
length-prefixed "TAG_R8_END"
```

The DLL also implements table and summary-table tags (`TAG_R8_TBL`, `TAG_R8_STB`). Those were not present in this specimen set; the research parser deliberately rejects them rather than pretending to support their layouts.

**Correction to the earlier marker concern:** the six Talapia Full Report viewers without `TAG_R8_FLD` have a well-bounded **empty field list terminated by `TAG_R8_END`**, followed by decodable control and SDK state. Their entire R8 wrapper is not absent. This explains the structural absence of field tags; it does not determine why the list is empty or whether the body fields associated with those pages update correctly. Marker absence alone does not establish a stripped header or a corrupted viewer.

## KENT records and compression

After the wrappers, the data uses a ten-byte framing header:

| Byte offset | Type | Observed meaning |
| --- | --- | --- |
| 0 | `uint16` little-endian | Record code |
| 2 | `uint32` little-endian | `0x4B454E54`, bytes `54 4E 45 4B` (`TNEK`) |
| 6 | `uint32` little-endian | Payload byte length |

Native reader and writer instructions confirm codes 100/101 as group begin/end and 102 as a length-bounded data record. Data records in these samples begin with a repeated length and a record identifier, followed by type-specific data. [Native implementation note, “KENT framing”](flir-binary-implementation-notes.md#confirmed-kent-framing-has-typed-length-bounded-records)

Code 107 has a 32-byte metadata payload. In every decoded block, its final two uint32 values give the compressed and inflated sizes. A zlib stream follows that metadata and ends exactly at the declared compressed size; code 109 with zero payload follows it. All **187** compressed blocks passed zlib's checksum validation and matched their declared output sizes. The wrapper's own payload length does not include the compressed byte sequence after its metadata, which matters for any writer.

Every observed viewer has two such compressed blocks: small control metadata, then the large SDK archive. A bare, self-sized 20-byte record with identifier 1002 separates them. Each nested field has one compressed archive. The parser accounts for these boundaries and every stream byte; it does not claim to understand every SDK record's semantics or validate a complete native object graph. In particular, it inventories group frames without requiring each extracted compression chunk to be a balanced standalone group tree.

For the switchgear panel:

| Component | Start in logical `Contents` | Compressed bytes | Inflated bytes |
| --- | ---: | ---: | ---: |
| First field archive | 267 | 284 | 689 |
| Second field archive | 734 | 276 | 679 |
| Third field archive | 1,191 | 275 | 679 |
| Fourth field archive | 1,647 | 253 | 655 |
| Viewer control metadata | 1,967 | 58 | 112 |
| Viewer SDK state | 2,097 | 298,075 | 625,696 |

These offsets locate zlib data, not the enclosing KENT header. These layouts show that `TAG_R8_FLD` is a per-field serialization tag, rather than one universal 4 KB proprietary header. The historical size delta still needs a before/after logical-stream comparison.

## Word fields have a second, compressed identity representation

In every one of the 111 nested fields, the decimal suffix of `_Fd…` also occurs as a little-endian uint32 inside its decompressed field archive: at byte offset 32 within the type-102 data record whose record identifier is 1000. In the four switchgear fields, that is byte offset 52 of each inflated field archive.

Record identifier 103 supplies a UTF-16 label. The template mapping is:

| Word variable | Decompressed label | Serialized bookmark uint32 |
| --- | --- | ---: |
| `_Fd1922861825` | `Sp1.Max. Temperature` | 1922861825 |
| `_Fd1967887225` | `Sp1.Temperature` | 1967887225 |
| `_Fd81475520` | `Sp2.Temperature` | 81475520 |
| `_Fd97091050` | `Dt1` | 97091050 |

Other samples expose `Ar1.Max. Temperature` and `Ar1.Average Temperature`. Native code has separate object-ID, SDK-ID and Word-bookmark operations, and maps SDK IDs to windowless field objects and bookmarks. Consequently, changing only the visible `_Fd` string can leave its compressed field object with the old numeric bookmark. [Native implementation note, “Separate shared-SDK and Word-field layers”](flir-binary-implementation-notes.md#confirmed-separate-shared-sdk-and-word-field-layers)

This is another concrete consistency obligation, beyond copying field names into `settings.xml`. The association is measured across all 111 fields, rather than inferred from a few matching labels.

## The SDK archive contains image and analysis state

In all 38 SDK archives, a type-102 record with identifier 1017 has a 618,320-byte payload. It includes an original image path, camera/model metadata and palette data. In the switchgear specimen it names `FLIR0211.jpg` and `FLIR T640`; no source path is needed to perform this static decode.

The specimen's values at payload offsets 630/632 encode 640/480 as uint16s. The final **614,400 bytes**, starting at offset 3,920 within that payload, have exactly `640 × 480 × 2` bytes. Interpreting them as a 640×480 little-endian uint16 plane reconstructs a coherent thermal scene directly from `Contents`, without the external WMF preview. All 38 inspected records have the same dimensions and size relationship. This strongly identifies embedded image data; the values are **not calibrated degrees Celsius**, and no temperature conversion is claimed.

The decompressed SDK state also contains analysis text such as `abs([ana.Sp1.temp] - [ana.Sp2.temp])` and palette names. It is more than a filename or saved flat preview. The record's image plane and additional SDK analysis state must be preserved during an identity-only experiment.

There is a useful existing comparison: Talapia Quick Report viewers 1/2/3 have byte-identical image record 1017 payloads to Full Report viewers 25/26/27, respectively, while the object UUIDs, SDK UUIDs and field bookmark names differ. For example, Quick viewer 1 uses `_Fd2060461679`; Full viewer 25 uses `_Fd703628520`, with an identical image-record SHA-256. The **whole SDK archives are not byte-identical**; this is evidence that image data can survive independent identity assignments, not a complete native-copy algorithm.

## A concrete candidate for crosstalk

The native viewer's `checkIRSDK` path looks up the SDK GUID. If an SDK object is already registered under that ID, it attaches that object to the viewer; otherwise it instantiates one and stores it under the ID. The connection and field-keeper implementations contain singleton class-factory types and SDK-ID registries. [Native implementation note, “A viewer can reconnect to an existing SDK”](flir-binary-implementation-notes.md#confirmed-control-flow-a-viewer-can-reconnect-to-an-existing-sdk)

**Inference:** cloning two binaries while preserving their SDK GUID can make both viewers reconnect to one live SDK, even when their `.bin` filenames, relationship IDs, shapes and control names differ. That directly explains how image state could be shared, independently of whether two DOCVARIABLE references happen to name the same variable. This specific joined-document behavior has not been executed or proven here.

The registry's full lifecycle and document scoping remain to be established. A later proof should include fresh Word processes as well as opening source and joined documents together; isolated source packages need not imply isolated runtime registries.

The [parallel agent's comment](https://github.com/adamlarGit/pahang-cli/issues/223#issuecomment-6782378932) states that separate `.bin` parts make image data “100% isolated.” Its stored-payload observation does not establish that runtime guarantee: the GUID-based reconnection path can attach an already registered SDK. Its suggestion to patch only the outer field-name tokens also needs to account for the compressed numeric bookmarks measured here. Likewise, the slice proof's behavioral and export pass conditions remain to be exercised before declaring it fully proven. These are qualifications to compare with that investigation, rather than changes to its findings on its author's behalf.

## What a future rewrite experiment can now target

There are three identity layers to treat separately:

1. **SDK UUID:** allocate a new SDK identity for an imported independent viewer group, and keep that group's viewer and field references consistent. Preserve intentional sharing inside a logical group. Namespace by import occurrence so two copies of one source can become independent.
2. **Object UUID:** allocate independent viewer and windowless-object identities wherever a distinct object is intended. Do not change the class CLSID.
3. **Word bookmark/variable identity:** reconcile the outer `_Fd` string, inner compressed numeric bookmark, all body field instructions and settings bindings, and any additional native bookmark references found by further inspection. Do not split deliberate multiple references to one binding into separate measurements.

The visible UUID strings have fixed serialized width, but that alone does not make a full rewrite length-neutral. Decimal field names may change length, and recompression can change byte counts. A writer must update R8 nested-object lengths, KENT compressed/inflated lengths and zlib checksums, and use correct CFB allocation if a logical stream changes size. Arbitrary string replacement in raw CFB sectors is still unjustified.

Unknowns include unobserved table/summary-table payloads, additional ID copies in other versions or object types, complete SDK-record semantics, registry lifetime and actual load/edit/save behavior. No binary writer, XML join, native object execution or behavior prototype was built in this continuation. The next experiment is substantially better specified, but success must still be measured through independent image edits, field updates and save/reopen checks.

## Validation boundary

The decoder rejects unsupported tags, impossible string/object lengths, invalid CFB reads, malformed framing and failed zlib size/checksum checks. Ten source hashes remain unchanged. Its successful inventory covers this 38-binary specimen set; it is not a general FLIR format compatibility promise. The original ADR and production compiler are unchanged.
