"""XML-level join engine for Word documents containing FLIR ActiveX controls.

Executes 100% in pure Python without Microsoft Word COM.
Implements in-place fixed-length rekeying of Measurement GUIDs, Instance GUIDs,
and _Fd variables to eliminate both Image Crosstalk and Measurement Crosstalk.
"""

from io import BytesIO
from pathlib import Path
import re
import struct
import uuid
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree
import olefile

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "o": "urn:schemas-microsoft-com:office:office",
    "ax": "http://schemas.microsoft.com/office/2006/activeX",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

def rekey_activex_bin(bin_bytes):
    """Perform fixed-length binary rekeying of instance GUID, measurement GUIDs, and _Fd names."""
    if not olefile.isOleFile(BytesIO(bin_bytes)):
        return bin_bytes, {}
    
    with olefile.OleFileIO(BytesIO(bin_bytes)) as ole:
        stream = ole.openstream('Contents').read()

    guid_regex = re.compile(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
    top_guids = [m.group() for m in guid_regex.finditer(stream[:100])]
    instance_guid = top_guids[1] if len(top_guids) > 1 else None

    # Find measurement GUIDs and _Fd fields in TAG_R8_FLD
    tag_matches = list(re.finditer(rb"TAG_R8_FLD\x00", stream))
    replacements = {}
    var_map = {} # old_str -> new_str

    if instance_guid:
        replacements[instance_guid] = str(uuid.uuid4()).encode('ascii')

    for idx, m in enumerate(tag_matches):
        pos = m.end()
        flen = struct.unpack("<I", stream[pos:pos+4])[0]
        fname = stream[pos+4:pos+4+flen].rstrip(b"\x00")
        pos += 4 + flen
        plen = struct.unpack("<I", stream[pos:pos+4])[0]
        pdata = stream[pos+4:pos+4+plen]
        
        pguids = [g.group() for g in guid_regex.finditer(pdata)]
        if pguids:
            meas_guid = pguids[0]
            replacements[meas_guid] = str(uuid.uuid4()).encode('ascii')
            
        # Generate new _Fd name of exact same length
        old_f_str = fname.decode('latin1')
        num_digits = len(old_f_str) - 3
        # Use pseudo-random unique number
        random_part = str(uuid.uuid4().int)[:num_digits]
        new_f_str = f"_Fd{random_part}"
        new_f_bytes = new_f_str.encode('ascii')
        assert len(new_f_bytes) == len(fname), f"Length mismatch: {new_f_bytes} vs {fname}"
        replacements[fname] = new_f_bytes
        var_map[old_f_str] = new_f_str

    patched_bin = bin_bytes
    for old_val, new_val in replacements.items():
        assert len(old_val) == len(new_val)
        patched_bin = patched_bin.replace(old_val, new_val)
        
    return patched_bin, var_map

def join_documents_in_xml(doc1_bytes, doc2_bytes):
    """Join doc2 into doc1 entirely in memory using pure XML manipulation."""
    pkg1 = {}
    pkg2 = {}
    
    with ZipFile(BytesIO(doc1_bytes)) as z:
        for name in z.namelist():
            pkg1[name] = z.read(name)
            
    with ZipFile(BytesIO(doc2_bytes)) as z:
        for name in z.namelist():
            pkg2[name] = z.read(name)
            
    doc1_xml = etree.fromstring(pkg1["word/document.xml"])
    doc1_rels = etree.fromstring(pkg1["word/_rels/document.xml.rels"])
    doc2_xml = etree.fromstring(pkg2["word/document.xml"])
    doc2_rels = etree.fromstring(pkg2["word/_rels/document.xml.rels"])
    content_types = etree.fromstring(pkg1["[Content_Types].xml"])
    
    # 1. Existing IDs in Document 1
    existing_rids = [r.get("Id") for r in doc1_rels]
    rid_nums = [int(m.group(0)) for r in existing_rids if (m := re.search(r"\d+", r))]
    max_rid = max(rid_nums) if rid_nums else 100
    
    existing_shapes = doc1_xml.xpath("//v:shape/@id", namespaces=NS)
    shape_nums = [int(m.group(0)) for s in existing_shapes if (m := re.search(r"\d+", s))]
    max_shape_id = max(shape_nums) if shape_nums else 2000
    
    existing_ctrl_names = set(doc1_xml.xpath("//w:control/@w:name", namespaces=NS))
    
    # Find existing activeX and media part numbers
    ax_nums = [int(m.group(1)) for name in pkg1 if (m := re.match(r"word/activeX/activeX(\d+)\.(xml|bin)", name))]
    next_ax_num = max(ax_nums) + 1 if ax_nums else 1
    
    img_nums = [int(m.group(1)) for name in pkg1 if (m := re.match(r"word/media/image(\d+)\.", name))]
    next_img_num = max(img_nums) + 1 if img_nums else 1
    
    # Map for Document 2 relationship IDs: old_rId -> new_rId
    rel_id_map = {}
    
    # 2. Process Document 2 relationships and parts
    for rel in doc2_rels:
        old_rid = rel.get("Id")
        rel_type = rel.get("Type")
        target = rel.get("Target")
        
        max_rid += 1
        new_rid = f"rId{max_rid}"
        rel_id_map[old_rid] = new_rid
        
        if "activeX" in target and target.endswith(".xml"):
            # It's an ActiveX descriptor!
            old_xml_name = f"word/{target}" if not target.startswith("/") else target[1:]
            new_target_xml = f"activeX/activeX{next_ax_num}.xml"
            new_xml_name = f"word/{new_target_xml}"
            
            # Read old activeX xml and rels
            old_ax_xml = etree.fromstring(pkg2[old_xml_name])
            old_ax_rels_name = f"word/activeX/_rels/{target.split('/')[-1]}.rels"
            old_ax_rels = etree.fromstring(pkg2[old_ax_rels_name])
            
            # Find binary target
            bin_rel = old_ax_rels[0]
            old_bin_target = bin_rel.get("Target")
            old_bin_name = f"word/activeX/{old_bin_target}"
            old_bin_bytes = pkg2[old_bin_name]
            
            # Rekey the binary!
            new_bin_bytes, var_map = rekey_activex_bin(old_bin_bytes)
            new_bin_target = f"activeX{next_ax_num}.bin"
            new_bin_name = f"word/activeX/{new_bin_target}"
            
            # Save new binary
            pkg1[new_bin_name] = new_bin_bytes
            
            # Update and save activeX rels
            bin_rel.set("Target", new_bin_target)
            new_ax_rels_name = f"word/activeX/_rels/activeX{next_ax_num}.xml.rels"
            pkg1[new_ax_rels_name] = etree.tostring(old_ax_rels)
            
            # Save new activeX XML
            pkg1[new_xml_name] = etree.tostring(old_ax_xml)
            
            # Add to Content_Types
            etree.SubElement(content_types, f"{{{NS['ct']}}}Override", {
                "PartName": f"/{new_xml_name}",
                "ContentType": "application/vnd.ms-office.activeX+xml"
            })
            
            # Add to Document 1 rels
            etree.SubElement(doc1_rels, f"{{{NS['rel']}}}Relationship", {
                "Id": new_rid,
                "Type": rel_type,
                "Target": new_target_xml
            })
            
            # Remap DOCVARIABLE in Document 2 body
            doc2_xml_str = etree.tostring(doc2_xml, encoding="unicode")
            for old_var, new_var in var_map.items():
                doc2_xml_str = doc2_xml_str.replace(old_var, new_var)
                # Also add new docVar in settings.xml
                if "word/settings.xml" in pkg1:
                    settings_xml = etree.fromstring(pkg1["word/settings.xml"])
                    docvars = settings_xml.xpath(f"//w:docVar[@w:name='{old_var}']", namespaces=NS)
                    old_val = docvars[0].get(f"{{{NS['w']}}}val") if docvars else "0.0 °C"
                    etree.SubElement(settings_xml, f"{{{NS['w']}}}docVar", {
                        f"{{{NS['w']}}}name": new_var,
                        f"{{{NS['w']}}}val": old_val
                    })
                    pkg1["word/settings.xml"] = etree.tostring(settings_xml)
                    
            doc2_xml = etree.fromstring(doc2_xml_str.encode('utf-8'))
            next_ax_num += 1
            
        elif "media" in target:
            # An image part (e.g. preview)
            ext = target.split(".")[-1]
            old_media_name = f"word/{target}" if not target.startswith("/") else target[1:]
            new_target_img = f"media/image{next_img_num}.{ext}"
            new_media_name = f"word/{new_target_img}"
            
            pkg1[new_media_name] = pkg2[old_media_name]
            
            # Add relationship in Document 1
            etree.SubElement(doc1_rels, f"{{{NS['rel']}}}Relationship", {
                "Id": new_rid,
                "Type": rel_type,
                "Target": new_target_img
            })
            next_img_num += 1
        else:
            # Other relationships (hyperlinks, styles, etc.)
            etree.SubElement(doc1_rels, f"{{{NS['rel']}}}Relationship", {
                "Id": new_rid,
                "Type": rel_type,
                "Target": target
            })

    # 3. Update Document 2 elements (controls, shapes, rIds)
    for c in doc2_xml.xpath("//w:control", namespaces=NS):
        # Update r:id
        old_c_rid = c.get(f"{{{NS['r']}}}id")
        if old_c_rid in rel_id_map:
            c.set(f"{{{NS['r']}}}id", rel_id_map[old_c_rid])
            
        # Update w:name to ensure document-wide uniqueness
        old_name = c.get(f"{{{NS['w']}}}name")
        new_name = old_name
        counter = 1
        while new_name in existing_ctrl_names:
            new_name = f"{old_name}{counter}"
            counter += 1
        c.set(f"{{{NS['w']}}}name", new_name)
        existing_ctrl_names.add(new_name)
        
        # Update shapeid
        max_shape_id += 1
        new_shape_id = f"_x0000_i{max_shape_id}"
        old_shape_id = c.get(f"{{{NS['w']}}}shapeid")
        c.set(f"{{{NS['w']}}}shapeid", new_shape_id)
        
        # Update companion v:shape if present
        v_shapes = doc2_xml.xpath(f"//v:shape[@id='{old_shape_id}']", namespaces=NS)
        for vs in v_shapes:
            vs.set("id", new_shape_id)
            if "{urn:schemas-microsoft-com:office:office}spid" in vs.attrib:
                vs.set("{urn:schemas-microsoft-com:office:office}spid", f"_x0000_s{max_shape_id}")
                
    # Update other relationship references in Document 2 (e.g. images)
    for img in doc2_xml.xpath("//v:imagedata", namespaces=NS):
        old_img_rid = img.get(f"{{{NS['r']}}}id")
        if old_img_rid in rel_id_map:
            img.set(f"{{{NS['r']}}}id", rel_id_map[old_img_rid])
            
    for blip in doc2_xml.xpath("//a:blip", namespaces=NS):
        old_blip_rid = blip.get(f"{{{NS['r']}}}embed")
        if old_blip_rid in rel_id_map:
            blip.set(f"{{{NS['r']}}}embed", rel_id_map[old_blip_rid])

    # 4. Append Document 2 body to Document 1
    doc1_body = doc1_xml.xpath("//w:body", namespaces=NS)[0]
    doc2_body = doc2_xml.xpath("//w:body", namespaces=NS)[0]
    
    # Save Document 1's trailing sectPr
    doc1_sectPr = doc1_body.xpath("./w:sectPr", namespaces=NS)
    trailing_sectPr = doc1_sectPr[0] if doc1_sectPr else None
    if trailing_sectPr is not None:
        doc1_body.remove(trailing_sectPr)
        
    # Insert a page break paragraph
    pb_p = etree.Element(f"{{{NS['w']}}}p")
    pb_r = etree.SubElement(pb_p, f"{{{NS['w']}}}r")
    etree.SubElement(pb_r, f"{{{NS['w']}}}br", {f"{{{NS['w']}}}type": "page"})
    doc1_body.append(pb_p)
    
    # Append all children of doc2_body except trailing sectPr
    doc2_children = list(doc2_body)
    for child in doc2_children:
        if child.tag == f"{{{NS['w']}}}sectPr":
            continue
        doc1_body.append(child)
        
    # Re-attach trailing sectPr
    if trailing_sectPr is not None:
        doc1_body.append(trailing_sectPr)
    elif doc2_body.xpath("./w:sectPr", namespaces=NS):
        doc1_body.append(doc2_body.xpath("./w:sectPr", namespaces=NS)[0])
        
    # Update modified XML files in pkg1
    pkg1["word/document.xml"] = etree.tostring(doc1_xml)
    pkg1["word/_rels/document.xml.rels"] = etree.tostring(doc1_rels)
    pkg1["[Content_Types].xml"] = etree.tostring(content_types)
    
    # Re-zip package
    out_buf = BytesIO()
    with ZipFile(out_buf, "w", ZIP_DEFLATED) as z_out:
        for fname, fcontent in pkg1.items():
            z_out.writestr(fname, fcontent)
            
    return out_buf.getvalue()

if __name__ == "__main__":
    template_path = Path("templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx")
    doc_bytes = template_path.read_bytes()
    print("Testing XML Join of two swg-panel pages...")
    joined_bytes = join_documents_in_xml(doc_bytes, doc_bytes)
    out_path = Path(".scratch/joined_swg_panels_proof.docx")
    out_path.write_bytes(joined_bytes)
    print(f"Joined document successfully written to {out_path} ({len(joined_bytes)} bytes)!")
