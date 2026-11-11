"""Read-only ZIP/XML/CFB inventory for FLIR join research (#223).

Run with a Python environment containing olefile. No application modules,
Office automation, or document writers are imported. JSON goes to stdout.
"""

from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import posixpath
import re
import sys
from zipfile import ZipFile

from lxml import etree
import olefile


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "o": "urn:schemas-microsoft-com:office:office",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}
FD = re.compile(rb"_Fd\d+")
GUID = re.compile(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def duplicates(values):
    return {key: count for key, count in Counter(values).items() if count > 1}


def attrs(node):
    return {etree.QName(k).localname: v for k, v in node.attrib.items()}


def inspect(path):
    source = path.read_bytes()
    result = {"path": str(path), "sha256": sha256(source).hexdigest()}
    with ZipFile(BytesIO(source)) as package:
        names = package.namelist()
        xml = {
            name: etree.fromstring(package.read(name))
            for name in names
            if name.endswith((".xml", ".rels"))
        }
        document = xml["word/document.xml"]
        controls = document.xpath("//w:control", namespaces=NS)
        result["controls"] = [attrs(n) for n in controls]
        result["duplicate_control_names"] = duplicates(n.get("{%s}name" % NS["w"]) for n in controls)
        result["ole_objects"] = [attrs(n) for n in document.xpath("//o:OLEObject", namespaces=NS)]
        result["objects"] = [etree.tostring(n, encoding="unicode") for n in document.xpath("//w:object", namespaces=NS)]
        shape_nodes = document.xpath("//v:shape", namespaces=NS)
        result["duplicate_shape_ids"] = duplicates(n.get("id") for n in shape_nodes)
        result["fallback_shapes"] = [attrs(n) for n in document.xpath("//mc:Fallback//v:shape", namespaces=NS)]
        result["docpr_ids"] = document.xpath("//wp:docPr/@id", namespaces=NS)
        result["duplicate_docpr_ids"] = duplicates(result["docpr_ids"])
        instructions = "".join(document.xpath("//w:instrText/text()", namespaces=NS))
        instructions += " ".join(document.xpath("//w:fldSimple/@w:instr", namespaces=NS))
        fields = re.findall(r'\bDOCVARIABLE\s+(?:"([^"]+)"|([^\s\\]+))', instructions)
        field_names = [quoted or plain for quoted, plain in fields]
        result["field_names"] = field_names
        result["duplicate_field_names"] = duplicates(field_names)
        variables = xml["word/settings.xml"].xpath("//w:docVar", namespaces=NS)
        variable_names = [n.get("{%s}name" % NS["w"]) for n in variables]
        result["docvar_count"] = len(variables)
        result["duplicate_docvar_names"] = duplicates(variable_names)
        result["field_values"] = {
            n.get("{%s}name" % NS["w"]): n.get("{%s}val" % NS["w"])
            for n in variables if n.get("{%s}name" % NS["w"]) in field_names
        }
        result["missing_docvars"] = sorted(set(field_names) - set(variable_names))
        result["activex_descriptors"] = {
            n: package.read(n).decode() for n in names
            if n.startswith("word/activeX/") and n.endswith((".xml", ".rels"))
        }
        result["binaries"] = []
        for name in sorted(names):
            if not name.startswith("word/activeX/") or not name.endswith(".bin"):
                continue
            data = package.read(name)
            record = {"part": name, "size": len(data), "sha256": sha256(data).hexdigest(), "tag_offsets": [m.start() for m in re.finditer(b"TAG_R8_FLD", data)]}
            record["streams"] = []
            if olefile.isOleFile(BytesIO(data)):
                with olefile.OleFileIO(BytesIO(data)) as storage:
                    record["root_clsid"] = storage.root.clsid
                    for entry in storage.listdir(streams=True, storages=False):
                        stream = storage.openstream(entry).read()
                        record["streams"].append({
                            "name": "/".join(entry), "size": len(stream),
                            "sha256": sha256(stream).hexdigest(),
                            "field_names": [v.decode() for v in FD.findall(stream)],
                            "guids": [v.decode() for v in GUID.findall(stream)],
                            "field_offsets": {v.decode(): stream.find(v) for v in FD.findall(stream)},
                            "tag_offsets": [m.start() for m in re.finditer(b"TAG_R8_FLD", stream)],
                            "jpeg_soi_count": stream.count(b"\xff\xd8\xff"),
                            "control_names_found": [n.get("{%s}name" % NS["w"]) for n in controls if n.get("{%s}name" % NS["w"]).encode() in stream],
                        })
            result["binaries"].append(record)
        field_owners = {}
        for binary in result["binaries"]:
            for stream in binary["streams"]:
                for field in set(stream["field_names"]):
                    field_owners.setdefault(field, []).append(binary["part"])
        result["binary_field_owners"] = field_owners
        result["shared_binary_fields"] = {n: owners for n, owners in field_owners.items() if len(owners) > 1}
        result["fields_absent_from_binary"] = sorted(set(field_names) - field_owners.keys())
        result["binary_fields_absent_from_body"] = sorted(field_owners.keys() - set(field_names))
        result["custom_properties"] = package.read("docProps/custom.xml").decode() if "docProps/custom.xml" in names else None
        result["content_types"] = package.read("[Content_Types].xml").decode()
        result["document_relationships"] = package.read("word/_rels/document.xml.rels").decode()
        missing = []
        for name, root in xml.items():
            if not name.endswith(".rels"):
                continue
            base = "" if name == "_rels/.rels" else posixpath.dirname(name).removesuffix("/_rels")
            for rel in root:
                target = rel.get("Target", "")
                if rel.get("TargetMode") == "External":
                    continue
                resolved = posixpath.normpath(posixpath.join(base, target)) if not target.startswith("/") else target[1:]
                if resolved not in names:
                    missing.append({"rels": name, "id": rel.get("Id"), "target": target})
        result["missing_internal_relationship_targets"] = missing
    result["source_unchanged"] = sha256(path.read_bytes()).hexdigest() == result["sha256"]
    return result


if __name__ == "__main__":
    json.dump([inspect(Path(arg)) for arg in sys.argv[1:]], sys.stdout, indent=2)
    print()
