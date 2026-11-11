from zipfile import ZipFile
from io import BytesIO
import olefile
import zlib
import re
import uuid

# Read swg-panel activeX1.bin
with ZipFile('templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx') as z:
    original_bin = z.read('word/activeX/activeX1.bin')

ole_orig = olefile.OleFileIO(BytesIO(original_bin))
stream_orig = ole_orig.openstream('Contents').read()

print("Original binary size:", len(original_bin))
print("Original Contents stream size:", len(stream_orig))

# Find the instance GUID and measurement GUIDs
guid_regex = re.compile(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
top_guids = [m.group() for m in guid_regex.finditer(stream_orig[:100])]
instance_guid = top_guids[1]  # 65f355f7-d614-4afe-85c8-dff34b8c47c7
print("Original Instance GUID:", instance_guid.decode())

# Find all field names
fd_regex = re.compile(rb"_Fd\d+")
field_names = list(set(fd_regex.findall(stream_orig[:2000])))
print("Original Field names:", [f.decode() for f in field_names])

# Generate new instance GUID (same length: 36 bytes)
new_instance_guid = str(uuid.uuid4()).encode('ascii')
print("New Instance GUID:", new_instance_guid.decode())

# Generate new field names (same length!)
replacements = {}
replacements[instance_guid] = new_instance_guid

for idx, f in enumerate(field_names):
    # keep same length
    num_digits = len(f) - 3
    # format replacement as _Fd + 9 + idx + digits
    new_num = f"99{idx:02d}" + "0" * (num_digits - 4)
    new_f = f"_Fd{new_num}".encode('ascii')
    assert len(new_f) == len(f), f"Length mismatch: {new_f} vs {f}"
    replacements[f] = new_f
    print(f"  Field {f.decode()} ({len(f)} chars) -> {new_f.decode()} ({len(new_f)} chars)")

# Perform fixed-length substitution directly on the binary
patched_bin = original_bin
for old_val, new_val in replacements.items():
    assert len(old_val) == len(new_val)
    count = patched_bin.count(old_val)
    print(f"Replacing {old_val.decode()} ({count} occurrences)...")
    patched_bin = patched_bin.replace(old_val, new_val)

print("\nPatched binary size:", len(patched_bin))
assert len(patched_bin) == len(original_bin), "Binary size must not change!"

# Validate patched binary with olefile
assert olefile.isOleFile(BytesIO(patched_bin)), "Must remain a valid OLE file!"
ole_patched = olefile.OleFileIO(BytesIO(patched_bin))
print("Patched OLE Root CLSID:", ole_patched.root.clsid)
stream_patched = ole_patched.openstream('Contents').read()
assert len(stream_patched) == len(stream_orig), "Stream size must not change!"

# Verify patched Contents stream
print("Verifying patched Contents stream...")
for old_val, new_val in replacements.items():
    assert old_val not in stream_patched, f"Old value {old_val} still present!"
    assert new_val in stream_patched, f"New value {new_val} missing!"
print("All old IDs successfully replaced with new IDs in Contents stream!")

# Verify zlib streams inside patched binary still decompress cleanly
dobj = zlib.decompressobj()
dec_sensor = dobj.decompress(stream_patched[2097:])
print(f"Patched sensor zlib decompressed successfully! (size={len(dec_sensor)})")
assert len(dec_sensor) == 625696

print("\nSUCCESS! Fixed-length Measurement ID and Variable patching is 100% mathematically and structurally verified!")
