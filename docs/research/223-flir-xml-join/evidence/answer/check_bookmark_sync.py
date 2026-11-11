"""Compare each field's _Fd name with the numeric bookmark inside its compressed field archive.

Read-only. For every TAG_R8_FLD record in every word/activeX/*.bin Contents stream,
print the ASCII field name and the little-endian uint32 at offset 52 of the inflated
field archive. The static-cfb Path found the two equal in 111 of 111 fields.

Usage: python check_bookmark_sync.py <docx> [<docx> ...]
"""

import re
import struct
import sys
import zlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import olefile

TAG = re.compile(re.escape(b"TAG_R8_FLD\x00"))
ZLIB_HEADER = re.compile(rb"\x78[\x01\x5e\x9c\xda]")
UUID = re.compile(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def inflate_first(payload: bytes) -> bytes | None:
    for match in ZLIB_HEADER.finditer(payload):
        try:
            return zlib.decompressobj().decompress(payload[match.start():])
        except zlib.error:
            continue
    return None


def check(path: Path) -> None:
    same = different = unreadable = 0
    object_ids: list[str | None] = []
    sdk_ids: list[str | None] = []
    with ZipFile(path) as package:
        parts = [n for n in package.namelist() if n.startswith("word/activeX/") and n.endswith(".bin")]
        parts.sort(key=lambda n: int(re.search(r"(\d+)\.bin$", n).group(1)))
        print(f"\n== {path.name} ({len(parts)} binaries)")
        for part in parts:
            data = package.read(part)
            if not olefile.isOleFile(BytesIO(data)):
                continue
            with olefile.OleFileIO(BytesIO(data)) as ole:
                stream = ole.openstream("Contents").read()
            top = [g.decode("ascii") for g in UUID.findall(stream[:100])]
            object_ids.append(top[0] if top else None)
            sdk_ids.append(top[1] if len(top) > 1 else None)
            for match in TAG.finditer(stream):
                pos = match.end()
                name_len = struct.unpack_from("<I", stream, pos)[0]
                name = stream[pos + 4:pos + 4 + name_len].rstrip(b"\x00").decode("latin1")
                pos += 4 + name_len
                payload_len = struct.unpack_from("<I", stream, pos)[0]
                plain = inflate_first(stream[pos + 4:pos + 4 + payload_len])
                if plain is None or len(plain) < 56:
                    unreadable += 1
                    print(f"  {Path(part).name:<16} {name:<16} archive not readable")
                    continue
                bookmark = struct.unpack_from("<I", plain, 52)[0]
                match_text = "same" if str(bookmark) == name[3:] else "DIFFERENT"
                same += match_text == "same"
                different += match_text == "DIFFERENT"
                print(f"  {Path(part).name:<16} {name:<16} bookmark {bookmark:<12} {match_text}")
    print(f"   total: {same} same, {different} different, {unreadable} unreadable")
    print(f"   viewer object UUIDs: {len(object_ids)}, unique {len(set(object_ids))}")
    print(f"   viewer SDK UUIDs:    {len(sdk_ids)}, unique {len(set(sdk_ids))}")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        check(Path(arg))
