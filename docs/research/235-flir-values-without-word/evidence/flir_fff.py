"""Read a FLIR radiometric JPEG with no FLIR software.

Layout follows ExifTool's FLIR.pm (https://exiftool.org/TagNames/FLIR.html):
APP1 "FLIR\\0" segments concatenate into one FFF file whose index lists
records: 0x01 RawData, 0x20 CameraInfo, 0x21 MeasurementInfo, ...
Temperature conversion is the one-path Planck and atmosphere model; it
reproduces FLIR Atlas SDK's GetValueFromSignal to 1e-6 C (see
atlas-curve-2026-11-13.log).

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


def transmission(c: dict) -> float:
    """Atmospheric transmission over the whole object distance, one path.

    Matches the value FLIR's Atlas SDK reports as ThermalParameters.Transmission.
    (Thermimage instead splits the path in two halves of OD/2 around an IR
    window, which gives a lower total and readings up to 0.04 C high here.)
    """
    AT, RH, OD = c["AtmosphericTemperature"], c["RelativeHumidity"], c["ObjectDistance"]
    A1, A2 = c["AtmosphericTransAlpha1"], c["AtmosphericTransAlpha2"]
    B1, B2, X = c["AtmosphericTransBeta1"], c["AtmosphericTransBeta2"], c["AtmosphericTransX"]
    h2o = (RH / 100) * math.exp(1.5587 + 0.06939 * AT - 0.00027816 * AT ** 2 + 0.00000068455 * AT ** 3)
    return X * math.exp(-math.sqrt(OD) * (A1 + B1 * math.sqrt(h2o))) +         (1 - X) * math.exp(-math.sqrt(OD) * (A2 + B2 * math.sqrt(h2o)))


def raw2temp(raw, c: dict):
    """Raw signal to deg C: S = E*tau*S_obj + (1-E)*tau*S_refl + (1-tau)*S_atm."""
    if abs(c["IRWindowTransmission"] - 1) > 1e-6:
        raise NotImplementedError("external optics / IR window not covered by the samples")
    E = c["Emissivity"]
    R1, R2, B, F, O = c["PlanckR1"], c["PlanckR2"], c["PlanckB"], c["PlanckF"], c["PlanckO"]
    tau = transmission(c)
    planck = lambda t: R1 / (R2 * (math.exp(B / (t + 273.15)) - F)) - O
    raw = np.asarray(raw, dtype=float)
    obj = (raw - (1 - E) * tau * planck(c["ReflectedApparentTemperature"])
           - (1 - tau) * planck(c["AtmosphericTemperature"])) / (E * tau)
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
        # Header bytes 22-23: flags; low 3 bits set when the tool has its own
        # object parameters ("local parameters", Atlas UseCustomObjectParameters),
        # which are then float32 emissivity, distance (m) and reflected
        # temperature (K) at header bytes 24, 28 and 32.
        flags = struct.unpack(bo + "H", rec[pos + 22:pos + 24])[0]
        local = None
        if flags & 0x07:
            e, od, refl = struct.unpack(bo + "3f", rec[pos + 24:pos + 36])
            local = {"Emissivity": e, "ObjectDistance": od,
                     "ReflectedApparentTemperature": refl - 273.15}
        tools.append({"type": TOOL_TYPES.get(ttype, ttype), "number": num,
                      "params": params, "label": label.split("\x00")[0],
                      "flags": flags, "local": local,
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


def ellipse_rect(tool):
    """Bounding rectangle (x, y, w, h) of an ellipse tool, as Atlas measures it.

    The trailing bytes after the 24-byte common block may hold int16 tag 5,
    length 12, then x, y, w, h. Atlas uses that rectangle when the common
    block's second uint16 is 24 (the offset of the block), as in FLIR Tools+
    saves. When it is 0, as in the Word viewer's save, Atlas ignores the block
    and takes the int16 params [cx, cy, x2, y2, x3, y3], a centre and two
    axis ends: (cx - rx, cy - ry, 2 rx, 2 ry). Both rules reproduce Atlas's
    MeasurementEllipse.Rectangle on the three samples.
    """
    b = bytes.fromhex(tool["extra"])
    use_block = len(b) >= 36 and struct.unpack("<H", b[2:4])[0] == 24
    if use_block:
        tag, length, x, y, w, h = struct.unpack("<6h", b[24:36])
        if tag != 5:
            raise ValueError(f"unexpected ellipse trailing tag {tag}")
        return x, y, w, h
    cx, cy, x2, y2, x3, y3 = tool["params"][:6]
    rx, ry = abs(x2 - cx), abs(y3 - cy)
    return cx - rx, cy - ry, 2 * rx, 2 * ry


def ellipse_mask(shape, rect):
    """Pixels Atlas averages for an ellipse: the filled integer midpoint ellipse.

    Semi-axes rx = w // 2 and ry = h // 2 about pixel (x + rx, y + ry), every
    pixel between the plotted boundary points included. Reproduces Atlas's
    GetValues() pixel set exactly for the two T440 samples (both circles, even
    w); odd sizes and true ellipses are untested.
    """
    x, y, w, h = rect
    rx, ry = w // 2, h // 2
    cx, cy = x + rx, y + ry
    span: dict[int, int] = {}

    def plot(px, py):
        span[py] = max(span.get(py, -1), px)

    xk, yk = 0, ry
    rx2, ry2 = rx * rx, ry * ry
    p1 = ry2 - rx2 * ry + 0.25 * rx2
    dx, dy = 0, 2 * rx2 * yk
    while dx < dy:
        plot(xk, yk)
        xk += 1
        dx += 2 * ry2
        if p1 < 0:
            p1 += dx + ry2
        else:
            yk -= 1
            dy -= 2 * rx2
            p1 += dx - dy + ry2
    p2 = ry2 * (xk + 0.5) ** 2 + rx2 * (yk - 1) ** 2 - rx2 * ry2
    while yk >= 0:
        plot(xk, yk)
        yk -= 1
        dy -= 2 * rx2
        if p2 > 0:
            p2 += rx2 - dy
        else:
            xk += 1
            dx += 2 * ry2
            p2 += dx - dy + rx2
    m = np.zeros(shape, dtype=bool)
    for ay, hw in span.items():
        for row in {cy - ay, cy + ay}:
            if 0 <= row < shape[0]:
                m[row, max(0, cx - hw):min(shape[1], cx + hw + 1)] = True
    return m


# Difference tool params: [type1, number1, member1, type2, number2, member2],
# value = member1 of tool 1 - member2 of tool 2. Members seen so far:
# 1 on a spot (its value), 2 on a box (its maximum; Atlas "Max").
MEMBER = {("spot", 1): "", ("box", 2): "Mx"}
TYPE_CODE = {1: "spot", 2: "box", 3: "ellipse", 10: 10}


def readings(path: Path) -> dict:
    """Spot, area and difference values, unrounded, in deg C.

    Keys: Sp1, Sp2; "Ar1 avg" and "Ar1 max" for the one area (box, ellipse
    or polygon, whatever its label); "Dt" = the file's difference tool between
    two spots, in its own order (tool number 1 minus tool number 2, whatever
    their labels, as FLIR Tools+ and Atlas show it), or else the file's only
    difference tool (a camera original's Bx1Mx - Sp1). Each difference tool
    is also given as "delta <expr>", and "Sp1-Sp2 by label" is kept.
    Tools are matched by their label when it has one, since a FLIR Tools+
    edit can leave tool number 1 labelled Sp2.
    """
    d = load(path)
    t_image = raw2temp(d["raw"], d["camera"])
    tools = measurement_tools(d["by"]["MeasurementInfo"])
    out = {}
    member_value, member_name = {}, {}
    for tl in tools:
        t = t_image
        if tl["local"]:
            # The tool's own emissivity, distance and reflected temperature
            # replace the image's for this tool only.
            t = raw2temp(d["raw"], {**d["camera"], **tl["local"]})
        p = tl["params"]
        lab = tl["label"]
        key = (tl["type"], tl["number"])
        if tl["type"] == "spot":
            name = lab if lab.startswith("Sp") else f"Sp{tl['number']}"
            out[name] = float(t[p[1], p[0]])
            out[name + " number"] = tl["number"]
            member_value[key + (1,)] = out[name]
            member_name[key + (1,)] = name
            continue
        if tl["type"] == "box":
            x, y, w, h = p
            m = np.zeros(t.shape, dtype=bool)
            m[y:y + h, x:x + w] = True
            shape, area = "box", "Bx"
        elif tl["type"] == "ellipse":
            rect = ellipse_rect(tl)
            m = ellipse_mask(t.shape, rect)
            shape, area = f"ellipse {rect}", "El"
        elif tl["type"] == 10:
            m = polygon_mask(t.shape, polygon_points(p))
            shape, area = "polygon", "Ar"
        else:
            continue
        out["Ar1 avg"] = float(t[m].mean())
        out["Ar1 max"] = float(t[m].max())
        out["Ar1 shape"] = f"{shape}, {int(m.sum())} px"
        member_value[key + (2,)] = out["Ar1 max"]
        member_name[key + (2,)] = f"{area}{tl['number']}Mx"
    for tl in tools:
        if tl["type"] != "difference":
            continue
        t1, n1, k1, t2, n2, k2 = tl["params"][:6]
        a = (TYPE_CODE.get(t1, t1), n1, k1)
        b = (TYPE_CODE.get(t2, t2), n2, k2)
        if a in member_value and b in member_value:
            expr = f"{member_name[a]}-{member_name[b]}"
            out[f"delta {expr}"] = member_value[a] - member_value[b]
    if "Sp1" in out and "Sp2" in out:
        out["Sp1-Sp2 by label"] = out["Sp1"] - out["Sp2"]
    deltas = [k for k in out if k.startswith("delta ")]
    spot_deltas = [k for k in deltas if "Mx" not in k]
    if spot_deltas:
        out["Dt"] = out[spot_deltas[0]]
    elif len(deltas) == 1:
        out["Dt"] = out[deltas[0]]
    return {"tools": tools, "values": out, "camera": d["camera"]}
