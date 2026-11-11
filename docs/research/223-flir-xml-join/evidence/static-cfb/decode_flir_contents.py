"""Read-only structural decoder for the R8/KENT specimens studied in #223.

This is a research parser, not a FLIR-compatible loader or binary writer.
"""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import struct
import sys
from uuid import UUID
from zipfile import ZipFile
import zlib

import olefile


MAGIC = 0x4B454E54
MAX_INFLATED = 64 * 1024 * 1024


def lp_string(data, offset):
    size = struct.unpack_from("<I", data, offset)[0]
    end = offset + 4 + size
    if not 0 < size <= 4096 or end > len(data) or data[end - 1] != 0:
        raise ValueError(f"Invalid string at {offset}")
    return data[offset + 4:end - 1].decode("ascii"), end


def kent(data, base=0):
    frames = []
    position = 0
    while position < len(data):
        if position + 10 > len(data):
            raise ValueError(f"Truncated KENT header at {base + position}")
        code, magic, size = struct.unpack_from("<HII", data, position)
        end = position + 10 + size
        bare = magic != MAGIC
        if bare:
            size = struct.unpack_from("<I", data, position)[0]
            end = position + size
            if size != 20 or end > len(data):
                raise ValueError(f"Invalid bare record at {base + position}")
            code = None
            body = data[position:end]
            if struct.unpack_from("<I", body, 4)[0] != 1002:
                raise ValueError("Unimplemented bare record ID")
        else:
            if end > len(data):
                raise ValueError(f"Invalid KENT frame at {base + position}")
            body = data[position + 10:end]
        frame = {"offset": base + position, "code": code, "size": size}
        if code == 102 or bare:
            if size < 20 or struct.unpack_from("<I", body)[0] != size:
                raise ValueError("Unexpected KENT data-frame layout")
            frame["record_id"] = struct.unpack_from("<I", body, 4)[0]
            frame["body_sha256"] = sha256(body).hexdigest()
            if frame["record_id"] == 1000 and size >= 36:
                frame["u32_at_payload_offset_32"] = struct.unpack_from("<I", body, 32)[0]
            if frame["record_id"] == 103:
                text = body[20:]
                if len(text) % 2 == 0:
                    frame["text"] = text.decode("utf-16le").rstrip("\0")
        if code == 107:
            if size != 32:
                raise ValueError(f"Unexpected compressed-block metadata size {size}")
            compressed_size, inflated_size = struct.unpack_from("<II", body, 24)
            if inflated_size > MAX_INFLATED or end + compressed_size > len(data):
                raise ValueError("Compressed block exceeds research parser bounds")
            compressed = data[end:end + compressed_size]
            inflater = zlib.decompressobj()
            plain = inflater.decompress(compressed, inflated_size + 1)
            if not inflater.eof or inflater.unused_data or len(plain) != inflated_size:
                raise ValueError("Compressed-block size/checksum validation failed")
            frame.update({
                "compressed_offset": base + end,
                "compressed_size": compressed_size,
                "inflated_size": inflated_size,
                "inflated_sha256": sha256(plain).hexdigest(),
                "frames": kent(plain),
            })
            end += compressed_size
            if data[end:end + 10] != struct.pack("<HII", 109, MAGIC, 0):
                raise ValueError("Missing compressed-block end marker")
            frame["end_marker_offset"] = base + end
            end += 10
        frames.append(frame)
        position = end
    return frames


def decode(data, base=0):
    version, position = lp_string(data, 0)
    object_id, position = lp_string(data, position)
    sdk_id, position = lp_string(data, position)
    UUID(object_id)
    UUID(sdk_id)
    flag = data[position]
    position += 1
    result = {
        "version": version,
        "object_id": object_id,
        "sdk_id": sdk_id,
        "metadata_flag": flag,
        "size": len(data),
        "fields": [],
    }
    if version != "R8:0.1" or flag not in (0, 1):
        raise ValueError("Unsupported R8 version/metadata flag")
    if flag:
        while True:
            tag_offset = position
            tag, position = lp_string(data, position)
            if tag == "TAG_R8_END":
                result["end_tag_offset"] = base + tag_offset
                break
            if tag != "TAG_R8_FLD":
                raise ValueError(f"Unimplemented R8 metadata tag: {tag}")
            field, position = lp_string(data, position)
            size = struct.unpack_from("<I", data, position)[0]
            position += 4
            payload = data[position:position + size]
            if len(payload) != size:
                raise ValueError("Truncated field object")
            result["fields"].append({
                "tag_offset": base + tag_offset,
                "name": field,
                "payload_offset": base + position,
                "payload_size": size,
                "object": decode(payload, base + position),
            })
            position += size
    result["kent_offset"] = base + position
    result["frames"] = kent(data[position:], base + position)
    return result


def inspect(path):
    source = path.read_bytes()
    results = []
    with ZipFile(BytesIO(source)) as package:
        for part in sorted(package.namelist()):
            if not re.fullmatch(r"word/activeX/activeX\d+\.bin", part):
                continue
            binary = package.read(part)
            with olefile.OleFileIO(BytesIO(binary)) as storage:
                contents = storage.openstream("Contents").read()
            results.append({
                "part": part,
                "binary_sha256": sha256(binary).hexdigest(),
                "contents_sha256": sha256(contents).hexdigest(),
                "decoded": decode(contents),
            })
    if path.read_bytes() != source:
        raise ValueError("Source changed during read-only inspection")
    return {"path": str(path), "sha256": sha256(source).hexdigest(), "binaries": results}


if __name__ == "__main__":
    json.dump([inspect(Path(arg)) for arg in sys.argv[1:]], sys.stdout, indent=2)
    print()
