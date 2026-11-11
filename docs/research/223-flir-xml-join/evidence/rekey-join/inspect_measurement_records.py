from zipfile import ZipFile
from io import BytesIO
import olefile
import zlib
import re

with ZipFile('templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx') as z:
    bdata = z.read('word/activeX/activeX1.bin')
    ole = olefile.OleFileIO(BytesIO(bdata))
    stream = ole.openstream('Contents').read()
    
    offsets = [267, 734, 1191, 1647]
    for idx, off in enumerate(offsets):
        dobj = zlib.decompressobj()
        dec = dobj.decompress(stream[off:])
        print(f"\n=======================================================")
        print(f"MEASUREMENT SUB-RECORD {idx+1} (offset {off}, decompressed {len(dec)} bytes)")
        print(f"=======================================================")
        
        # Look for Unicode UTF-16LE or ASCII strings
        # In FLIR controls, strings are often UTF-16LE!
        utf16_strings = re.findall(rb"(?:[\x20-\x7e]\x00){2,}", dec)
        print("UTF-16 strings:")
        for s in utf16_strings:
            try:
                print("  UTF-16:", s.decode('utf-16le'))
            except Exception:
                pass
                
        ascii_strings = re.findall(rb"[\x20-\x7e]{3,}", dec)
        print("ASCII strings:")
        for s in ascii_strings:
            print("  ASCII:", s.decode('latin1'))
            
        # Look for floats / doubles / integers
        # Print hex dump of the first 200 bytes
        print("Hex dump (first 160 bytes):")
        for r in range(0, min(len(dec), 160), 16):
            chunk = dec[r:r+16]
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            asc_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            print(f"  {r:04x}: {hex_str:<48}  {asc_str}")
