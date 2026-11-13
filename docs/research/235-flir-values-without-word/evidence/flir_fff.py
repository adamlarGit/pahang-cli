"""Read a FLIR radiometric JPEG with no FLIR software.

Layout follows ExifTool's FLIR.pm (https://exiftool.org/TagNames/FLIR.html):
APP1 "FLIR\\0" segments concatenate into one FFF file whose index lists
records: 0x01 RawData, 0x20 CameraInfo, 0x21 MeasurementInfo, ...
Temperature conversion is the Planck and atmosphere model of the Thermimage
R package's raw2temp, which ExifTool's FLIR notes also point to.

Usage:  python -I flir_fff.py <image.jpg> [...]   prints a dump per image.
"""
from __future__ import annotations

import io
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

RECORD_NAMES = {
    0x01: "RawData", 0x0E: "EmbeddedImage", 0x20: "CameraInfo",
    0x21: "MeasurementInfo", 0x22: "PaletteInfo", 0x23: "TextInfo",
    0x24: "EmbeddedAudioFile", 0x28: "PaintData", 0x2A: "PiP",
    0x2B: "GPSInfo", 0x2C: "MeterLink", 0x2E: "ParamInfo",
}


def fff_bytes(jpeg: bytes) -> bytes:
    parts: dict[int, bytes] = {}
    i = 2
    while i < len(jpeg) - 4 and jpeg[i] == 0xFF:
        marker = jpeg[i + 1]
        if marker == 0xDA:
            break
        seglen = struct.unpack(">H", jpeg[i + 2:i + 4])[0]
        body = jpeg[i + 4:i + 2 + seglen]
        if marker == 0xE1 and body[:5] == b"FLIR\x00":
            parts[body[6]] = body[8:]
        i += 2 + seglen
    if not parts:
        raise ValueError("no FLIR APP1 segments")
    return b"".join(parts[k] for k in sorted(parts))


def records(fff: bytes) -> list[dict]:
    if fff[:4] != b"FFF\x00":
        raise ValueError("not an FFF file")
    ver = struct.unpack(">I", fff[0x14:0x18])[0]
    bo = ">" if 100 <= ver < 200 else "<"
    idx_off, n = struct.unpack(bo + "II", fff[0x18:0x20])
    out = []
    for k in range(n):
        e = fff[idx_off + 32 * k: idx_off + 32 * (k + 1)]
        rtype, sub, rver, rid, off, ln = struct.unpack(bo + "HHIIII", e[:20])
        if rtype == 0:
            continue
        out.append({"type": rtype, "name": RECORD_NAMES.get(rtype, hex(rtype)),
                    "offset": off, "length": ln, "data": fff[off:off + ln]})
    return out


def rec_bo(rec: bytes) -> str:
    # First uint16 is small (1 or 2) when read in the record's own byte order.
    return "<" if struct.unpack("<H", rec[:2])[0] < 0x100 else ">"


def camera_info(rec: bytes) -> dict:
    bo = rec_bo(rec)
    f = lambda o: struct.unpack(bo + "f", rec[o:o + 4])[0]
    s = lambda o, n: rec[o:o + n].split(b"\x00")[0].decode("latin-1")
    k = lambda v: v - 273.15
    rh = f(0x3C)
    return {
        "Emissivity": f(0x20), "ObjectDistance": f(0x24),
        "ReflectedApparentTemperature": k(f(0x28)),
        "AtmosphericTemperature": k(f(0x2C)),
        "IRWindowTemperature": k(f(0x30)),
        "IRWindowTransmission": f(0x34),
        "RelativeHumidity": rh * 100 if rh <= 1 else rh,
        "PlanckR1": f(0x58), "PlanckB": f(0x5C), "PlanckF": f(0x60),
        "AtmosphericTransAlpha1": f(0x70), "AtmosphericTransAlpha2": f(0x74),
        "AtmosphericTransBeta1": f(0x78), "AtmosphericTransBeta2": f(0x7C),
        "AtmosphericTransX": f(0x80),
        "CameraModel": s(0xD4, 32),
        "PlanckO": struct.unpack(bo + "i", rec[0x308:0x30C])[0],
        "PlanckR2": f(0x30C),
    }


def raw_data(rec: bytes) -> np.ndarray:
    bo = rec_bo(rec)
    w, h = struct.unpack(bo + "HH", rec[2:6])
    payload = rec[0x20:]
    if payload[:4] == b"\x89PNG":
        # FLIR writes the PNG samples little-endian; PNG readers assume big.
        return np.array(Image.open(io.BytesIO(payload)), dtype=np.uint16).byteswap()
    return np.frombuffer(payload[: w * h * 2], dtype=bo + "u2").reshape(h, w).astype(np.uint16)


