from zipfile import ZipFile
from io import BytesIO
import olefile
import zlib
import re
import struct

with ZipFile('.scratch/prod-proof/data/talapia.docx') as z:
    for i in range(1, 28):
        name = f"word/activeX/activeX{i}.bin"
        bdata = z.read(name)
        if not olefile.isOleFile(BytesIO(bdata)):
            continue
        with olefile.OleFileIO(BytesIO(bdata)) as ole:
            stream = ole.openstream('Contents').read()
            
        guids = re.findall(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", stream[:100])
        top_guids = [g.decode() for g in guids]
        tag_matches = list(re.finditer(rb"TAG_R8_FLD\x00", stream))
        
        fields = []
        for m in tag_matches:
            pos = m.end()
            flen = struct.unpack("<I", stream[pos:pos+4])[0]
            fname = stream[pos+4:pos+4+flen].rstrip(b"\x00").decode('latin1', errors='ignore')
            pos += 4 + flen
            plen = struct.unpack("<I", stream[pos:pos+4])[0]
            pdata = stream[pos+4:pos+4+plen]
            pguids = [g.decode() for g in re.findall(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", pdata)]
            fields.append((fname, pguids[0] if pguids else 'None'))
            
        print(f"activeX{i:2d}.bin: size={len(bdata):7d} | Top GUIDs={top_guids} | fields={len(fields)}")
        for f, g in fields:
            print(f"     {f:<15} -> GUID {g}")
