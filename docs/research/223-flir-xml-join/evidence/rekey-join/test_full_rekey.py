from zipfile import ZipFile
from io import BytesIO
import olefile
import zlib
import re
import uuid

with ZipFile('templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx') as z:
    original_bin = z.read('word/activeX/activeX1.bin')

ole_orig = olefile.OleFileIO(BytesIO(original_bin))
stream_orig = ole_orig.openstream('Contents').read()

# 1. Measurement GUIDs in swg-panel:
meas_guids = [
    b"b6ff78c0-1459-43d3-a90a-9246e31cf8ab",
    b"fdd3008e-bb11-4f85-8d78-402a7e2ac8d6",
    b"67554dcf-a2e5-439f-b8b9-5b16c62a57c2",
    b"2c336045-beec-4eca-8283-9f8b408cf619",
]

# 2. Instance GUID:
instance_guid = b"65f355f7-d614-4afe-85c8-dff34b8c47c7"

# 3. Field names:
field_names = [
    b"_Fd81475520",
    b"_Fd1922861825",
    b"_Fd1967887225",
    b"_Fd97091050"
]

replacements = {}
replacements[instance_guid] = str(uuid.uuid4()).encode('ascii')

for mg in meas_guids:
    new_mg = str(uuid.uuid4()).encode('ascii')
    replacements[mg] = new_mg
    print(f"Measurement GUID {mg.decode()[:8]}... -> {new_mg.decode()[:8]}...")

for idx, f in enumerate(field_names):
    num_digits = len(f) - 3
    new_num = f"99{idx:02d}" + "0" * (num_digits - 4)
    new_f = f"_Fd{new_num}".encode('ascii')
    assert len(new_f) == len(f)
    replacements[f] = new_f
    print(f"Field {f.decode()} -> {new_f.decode()}")

patched_bin = original_bin
for old_val, new_val in replacements.items():
    assert len(old_val) == len(new_val)
    patched_bin = patched_bin.replace(old_val, new_val)

assert len(patched_bin) == len(original_bin)
ole_patched = olefile.OleFileIO(BytesIO(patched_bin))
stream_patched = ole_patched.openstream('Contents').read()
assert len(stream_patched) == len(stream_orig)

for old_val, new_val in replacements.items():
    assert old_val not in stream_patched
    assert new_val in stream_patched

dobj = zlib.decompressobj()
dec_sensor = dobj.decompress(stream_patched[2097:])
assert len(dec_sensor) == 625696

print("\nALL Measurement GUIDs, Instance GUIDs, and Field Variable names successfully re-keyed with ZERO byte offset shifts!")
