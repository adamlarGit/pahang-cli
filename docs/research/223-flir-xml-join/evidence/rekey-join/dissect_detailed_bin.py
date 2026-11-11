from zipfile import ZipFile
from io import BytesIO
import olefile
import zlib
import re
import struct

def dissect_activex_bin(bin_bytes, label=""):
    print(f"\n=======================================================")
    print(f"DISSECTING: {label} (Total size: {len(bin_bytes)} bytes)")
    print(f"=======================================================")
    
    if not olefile.isOleFile(BytesIO(bin_bytes)):
        print("NOT an OLE file!")
        return

    ole = olefile.OleFileIO(BytesIO(bin_bytes))
    print("Root CLSID:", ole.root.clsid)
    print("Directory entries:")
    for entry in ole.listdir(streams=True, storages=True):
        print(f"  - {'/'.join(entry)} ({ole.get_size(entry)} bytes)")
        
    stream = ole.openstream('Contents').read()
    print(f"\nContents stream length: {len(stream)} bytes")
    
    # 1. Parse top-level length-prefixed records before the raw zlib payloads
    pos = 0
    record_idx = 0
    print("\n--- Top-level records in Contents ---")
    while pos < len(stream):
        if pos + 4 > len(stream):
            break
        length = struct.unpack("<I", stream[pos:pos+4])[0]
        
        # Check if this might be a zlib header instead of a length
        if stream[pos:pos+2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda"):
            print(f"[@ {pos}] Found raw zlib block (magic {stream[pos:pos+2].hex()})")
            break
            
        if length > len(stream) - pos:
            print(f"[@ {pos}] Length {length} exceeds remaining stream ({len(stream) - pos} bytes)")
            # Let's see what bytes are here
            print(f"     Hex: {stream[pos:pos+32].hex()}")
            break
            
        data = stream[pos+4:pos+4+length]
        
        # Check if data contains ASCII strings or GUIDs or TAG_R8_FLD
        ascii_strings = re.findall(rb"[A-Za-z0-9_\-\.\:\+]{3,}", data)
        ascii_preview = [s.decode(errors='ignore') for s in ascii_strings]
        
        print(f"[@ {pos:5d}] Record {record_idx:2d} (len={length:5d}): {ascii_preview[:8]}")
        
        # If it contains TAG_R8_FLD, let's dissect it deeper
        if b"TAG_R8_FLD" in data:
            print(f"      -> TAG_R8_FLD block details:")
            tag_pos = 0
            while tag_pos < len(data):
                if tag_pos + 4 > len(data):
                    break
                sub_len = struct.unpack("<I", data[tag_pos:tag_pos+4])[0]
                if sub_len > len(data) - tag_pos:
                    # Maybe raw bytes or flag
                    # Let's print non-length bytes
                    print(f"         Sub-item @ {tag_pos}: raw byte {data[tag_pos]:02x}")
                    tag_pos += 1
                    continue
                sub_data = data[tag_pos+4:tag_pos+4+sub_len]
                sub_strings = re.findall(rb"[A-Za-z0-9_\-\.\:\+]{2,}", sub_data)
                print(f"         Sub-record @ {tag_pos:4d} (len={sub_len:4d}): {[s.decode(errors='ignore') for s in sub_strings]}")
                tag_pos += 4 + sub_len
        
        pos += 4 + length
        record_idx += 1
        if record_idx > 30:
            print("... stopped after 30 records")
            break

dissect_activex_bin(
    ZipFile('templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx').read('word/activeX/activeX1.bin'),
    "templates/.../swg-panel.docx activeX1.bin"
)
