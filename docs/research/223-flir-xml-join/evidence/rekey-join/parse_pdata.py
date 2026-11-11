from zipfile import ZipFile
from io import BytesIO
import olefile
import struct

with ZipFile('templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx') as z:
    bdata = z.read('word/activeX/activeX1.bin')
    ole = olefile.OleFileIO(BytesIO(bdata))
    stream = ole.openstream('Contents').read()

# Let's inspect the sub-record for _Fd1922861825 starting at offset 98:
# Around 98:
# "TAG_R8_FLD\0" (len 11)
# "_Fd1922861825\0" (len 14)
# Next is payload len:
pos = 98 + 11  # after TAG_R8_FLD\0
flen = struct.unpack("<I", stream[pos:pos+4])[0]
pos += 4
fname = stream[pos:pos+flen]
pos += flen

plen = struct.unpack("<I", stream[pos:pos+4])[0]
pos += 4
pdata = stream[pos:pos+plen]

print(f"Field: {fname.decode('latin1')}")
print(f"Payload total length: {len(pdata)} bytes")

# Let's parse the elements inside pdata:
p_pos = 0
elem_idx = 0
while p_pos < len(pdata):
    if p_pos + 4 > len(pdata):
        print(f"Remaining bytes: {pdata[p_pos:].hex()}")
        break
    elem_len = struct.unpack("<I", pdata[p_pos:p_pos+4])[0]
    
    # Check if this looks like a zlib block or raw data
    if pdata[p_pos:p_pos+2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
        print(f"[@ {p_pos}] Element {elem_idx}: Raw ZLIB stream found!")
        break
        
    if elem_len <= len(pdata) - (p_pos + 4):
        elem_content = pdata[p_pos+4:p_pos+4+elem_len]
        # check printable
        try:
            preview = elem_content.decode('latin1')
            if all(32 <= ord(c) < 127 or c in '\r\n\t\0' for c in preview):
                print(f"[@ {p_pos:3d}] Element {elem_idx}: len={elem_len:3d} -> string: {repr(preview)}")
            else:
                print(f"[@ {p_pos:3d}] Element {elem_idx}: len={elem_len:3d} -> hex: {elem_content[:32].hex()}...")
        except Exception:
            print(f"[@ {p_pos:3d}] Element {elem_idx}: len={elem_len:3d} -> hex: {elem_content[:32].hex()}...")
        p_pos += 4 + elem_len
    else:
        print(f"[@ {p_pos:3d}] Element {elem_idx}: non-length value or zlib start: {pdata[p_pos:p_pos+16].hex()}")
        # Check if zlib starts at p_pos
        for z_off in range(p_pos, len(pdata)-2):
            if pdata[z_off:z_off+2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
                print(f"   Zlib starts at offset {z_off} inside payload!")
                p_pos = z_off
                break
        else:
            break
    elem_idx += 1