def raw2temp(raw, c: dict):
    E = c["Emissivity"]; OD = c["ObjectDistance"]
    RT = c["ReflectedApparentTemperature"]; AT = c["AtmosphericTemperature"]
    IRWT = c["IRWindowTemperature"]; IRT = c["IRWindowTransmission"]
    RH = c["RelativeHumidity"]
    R1, R2, B, F, O = c["PlanckR1"], c["PlanckR2"], c["PlanckB"], c["PlanckF"], c["PlanckO"]
    A1, A2 = c["AtmosphericTransAlpha1"], c["AtmosphericTransAlpha2"]
    B1, B2, X = c["AtmosphericTransBeta1"], c["AtmosphericTransBeta2"], c["AtmosphericTransX"]
    h2o = (RH / 100) * math.exp(1.5587 + 0.06939 * AT - 0.00027816 * AT ** 2 + 0.00000068455 * AT ** 3)
    tau = X * math.exp(-math.sqrt(OD / 2) * (A1 + B1 * math.sqrt(h2o))) + \
        (1 - X) * math.exp(-math.sqrt(OD / 2) * (A2 + B2 * math.sqrt(h2o)))
    planck = lambda t: R1 / (R2 * (math.exp(B / (t + 273.15)) - F)) - O
    refl = (1 - E) / E * planck(RT)
    atm1 = (1 - tau) / E / tau * planck(AT)
    wind = (1 - IRT) / E / tau / IRT * planck(IRWT)
    atm2 = (1 - tau) / E / tau / IRT / tau * planck(AT)
    obj = np.asarray(raw, dtype=float) / E / tau / IRT / tau - atm1 - atm2 - wind - refl
    return B / np.log(R1 / (R2 * (obj + O)) + F) - 273.15


def load(path: Path) -> dict:
    fff = fff_bytes(path.read_bytes())
    recs = records(fff)
    by = {r["name"]: r["data"] for r in recs}
    return {"fff": fff, "records": recs, "by": by,
            "camera": camera_info(by["CameraInfo"]), "raw": raw_data(by["RawData"])}


if __name__ == "__main__":
    for a in sys.argv[1:]:
        d = load(Path(a))
        t = raw2temp(d["raw"], d["camera"])
        print(f"== {Path(a).parent.name}/{Path(a).name}")
        print("records:", [(r["name"], r["length"]) for r in d["records"]])
        print("camera:", {k: (round(v, 5) if isinstance(v, float) else v) for k, v in d["camera"].items()})
        print("raw:", d["raw"].shape, "min/max C:", round(float(t.min()), 2), round(float(t.max()), 2))


TOOL_TYPES = {1: "spot", 2: "box", 3: "ellipse", 4: "line", 8: "difference"}


def measurement_tools(rec: bytes) -> list[dict]:
    """Tools in a MeasurementInfo record.

    Record header: uint16 byte-order mark, uint16 header length (12),
    uint16 per-tool header length (36). Each tool: 36-byte header holding
    uint16 tool size, ?, params length, label length, ?, type, number;
    then int16 params, then the label (ASCII, or UTF-16LE after a FLIR Tools+
    save), then any trailing per-tool settings up to the tool size.
    """
    bo = rec_bo(rec)
    hdr_len, tool_hdr = struct.unpack(bo + "HH", rec[2:6])
    pos, tools = hdr_len, []
    while pos + tool_hdr <= len(rec):
        size, _, plen, llen, _, ttype, num = struct.unpack(bo + "7H", rec[pos:pos + 14])
        if ttype == 0 and plen == 0:
            break
        p0 = pos + tool_hdr
        params = list(struct.unpack(bo + f"{plen // 2}h", rec[p0:p0 + plen]))
        lab = rec[p0 + plen:p0 + plen + llen]
        label = lab.decode("utf-16-le") if llen > 1 and lab[1:2] == b"\x00" else lab.decode("latin-1")
        tools.append({"type": TOOL_TYPES.get(ttype, ttype), "number": num,
                      "params": params, "label": label.split("\x00")[0],
                      "extra": rec[p0 + plen + llen:pos + size].hex() if size else ""})
        pos += size if size else tool_hdr + plen + llen
    return tools


def polygon_mask(shape, pts):
    """Pixels whose centres lie inside the closed polygon (even-odd rule)."""
    from PIL import ImageDraw
    m = Image.new("1", (shape[1], shape[0]), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in pts], fill=1, outline=1)
    return np.array(m, dtype=bool)


def polygon_points(params):
    """Type 10 params: [n, ?, ?, ?, x1, y1, ..., xn, yn] with the last point = the first."""
    n = params[0]
    flat = params[4:4 + 2 * n]
    return [(flat[2 * k], flat[2 * k + 1]) for k in range(n)]


def readings(path: Path) -> dict:
    """Sp1, Sp2, Ar1 average and Dt = Sp1 - Sp2, unrounded, in deg C.

    Tools are matched by their label when it has one (Sp1, Sp2, Bx1/Ar1),
    since a FLIR Tools+ edit can leave tool number 1 labelled Sp2.
    """
    d = load(path)
    t = raw2temp(d["raw"], d["camera"])
    tools = measurement_tools(d["by"]["MeasurementInfo"])
    out = {}
    for tl in tools:
        p = tl["params"]
        lab = tl["label"]
        if tl["type"] == "spot":
            name = lab if lab.startswith("Sp") else f"Sp{tl['number']}"
            out[name] = float(t[p[1], p[0]])
            out[name + " number"] = tl["number"]
        elif tl["type"] == "box":
            x, y, w, h = p
            out["Ar1 avg"] = float(t[y:y + h, x:x + w].mean())
            out["Ar1 avg (inclusive edge)"] = float(t[y:y + h + 1, x:x + w + 1].mean())
            out["Ar1 shape"] = "box"
        elif tl["type"] == 10:
            m = polygon_mask(t.shape, polygon_points(p))
            out["Ar1 avg"] = float(t[m].mean())
            out["Ar1 shape"] = f"polygon, {m.sum()} px"
    if "Sp1" in out and "Sp2" in out:
        out["Dt"] = out["Sp1"] - out["Sp2"]
    return {"tools": tools, "values": out, "camera": d["camera"]}
