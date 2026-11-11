from zipfile import ZipFile
from io import BytesIO
from lxml import etree
import olefile
import re

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

with ZipFile('.scratch/joined_swg_panels_proof.docx') as z:
    doc_xml = etree.fromstring(z.read('word/document.xml'))
    doc_rels = etree.fromstring(z.read('word/_rels/document.xml.rels'))
    settings_xml = etree.fromstring(z.read('word/settings.xml'))
    
    controls = doc_xml.xpath('//w:control', namespaces=NS)
    print(f"Controls count: {len(controls)}")
    for idx, c in enumerate(controls):
        name = c.get(f"{{{NS['w']}}}name")
        rid = c.get(f"{{{NS['r']}}}id")
        shapeid = c.get(f"{{{NS['w']}}}shapeid")
        print(f"  Control {idx+1}: name='{name}', r:id='{rid}', shapeid='{shapeid}'")
        
    # Check binaries
    bins = [n for n in z.namelist() if n.startswith('word/activeX/') and n.endswith('.bin')]
    print(f"\nActiveX Binaries: {bins}")
    for b in bins:
        bdata = z.read(b)
        assert olefile.isOleFile(BytesIO(bdata)), f"{b} is NOT valid OLE!"
        with olefile.OleFileIO(BytesIO(bdata)) as ole:
            stream = ole.openstream('Contents').read()
            guid_regex = re.compile(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
            guids = [g.decode() for g in guid_regex.findall(stream[:100])]
            fds = [m.decode() for m in set(re.findall(rb"_Fd\d+", stream))]
            print(f"  {b}: size={len(bdata)}, instance_guid={guids[1]}, fds={fds}")
            
    # Check DOCVARIABLE fields in document.xml
    instrs = doc_xml.xpath('//w:instrText/text()', namespaces=NS)
    fd_fields = [m for i in instrs for m in re.findall(r'_Fd\d+', i)]
    print(f"\nDocument.xml DOCVARIABLE fields ({len(fd_fields)} total):")
    print(f"  Fields: {fd_fields}")
    print(f"  Unique fields: {len(set(fd_fields))}")
    assert len(fd_fields) == len(set(fd_fields)), "All DOCVARIABLE fields must be unique!"
    
    # Check settings.xml docVars
    docvars = settings_xml.xpath('//w:docVar/@w:name', namespaces=NS)
    print(f"\nSettings.xml docVar count: {len(docvars)}")
    for f in fd_fields:
        assert f in docvars, f"Field {f} missing from settings.xml!"
    print("All DOCVARIABLE fields are correctly declared in settings.xml!")

print("\n>>> ALL VALIDATION CHECKS PASSED PERFECTLY! <<<")
