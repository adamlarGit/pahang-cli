"""Pure-XML Join Engine Prototype for Word documents with FLIR ActiveX controls.

Ticket #225 Spike Prototype: joins real compile inputs (Part 03 and Part 32)
without Microsoft Word COM.
"""

import hashlib
from io import BytesIO
from pathlib import Path
import re
import secrets
import struct
import time
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

SINGLETON_TARGETS = {
    "styles.xml",
    "settings.xml",
    "webSettings.xml",
    "fontTable.xml",
    "theme/theme1.xml",
    "numbering.xml",
}

DEFAULT_CONTENT_TYPES = {
    "bin": "application/vnd.ms-office.activeX",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "rels": "application/vnd.openxmlformats-package.relationships+xml",
    "wmf": "image/x-wmf",
    "xml": "application/xml",
}

def rekey_activex_bin(bin_bytes: bytes, used_fd_names: set[str]) -> tuple[bytes, dict[str, str]]:
    """Perform fixed-length in-place binary rekeying of instance GUID, measurement GUIDs, and _Fd variables."""
    if not olefile.isOleFile(BytesIO(bin_bytes)):
        return bin_bytes, {}

    with olefile.OleFileIO(BytesIO(bin_bytes)) as ole:
        stream = ole.openstream("Contents").read()

    guid_regex = re.compile(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
    top_guids = [m.group() for m in guid_regex.finditer(stream[:100])]
    session_guid = top_guids[0] if len(top_guids) > 0 else None
    instance_guid = top_guids[1] if len(top_guids) > 1 else None

    tag_matches = list(re.finditer(rb"TAG_R8_FLD\x00", stream))
    replacements: dict[bytes, bytes] = {}
    var_map: dict[str, str] = {}

    if session_guid:
        replacements[session_guid] = str(uuid.uuid4()).encode("ascii")
    if instance_guid:
        replacements[instance_guid] = str(uuid.uuid4()).encode("ascii")

    for m in tag_matches:
        pos = m.end()
        flen = struct.unpack("<I", stream[pos:pos+4])[0]
        fname = stream[pos+4:pos+4+flen].rstrip(b"\x00")
        pos += 4 + flen
        plen = struct.unpack("<I", stream[pos:pos+4])[0]
        pdata = stream[pos+4:pos+4+plen]

        pguids = [g.group() for g in guid_regex.finditer(pdata)]
        if pguids:
            meas_guid = pguids[0]
            replacements[meas_guid] = str(uuid.uuid4()).encode("ascii")

        old_f_str = fname.decode("latin1")
        num_digits = len(old_f_str) - 3
        assert num_digits > 0, f"Invalid _Fd name: {old_f_str}"

        while True:
            first_digit = secrets.choice("123456789")
            remaining = "".join(secrets.choice("0123456789") for _ in range(num_digits - 1))
            new_f_str = f"_Fd{first_digit}{remaining}"
            if new_f_str not in used_fd_names:
                used_fd_names.add(new_f_str)
                break

        new_f_bytes = new_f_str.encode("ascii")
        assert len(new_f_bytes) == len(fname), f"Length mismatch: {new_f_bytes} vs {fname}"
        replacements[fname] = new_f_bytes
        var_map[old_f_str] = new_f_str

    patched_bin = bin_bytes
    for old_val, new_val in replacements.items():
        assert len(old_val) == len(new_val), "Rekeying must be strictly fixed-length!"
        patched_bin = patched_bin.replace(old_val, new_val)

    return patched_bin, var_map


def join_multiple_documents_in_xml(parts: list[Path]) -> bytes:
    """Join multiple Word documents entirely in memory using pure XML manipulation."""
    if not parts:
        raise ValueError("Parts list cannot be empty")

    if len(parts) == 1:
        return parts[0].read_bytes()

    # 1. Initialize base package from parts[0]
    pkg_files: dict[str, bytes] = {}
    with ZipFile(parts[0]) as z:
        for name in z.namelist():
            pkg_files[name] = z.read(name)

    base_doc_xml = etree.fromstring(pkg_files["word/document.xml"])
    base_doc_rels = etree.fromstring(pkg_files["word/_rels/document.xml.rels"])
    content_types = etree.fromstring(pkg_files["[Content_Types].xml"])

    # Ensure default content types exist
    existing_defaults = {
        d.get("Extension"): d.get("ContentType")
        for d in content_types.xpath("//ct:Default", namespaces=NS)
    }
    for ext, ctype in DEFAULT_CONTENT_TYPES.items():
        if ext not in existing_defaults:
            etree.SubElement(content_types, f"{{{NS['ct']}}}Default", {
                "Extension": ext,
                "ContentType": ctype
            })

    # Remove any specific overrides for .bin files since Default covers them
    for ovr in content_types.xpath("//ct:Override[contains(@PartName, '.bin')]", namespaces=NS):
        content_types.remove(ovr)

    # Clean up customXml if unreferenced
    doc_xml_str_initial = pkg_files["word/document.xml"].decode("utf-8")
    if "customXml" not in doc_xml_str_initial:
        for r in list(base_doc_rels):
            if "customXml" in r.get("Target", ""):
                base_doc_rels.remove(r)
        for ovr in list(content_types.xpath("//ct:Override[contains(@PartName, 'customXml')]", namespaces=NS)):
            content_types.remove(ovr)
        pkg_files = {k: v for k, v in pkg_files.items() if not k.startswith("customXml/")}

    settings_xml = None
    if "word/settings.xml" in pkg_files:
        settings_xml = etree.fromstring(pkg_files["word/settings.xml"])

    # Index existing base relationships
    singleton_rel_map: dict[str, str] = {}
    image_hash_to_rid: dict[str, str] = {}
    existing_rids: list[str] = []

    for rel in base_doc_rels:
        r_id = rel.get("Id")
        existing_rids.append(r_id)
        target = rel.get("Target")
        if target in SINGLETON_TARGETS:
            singleton_rel_map[target] = r_id
        elif "media/" in target:
            img_path = f"word/{target}" if not target.startswith("/") else target[1:]
            if img_path in pkg_files:
                h = hashlib.sha256(pkg_files[img_path]).hexdigest()
                image_hash_to_rid[h] = r_id

    rid_nums = [int(m.group(0)) for r in existing_rids if (m := re.search(r"\d+", r))]
    max_rid = max(rid_nums) if rid_nums else 100

    existing_shapes = base_doc_xml.xpath("//v:shape/@id", namespaces=NS)
    shape_nums = [int(m.group(1)) for s in existing_shapes if (m := re.search(r"_x0000_i(\d+)", s))]
    max_shape_id = max(shape_nums) if shape_nums else 1024
    if max_shape_id < 1024:
        max_shape_id = 1024

    existing_docprs = base_doc_xml.xpath("//wp:docPr/@id", namespaces=NS)
    docpr_nums = [int(m.group(0)) for d in existing_docprs if (m := re.search(r"\d+", d))]
    max_docpr_id = max(docpr_nums) if docpr_nums else 100

    existing_ctrl_names = set(base_doc_xml.xpath("//w:control/@w:name", namespaces=NS))

    used_fd_names: set[str] = set()
    used_fd_names.update(re.findall(r"_Fd\d+", etree.tostring(base_doc_xml, encoding="unicode")))
    if settings_xml is not None:
        used_fd_names.update(settings_xml.xpath("//w:docVar/@w:name", namespaces=NS))

    # Rekey base document (parts[0]) ActiveX controls to prevent cross-document collisions
    base_bin_names = [n for n in pkg_files if n.startswith("word/activeX/") and n.endswith(".bin")]
    for bname in base_bin_names:
        new_bdata, b_var_map = rekey_activex_bin(pkg_files[bname], used_fd_names)
        pkg_files[bname] = new_bdata
        if b_var_map:
            base_doc_xml_str = etree.tostring(base_doc_xml, encoding="unicode")
            for old_var, new_var in b_var_map.items():
                base_doc_xml_str = base_doc_xml_str.replace(old_var, new_var)
                if settings_xml is not None:
                    matches = settings_xml.xpath(f"//w:docVar[@w:name='{old_var}']", namespaces=NS)
                    for m in matches:
                        m.set(f"{{{NS['w']}}}name", new_var)
            base_doc_xml = etree.fromstring(base_doc_xml_str.encode("utf-8"))

    ax_nums = [int(m.group(1)) for name in pkg_files if (m := re.match(r"word/activeX/activeX(\d+)\.(xml|bin)", name))]
    next_ax_num = max(ax_nums) + 1 if ax_nums else 1

    img_nums = [int(m.group(1)) for name in pkg_files if (m := re.match(r"word/media/image(\d+)\.", name))]
    next_img_num = max(img_nums) + 1 if img_nums else 1

    base_body = base_doc_xml.xpath("//w:body", namespaces=NS)[0]
    base_sect_prs = base_body.xpath("./w:sectPr", namespaces=NS)
    trailing_sect_pr = base_sect_prs[0] if base_sect_prs else None
    if trailing_sect_pr is not None:
        base_body.remove(trailing_sect_pr)

    # 2. Append each subsequent part
    for part_idx, part_path in enumerate(parts[1:], start=2):
        part_pkg: dict[str, bytes] = {}
        with ZipFile(part_path) as pz:
            for name in pz.namelist():
                part_pkg[name] = pz.read(name)

        part_doc_xml = etree.fromstring(part_pkg["word/document.xml"])
        part_doc_rels = etree.fromstring(part_pkg["word/_rels/document.xml.rels"])
        part_settings_xml = (
            etree.fromstring(part_pkg["word/settings.xml"])
            if "word/settings.xml" in part_pkg
            else None
        )

        rel_id_map: dict[str, str] = {}
        all_var_maps: dict[str, str] = {}

        for rel in part_doc_rels:
            old_rid = rel.get("Id")
            rel_type = rel.get("Type")
            target = rel.get("Target")
            target_mode = rel.get("TargetMode")

            # Check if this is a singleton document part (styles, settings, fontTable, etc.)
            if target in SINGLETON_TARGETS:
                if target in singleton_rel_map:
                    rel_id_map[old_rid] = singleton_rel_map[target]
                    continue

            if "activeX" in target and target.endswith(".xml"):
                max_rid += 1
                new_rid = f"rId{max_rid}"
                rel_id_map[old_rid] = new_rid

                old_xml_name = f"word/{target}" if not target.startswith("/") else target[1:]
                ax_id = next_ax_num
                next_ax_num += 1

                new_target_xml = f"activeX/activeX{ax_id}.xml"
                new_xml_name = f"word/{new_target_xml}"

                old_ax_xml = etree.fromstring(part_pkg[old_xml_name])
                old_ax_rels_name = f"word/activeX/_rels/{target.split('/')[-1]}.rels"
                old_ax_rels = etree.fromstring(part_pkg[old_ax_rels_name])

                bin_rel = old_ax_rels[0]
                old_bin_target = bin_rel.get("Target")
                old_bin_name = f"word/activeX/{old_bin_target}"
                old_bin_bytes = part_pkg[old_bin_name]

                # Rekey binary
                new_bin_bytes, var_map = rekey_activex_bin(old_bin_bytes, used_fd_names)
                all_var_maps.update(var_map)

                new_bin_target = f"activeX{ax_id}.bin"
                new_bin_name = f"word/activeX/{new_bin_target}"

                pkg_files[new_bin_name] = new_bin_bytes
                bin_rel.set("Target", new_bin_target)
                pkg_files[f"word/activeX/_rels/activeX{ax_id}.xml.rels"] = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + etree.tostring(old_ax_rels)
                pkg_files[new_xml_name] = b'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + etree.tostring(old_ax_xml)

                # Content_Types override
                etree.SubElement(content_types, f"{{{NS['ct']}}}Override", {
                    "PartName": f"/{new_xml_name}",
                    "ContentType": "application/vnd.ms-office.activeX+xml"
                })

                # Base document relationship
                etree.SubElement(base_doc_rels, f"{{{NS['rel']}}}Relationship", {
                    "Id": new_rid,
                    "Type": rel_type,
                    "Target": new_target_xml
                })

            elif "media/" in target:
                ext = target.split(".")[-1]
                old_media_name = f"word/{target}" if not target.startswith("/") else target[1:]
                img_bytes = part_pkg[old_media_name]
                img_hash = hashlib.sha256(img_bytes).hexdigest()

                # Reuse existing media relationship if identical
                if img_hash in image_hash_to_rid:
                    rel_id_map[old_rid] = image_hash_to_rid[img_hash]
                    continue

                max_rid += 1
                new_rid = f"rId{max_rid}"
                rel_id_map[old_rid] = new_rid
                image_hash_to_rid[img_hash] = new_rid

                img_id = next_img_num
                next_img_num += 1

                new_target_img = f"media/image{img_id}.{ext}"
                new_media_name = f"word/{new_target_img}"

                pkg_files[new_media_name] = img_bytes

                etree.SubElement(base_doc_rels, f"{{{NS['rel']}}}Relationship", {
                    "Id": new_rid,
                    "Type": rel_type,
                    "Target": new_target_img
                })

            elif "customXml" in target:
                # Skip duplicate customXml relationships
                continue
            else:
                max_rid += 1
                new_rid = f"rId{max_rid}"
                rel_id_map[old_rid] = new_rid

                rel_attrib = {
                    "Id": new_rid,
                    "Type": rel_type,
                    "Target": target
                }
                if target_mode:
                    rel_attrib["TargetMode"] = target_mode
                etree.SubElement(base_doc_rels, f"{{{NS['rel']}}}Relationship", rel_attrib)

        # Substitute rekeyed _Fd variable names in part_doc_xml and register in settings.xml
        if all_var_maps:
            part_doc_xml_str = etree.tostring(part_doc_xml, encoding="unicode")
            for old_var, new_var in all_var_maps.items():
                part_doc_xml_str = part_doc_xml_str.replace(old_var, new_var)

                # Add to settings.xml
                if settings_xml is not None:
                    old_val = "0.0 °C"
                    if part_settings_xml is not None:
                        matches = part_settings_xml.xpath(f"//w:docVar[@w:name='{old_var}']/@w:val", namespaces=NS)
                        if matches:
                            old_val = matches[0]
                    etree.SubElement(settings_xml, f"{{{NS['w']}}}docVar", {
                        f"{{{NS['w']}}}name": new_var,
                        f"{{{NS['w']}}}val": old_val
                    })

            part_doc_xml = etree.fromstring(part_doc_xml_str.encode("utf-8"))

        # Update controls
        for c in part_doc_xml.xpath("//w:control", namespaces=NS):
            old_c_rid = c.get(f"{{{NS['r']}}}id")
            if old_c_rid in rel_id_map:
                c.set(f"{{{NS['r']}}}id", rel_id_map[old_c_rid])

            old_name = c.get(f"{{{NS['w']}}}name")
            new_name = old_name
            cnt = 1
            while new_name in existing_ctrl_names:
                new_name = f"{old_name}{cnt}"
                cnt += 1
            c.set(f"{{{NS['w']}}}name", new_name)
            existing_ctrl_names.add(new_name)

            max_shape_id += 1
            new_shape_id = f"_x0000_i{max_shape_id}"
            old_shape_id = c.get(f"{{{NS['w']}}}shapeid")
            c.set(f"{{{NS['w']}}}shapeid", new_shape_id)

            for vs in part_doc_xml.xpath(f"//v:shape[@id='{old_shape_id}']", namespaces=NS):
                vs.set("id", new_shape_id)
                if f"{{{NS['o']}}}spid" in vs.attrib:
                    vs.set(f"{{{NS['o']}}}spid", f"_x0000_s{max_shape_id}")

        # Update remaining v:shape elements
        for vs in part_doc_xml.xpath("//v:shape", namespaces=NS):
            vs_id = vs.get("id")
            if vs_id and not vs_id.startswith("_x0000_i"):
                max_shape_id += 1
                vs.set("id", f"_x0000_s{max_shape_id}")

        # Update DrawingML docPr ids
        for dp in part_doc_xml.xpath("//wp:docPr", namespaces=NS):
            max_docpr_id += 1
            dp.set("id", str(max_docpr_id))

        # Update imagedata and blip relationships
        for img in part_doc_xml.xpath("//v:imagedata", namespaces=NS):
            old_img_rid = img.get(f"{{{NS['r']}}}id")
            if old_img_rid in rel_id_map:
                img.set(f"{{{NS['r']}}}id", rel_id_map[old_img_rid])

        for blip in part_doc_xml.xpath("//a:blip", namespaces=NS):
            old_blip_rid = blip.get(f"{{{NS['r']}}}embed")
            if old_blip_rid in rel_id_map:
                blip.set(f"{{{NS['r']}}}embed", rel_id_map[old_blip_rid])
            old_link = blip.get(f"{{{NS['r']}}}link")
            if old_link in rel_id_map:
                blip.set(f"{{{NS['r']}}}link", rel_id_map[old_link])

        for hl in part_doc_xml.xpath("//w:hyperlink", namespaces=NS):
            old_hl_rid = hl.get(f"{{{NS['r']}}}id")
            if old_hl_rid in rel_id_map:
                hl.set(f"{{{NS['r']}}}id", rel_id_map[old_hl_rid])

        # Insert page break paragraph
        pb_p = etree.Element(f"{{{NS['w']}}}p")
        pb_r = etree.SubElement(pb_p, f"{{{NS['w']}}}r")
        etree.SubElement(pb_r, f"{{{NS['w']}}}br", {f"{{{NS['w']}}}type": "page"})
        base_body.append(pb_p)

        # Append body children (excluding direct trailing sectPr)
        part_body = part_doc_xml.xpath("//w:body", namespaces=NS)[0]
        for child in list(part_body):
            if child.tag == f"{{{NS['w']}}}sectPr":
                continue
            base_body.append(child)

    # 3. Finalize base package
    if trailing_sect_pr is not None:
        base_body.append(trailing_sect_pr)

    pkg_files["word/document.xml"] = etree.tostring(base_doc_xml)
    pkg_files["word/_rels/document.xml.rels"] = etree.tostring(base_doc_rels)
    pkg_files["[Content_Types].xml"] = etree.tostring(content_types)
    if settings_xml is not None:
        pkg_files["word/settings.xml"] = etree.tostring(settings_xml)

    out_buf = BytesIO()
    with ZipFile(out_buf, "w", ZIP_DEFLATED) as z_out:
        for fname, fcontent in pkg_files.items():
            z_out.writestr(fname, fcontent)

    return out_buf.getvalue()
