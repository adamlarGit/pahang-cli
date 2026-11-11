from collections import Counter
import json

# Let's inspect duplicate measurement GUIDs across all binaries
import re
from zipfile import ZipFile
from io import BytesIO
import olefile

all_meas_guids = []
all_top_guids = []
all_bin_fds = []

with ZipFile('.scratch/prod-proof/data/talapia.docx') as z:
    for i in range(1, 28):
        name = f"word/activeX/activeX{i}.bin"
        bdata = z.read(name)
        if not olefile.isOleFile(BytesIO(bdata)):
            continue
        with olefile.OleFileIO(BytesIO(bdata)) as ole:
            stream = ole.openstream('Contents').read()
        
        guids = re.findall(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", stream[:100])
        all_top_guids.extend([g.decode() for g in guids])
        
        # tag matches
        for m in re.finditer(rb"TAG_R8_FLD\x00", stream):
            pos = m.end()
            # flen
            flen = int.from_bytes(stream[pos:pos+4], 'little')
            fname = stream[pos+4:pos+4+flen].rstrip(b"\x00").decode('latin1', errors='ignore')
            all_bin_fds.append(fname)
            pos += 4 + flen
            plen = int.from_bytes(stream[pos:pos+4], 'little')
            pdata = stream[pos+4:pos+4+plen]
            pguids = [g.decode() for g in re.findall(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", pdata)]
            if pguids:
                all_meas_guids.append(pguids[0])

print("Total Top GUIDs:", len(all_top_guids), "Unique:", len(set(all_top_guids)))
print("Total Measurement GUIDs:", len(all_meas_guids), "Unique:", len(set(all_meas_guids)))
print("Total Binary _Fd fields:", len(all_bin_fds), "Unique:", len(set(all_bin_fds)))
