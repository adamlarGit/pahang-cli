from zipfile import ZipFile
from io import BytesIO
import olefile
import zlib
import re

with ZipFile('templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx') as z:
    bdata = z.read('word/activeX/activeX1.bin')
    ole = olefile.OleFileIO(BytesIO(bdata))
    stream = ole.openstream('Contents').read()

# Measurement GUIDs we found earlier in swg-panel:
guids = [
    b"b6ff78c0-1459-43d3-a90a-9246e31cf8ab",
    b"fdd3008e-bb11-4f85-8d78-402a7e2ac8d6",
    b"67554dcf-a2e5-439f-b8b9-5b16c62a57c2",
    b"2c336045-beec-4eca-8283-9f8b408cf619",
]

print("Searching for Measurement GUIDs in swg-panel.docx activeX1.bin:")
for g in guids:
    # 1. In uncompressed stream:
    pos_raw = [m.start() for m in re.finditer(re.escape(g), stream)]
    # Also search for binary GUID (16 bytes) if represented as raw bytes:
    # Convert string GUID to 16 bytes: 4 bytes LE, 2 bytes LE, 2 bytes LE, 2 bytes BE, 6 bytes BE
    import uuid
    u = uuid.UUID(g.decode())
    raw_guid_le = u.bytes_le
    raw_guid_be = u.bytes
    pos_bin_le = [m.start() for m in re.finditer(re.escape(raw_guid_le), stream)]
    pos_bin_be = [m.start() for m in re.finditer(re.escape(raw_guid_be), stream)]
    
    print(f"\nGUID: {g.decode()}")
    print(f"  ASCII occurrences in Contents: {pos_raw}")
    print(f"  Binary (LE) in Contents: {pos_bin_le}")
    print(f"  Binary (BE) in Contents: {pos_bin_be}")

# Now decompress the big zlib stream at 2089 (the sensor image):
dobj = zlib.decompressobj()
dec_sensor = dobj.decompress(stream[2097:])
print(f"\nBig sensor block decompressed size: {len(dec_sensor)}")
for g in guids:
    u = uuid.UUID(g.decode())
    in_ascii = [m.start() for m in re.finditer(re.escape(g), dec_sensor)]
    in_bin_le = [m.start() for m in re.finditer(re.escape(u.bytes_le), dec_sensor)]
    in_bin_be = [m.start() for m in re.finditer(re.escape(u.bytes), dec_sensor)]
    print(f"In decompressed sensor block -> GUID {g.decode()[:8]}: ASCII={in_ascii}, BinLE={in_bin_le}, BinBE={in_bin_be}")
