from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
import olefile
import zlib
import re
import struct

def analyze_template_measurements(docx_path):
    with ZipFile(docx_path) as z:
        for name in sorted(z.namelist()):
            if not (name.startswith('word/activeX/') and name.endswith('.bin')):
                continue
            bdata = z.read(name)
            if not olefile.isOleFile(BytesIO(bdata)):
                continue
            with olefile.OleFileIO(BytesIO(bdata)) as ole:
                stream = ole.openstream('Contents').read()
                
            # Parse top level GUIDs
            guids = re.findall(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", stream[:100])
            top_guids = [g.decode() for g in guids]
            
            # Find all TAG_R8_FLD occurrences
            tag_matches = list(re.finditer(rb"TAG_R8_FLD\x00", stream))
            print(f"\nFile: {docx_path.name} -> {name} (size {len(bdata)}, {len(tag_matches)} fields)")
            print(f"  Top GUIDs: {top_guids}")
            
            for m in tag_matches:
                pos = m.end()
                # Next is length-prefixed field name
                flen = struct.unpack("<I", stream[pos:pos+4])[0]
                fname = stream[pos+4:pos+4+flen].rstrip(b"\x00").decode('latin1', errors='ignore')
                pos += 4 + flen
                
                # Next is payload len
                plen = struct.unpack("<I", stream[pos:pos+4])[0]
                pdata = stream[pos+4:pos+4+plen]
                
                # Inside payload: find GUIDs
                pguids = [g.decode() for g in re.findall(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", pdata)]
                
                # Find zlib inside payload
                tool_label = "unknown"
                for zpos in range(len(pdata)-2):
                    if pdata[zpos:zpos+2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
                        try:
                            dec = zlib.decompress(pdata[zpos:])
                            # look for UTF-16 tool name
                            utf16 = re.findall(rb"(?:[\x20-\x7e]\x00){2,}", dec)
                            labels = [u.decode('utf-16le') for u in utf16 if any(k in u.decode('utf-16le', errors='ignore') for k in ['Sp', 'Ar', 'Li', 'Dt', 'Max', 'Min', 'Temp', 'Iso'])]
                            if labels:
                                tool_label = labels[0]
                            break
                        except Exception:
                            pass
                
                print(f"    Field: {fname:<15} | Measurement GUID: {pguids[0] if len(pguids)>0 else 'None'} | Tool: {tool_label}")

for p in sorted(Path('templates/FULL REPORT/NORMAL IR US TEV').glob('*.docx')):
    analyze_template_measurements(p)
