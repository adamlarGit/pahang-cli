"""Runner for Ticket #225 Spike Prototype: Join Real Compile Inputs in XML.

Produces Part 03 and Part 32 Word documents using pure XML join engine.
Validates structural integrity, uniqueness of FLIR identifiers, and measures wall time.
"""

from io import BytesIO
from pathlib import Path
import re
import sys
import time
from zipfile import ZipFile
from lxml import etree
import olefile

sys.path.insert(0, str(Path(__file__).parent))
from prototype_join_engine import join_multiple_documents_in_xml, NS

def validate_joined_document(doc_path: Path, expected_viewers: int):
    """Run full package and ActiveX structural validation on the output docx."""
    print(f"\n=======================================================")
    print(f"VALIDATING: {doc_path.name}")
    print(f"File Size: {doc_path.stat().st_size:,} bytes")
    print(f"=======================================================")

    with ZipFile(doc_path) as z:
        doc_xml = etree.fromstring(z.read("word/document.xml"))
        doc_rels = etree.fromstring(z.read("word/_rels/document.xml.rels"))
        settings_xml = etree.fromstring(z.read("word/settings.xml")) if "word/settings.xml" in z.namelist() else None

        # 1. Check controls
        controls = doc_xml.xpath("//w:control", namespaces=NS)
        ctrl_names = [c.get(f"{{{NS['w']}}}name") for c in controls]
        shape_ids = [c.get(f"{{{NS['w']}}}shapeid") for c in controls]
        r_ids = [c.get(f"{{{NS['r']}}}id") for c in controls]

        print(f"1. Controls count: {len(controls)} (expected: {expected_viewers})")
        assert len(controls) == expected_viewers, f"Control count {len(controls)} != {expected_viewers}"
        print(f"   Unique control names: {len(set(ctrl_names))}/{len(ctrl_names)}")
        assert len(ctrl_names) == len(set(ctrl_names)), "Duplicate control names found!"
        print(f"   Unique shapeids: {len(set(shape_ids))}/{len(shape_ids)}")
        assert len(shape_ids) == len(set(shape_ids)), "Duplicate shapeids found!"
        print(f"   Unique relationship IDs: {len(set(r_ids))}/{len(r_ids)}")
        assert len(r_ids) == len(set(r_ids)), "Duplicate control r:ids found!"

        # 2. Check ActiveX binaries
        bins = [n for n in z.namelist() if n.startswith("word/activeX/") and n.endswith(".bin")]
        print(f"\n2. ActiveX Binaries in package: {len(bins)} parts")
        assert len(bins) == expected_viewers, f"ActiveX binary count {len(bins)} != {expected_viewers}"

        all_instance_guids = []
        all_meas_guids = []
        all_bin_fds = []

        guid_regex = re.compile(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")

        for b in sorted(bins):
            bdata = z.read(b)
            assert olefile.isOleFile(BytesIO(bdata)), f"{b} is not valid OLE!"
            with olefile.OleFileIO(BytesIO(bdata)) as ole:
                stream = ole.openstream("Contents").read()
                guids = [g.decode("ascii") for g in guid_regex.findall(stream[:100])]
                if len(guids) > 1:
                    all_instance_guids.append(guids[1])
                
                # Check TAG_R8_FLD records
                tag_matches = list(re.finditer(rb"TAG_R8_FLD\x00", stream))
                for m in tag_matches:
                    pos = m.end()
                    flen = int.from_bytes(stream[pos:pos+4], "little")
                    fname = stream[pos+4:pos+4+flen].rstrip(b"\x00").decode("latin1")
                    all_bin_fds.append(fname)
                    pos += 4 + flen
                    plen = int.from_bytes(stream[pos:pos+4], "little")
                    pdata = stream[pos+4:pos+4+plen]
                    pguids = [g.decode("ascii") for g in guid_regex.findall(pdata)]
                    if pguids:
                        all_meas_guids.append(pguids[0])
                    if len(pguids) > 1 and len(guids) > 1:
                        # Verify payload instance GUID matches top instance GUID
                        assert pguids[1] == guids[1], f"Payload instance GUID {pguids[1]} != top {guids[1]}"

        print(f"   Instance GUIDs: {len(all_instance_guids)} (unique: {len(set(all_instance_guids))})")
        assert len(all_instance_guids) == len(set(all_instance_guids)), "Duplicate Instance GUIDs in binaries!"
        print(f"   Measurement GUIDs: {len(all_meas_guids)} (unique: {len(set(all_meas_guids))})")
        assert len(all_meas_guids) == len(set(all_meas_guids)), "Duplicate Measurement GUIDs in binaries!"
        print(f"   Binary _Fd fields: {len(all_bin_fds)} (unique: {len(set(all_bin_fds))})")
        assert len(all_bin_fds) == len(set(all_bin_fds)), "Duplicate _Fd field names in binaries!"

        # 3. Check document.xml DOCVARIABLE fields
        instrs = doc_xml.xpath("//w:instrText/text()", namespaces=NS)
        fd_fields = [m for i in instrs for m in re.findall(r"_Fd\d+", i)]
        print(f"\n3. Body DOCVARIABLE fields: {len(fd_fields)} (unique: {len(set(fd_fields))})")
        assert len(fd_fields) == len(set(fd_fields)), "Duplicate _Fd fields in document.xml!"
        assert set(fd_fields).issubset(set(all_bin_fds)), "Mismatch between binary _Fd and document.xml _Fd!"
        print("   -> All document.xml fields are accounted for in binary TAG_R8_FLD headers!")

        # 4. Check settings.xml docVars
        if settings_xml is not None:
            docvars = set(settings_xml.xpath("//w:docVar/@w:name", namespaces=NS))
            print(f"\n4. Settings.xml docVar count: {len(docvars)}")
            for f in fd_fields:
                assert f in docvars, f"Field {f} missing from settings.xml!"
            print(f"   -> All {len(fd_fields)} _Fd variables declared in settings.xml!")

        # 5. Check DrawingML docPr uniqueness
        docprs = [d.get("id") for d in doc_xml.xpath("//wp:docPr", namespaces=NS)]
        print(f"\n5. DrawingML docPr IDs: {len(docprs)} (unique: {len(set(docprs))})")
        assert len(docprs) == len(set(docprs)), "Duplicate docPr IDs found!"

        # 6. Page breaks and sectPr
        brs = doc_xml.xpath("//w:br[@w:type='page']", namespaces=NS)
        sects = doc_xml.xpath("//w:sectPr", namespaces=NS)
        print(f"\n6. Page structure: {len(brs)} page breaks, {len(sects)} sectPr")

    print(f"\n>>> RESULT: ALL STRUCTURAL INTEGRITY & CROSSTALK CHECKS PASSED! <<<")


def main():
    rendered_dir = Path(r"C:\Users\ADAM\AppData\Local\Temp\r232\project\.temp\full_report\001_PPU APMM 3311kV_07-10-2026\rendered")
    sources_p3_dir = Path(r"C:\Users\ADAM\Desktop\pahang-cli-33kv\scratch\prototype-flir-xml-join-225\worktree\scratch\sources_part03")
    out_dir = Path(r"C:\Users\ADAM\Desktop\pahang-cli-33kv\scratch\prototype-flir-xml-join-225\worktree\scratch\output")
    out_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------
    # 1. Part 03 Spike
    # -------------------------------------------------------------
    print("\n" + "#" * 60)
    print("PROTOTYPE SPIKE 1: PPU APMM Part 03 (7 source documents)")
    print("#" * 60)

    p3_sources = (
        sorted(sources_p3_dir.glob("01[5-9]_*.docx")) +
        sorted(sources_p3_dir.glob("02[0-1]_*.docx"))
    )
    print(f"Found {len(p3_sources)} source documents for Part 03:")
    for s in p3_sources:
        print(f"  - {s.name}")

    t0 = time.perf_counter()
    p3_bytes = join_multiple_documents_in_xml(p3_sources)
    p3_xml_time = time.perf_counter() - t0

    p3_out = out_dir / "01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE) [XML-JOINED].docx"
    p3_out.write_bytes(p3_bytes)

    print(f"\nPart 03 XML Join completed in: {p3_xml_time:.4f} seconds!")
    print(f"Word COM compile time (baseline #232): 46.5180 seconds")
    print(f"Speedup: {46.5180 / p3_xml_time:.1f}x faster!")

    validate_joined_document(p3_out, expected_viewers=7)

    # -------------------------------------------------------------
    # 2. Part 32 Spike
    # -------------------------------------------------------------
    print("\n" + "#" * 60)
    print("PROTOTYPE SPIKE 2: PPU APMM Part 32 (28 source documents, 26 viewers)")
    print("#" * 60)

    p32_sources = []
    for i in range(201, 229):
        matches = list(rendered_dir.glob(f"{i:03d}_*.docx"))
        assert len(matches) == 1, f"Expected 1 match for {i:03d}, found {matches}"
        p32_sources.append(matches[0])

    print(f"Found {len(p32_sources)} source documents for Part 32:")
    for s in p32_sources:
        print(f"  - {s.name}")

    t0 = time.perf_counter()
    p32_bytes = join_multiple_documents_in_xml(p32_sources)
    p32_xml_time = time.perf_counter() - t0

    p32_out = out_dir / "01. PPU APMM 3311kV - Part 32 - TX and Condition [XML-JOINED].docx"
    p32_out.write_bytes(p32_bytes)

    print(f"\nPart 32 XML Join completed in: {p32_xml_time:.4f} seconds!")
    print(f"Word COM compile time (baseline #232): 173.5910 seconds")
    print(f"Speedup: {173.5910 / p32_xml_time:.1f}x faster!")

    validate_joined_document(p32_out, expected_viewers=26)

    # -------------------------------------------------------------
    # Summary Table
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PROTOTYPE SUMMARY RESULTS (TICKET #225)")
    print("=" * 60)
    print(f"Part 03 (7 sources, 7 FLIR viewers):")
    print(f"  - XML Join Time:   {p3_xml_time:.4f} s")
    print(f"  - COM Compile:     46.5180 s")
    print(f"  - Output Size:     {len(p3_bytes):,} bytes")
    print(f"  - Output File:     {p3_out}")
    print()
    print(f"Part 32 (28 sources, 26 FLIR viewers):")
    print(f"  - XML Join Time:   {p32_xml_time:.4f} s")
    print(f"  - COM Compile:     173.5910 s")
    print(f"  - Output Size:     {len(p32_bytes):,} bytes")
    print(f"  - Output File:     {p32_out}")
    print("=" * 60)

if __name__ == "__main__":
    main()
