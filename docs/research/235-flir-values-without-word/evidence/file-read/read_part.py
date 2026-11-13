"""Read the IR table values of a delivered Part (.docx) with Word closed.

Usage: uv run --frozen --with olefile python -I read_part.py <part.docx>

Two independent routes, compared field by field:

1. Cached: every viewer field in the body is a DOCVARIABLE field. Its value
   is a w:docVar in word/settings.xml, and Word keeps the last result as
   text in document.xml.
2. Computed: each viewer's ActiveX binary (a CFB file, stream "Contents",
   decoded with #223's decode_flir_contents.py) carries the camera's own
   CameraInfo record and raw plane in record 1017, and one record group per
   measurement tool. The values are computed from those with flir_fff.py.

The file is opened read-only and its SHA-256 is checked before and after.
Prints one line per field and a summary.
"""
import hashlib
import html
import re
import struct
import sys
import zlib
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import olefile

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "223-flir-xml-join" / "evidence" / "static-cfb"))
import decode_flir_contents as D  # noqa: E402
import flir_fff as F  # noqa: E402

# Record 1001 in a tool group: the tool's kind.
TOOL_KIND = {1: "spot", 4: "box", 16: "polygon", 1024: "delta"}


def inflate(src, frames):
    for f in frames:
        if "compressed_offset" in f:
            yield zlib.decompress(src[f["compressed_offset"]:f["compressed_offset"] + f["compressed_size"]])


def body(plain, f):
    return plain[f["offset"] + 10:f["offset"] + 10 + f["size"]]


def i32s(b):
    pl = b[20:]
    return list(struct.unpack(f"<{len(pl) // 4}i", pl[:len(pl) // 4 * 4]))


def viewer_state(contents):
    """CameraInfo, raw plane and tools from a viewer's Contents stream."""
    dec = D.decode(contents)
    plain = list(inflate(contents, dec["frames"]))[-1]
    frames = D.kent(plain)
    r1017 = next(f for f in frames if f.get("record_id") == 1017)
    b = body(plain, r1017)
    # CameraInfo sits whole inside record 1017, in the FFF layout: the camera
    # model string at +0xD4 names it, and the record is 2476 bytes long.
    ci_at = b.find(b"FLIR", 0, 4096) - 0xD4
    ci = b[ci_at:ci_at + 2476]
    cam = F.camera_info(ci)
    w, h = struct.unpack("<HH", ci[2:6])
    raw = np.frombuffer(b[len(b) - w * h * 2:], "<u2").reshape(h, w)
    # Tool groups follow record 112 (the rendered picture). Each group ends
    # with a text record 103 holding the tool's label.
    start = next(i for i, f in enumerate(frames) if f.get("record_id") == 112) + 1
    tools, group = [], []
    for f in frames[start:]:
        if f.get("code") != 102:
            continue
        rid = f.get("record_id")
        if rid == 103:
            label = body(plain, f)[20:].decode("utf-16le").rstrip("\0")
            kinds = [i32s(body(plain, g))[0] for g in group if g.get("record_id") == 1001]
            geoms = [i32s(body(plain, g)) for g in group if g.get("record_id") == 104]
            params = [body(plain, g) for g in group if g.get("record_id") == 1000 and g["size"] == 80]
            tools.append({"label": label, "kind": TOOL_KIND.get(kinds[0], kinds[0]) if kinds else None,
                          "geometry": geoms[0] if geoms else None, "formula": None,
                          "object_params": struct.unpack("<15f", params[0][20:80]) if params else None})
            group = []
        elif rid == 1004 and tools and tools[-1]["kind"] == "delta" and f["size"] > 20:
            # The delta's formula follows its label, e.g.
            # "abs([ana.Sp1.temp] - [ana.Sp2.temp])", UTF-16LE.
            fb = body(plain, f)[20:]
            end = next((i for i in range(0, len(fb) - 1, 2) if fb[i:i + 2] == b"\x00\x00"), len(fb))
            tools[-1]["formula"] = fb[:end].decode("utf-16le")
        else:
            group.append(f)
    fields = []
    for fld in dec["fields"]:
        o = fld["object"]
        src = contents[o["kent_offset"]:fld["payload_offset"] + fld["payload_size"]]
        fp = list(inflate(src, D.kent(src)))[0]
        r = next(f for f in D.kent(fp) if f.get("record_id") == 1000)
        fb = body(fp, r)
        # Bytes 20-32: tool class (8 spot, 7 area, 10 delta), member (32 spot
        # value, 64 area average, 61 area maximum, 104 delta value) and tool
        # number; bytes 32-36 repeat the field's own _Fd number (223 C11).
        kind, member, number = struct.unpack("<3I", fb[20:32])
        # The caption is UTF-16LE from byte 37 up to the first NUL character.
        cap = fb[37:]
        end = next((i for i in range(0, len(cap) - 1, 2) if cap[i:i + 2] == b"\x00\x00"), len(cap))
        caption = cap[:end].decode("utf-16le", "replace")
        fields.append({"name": fld["name"], "code": kind, "member": member, "number": number, "caption": caption})
    return {"camera": cam, "raw": raw, "tools": tools, "fields": fields, "sdk_id": dec["sdk_id"]}


def tool_values(state):
    """Unrounded value per tool label, and the area mean and max."""
    cam = state["camera"]
    out = {}
    for tl in state["tools"]:
        c = dict(cam)
        if tl["object_params"]:
            # Per-tool object parameters: emissivity, reflected temperature
            # (K), atmospheric temperature (K), distance, ?, ?, humidity (0-1).
            e, refl, atm, dist, _, _, rh = tl["object_params"][:7]
            c.update(Emissivity=e, ReflectedApparentTemperature=refl - 273.15,
                     AtmosphericTemperature=atm - 273.15, ObjectDistance=dist,
                     RelativeHumidity=rh * 100)
        t = F.raw2temp(state["raw"], c)
        g = tl["geometry"]
        if tl["kind"] == "spot":
            out[tl["label"]] = float(t[g[2], g[1]])
        elif tl["kind"] == "box":
            # Geometry [2, x1, y1, x2, y2], both corners included. The
            # exclusive reading x1..x2-1 is kept for the log.
            _, x1, y1, x2, y2 = g
            r = t[y1:y2 + 1, x1:x2 + 1]
            out[tl["label"] + " avg"] = float(r.mean())
            out[tl["label"] + " max"] = float(r.max())
            out[tl["label"] + " min"] = float(r.min())
            out[tl["label"] + " avg excl"] = float(t[y1:y2, x1:x2].mean())
        elif tl["kind"] == "polygon":
            pts = [(g[1 + 2 * k], g[2 + 2 * k]) for k in range(g[0])]
            m = F.polygon_mask(t.shape, pts + [pts[0]])
            out[tl["label"] + " avg"] = float(t[m].mean())
            out[tl["label"] + " max"] = float(t[m].max())
            out[tl["label"] + " min"] = float(t[m].min())
    for tl in state["tools"]:
        if tl["kind"] == "delta" and tl["formula"]:
            out[tl["label"]] = evaluate(tl["formula"], out)
    return out


MEMBER = {"temp": "", "max": " max", "min": " min", "avg": " avg"}
FIELD_MEMBER = {32: "", 64: " avg", 61: " max", 104: ""}


def evaluate(formula, vals):
    """Evaluate a viewer formula such as abs([ana.Sp1.max] - [ana.Sp2.temp])."""
    def ref(m):
        return repr(vals[m.group(1) + MEMBER[m.group(2)]])
    expr = re.sub(r"\[ana\.(\w+)\.(\w+)\]", ref, formula)
    if not re.fullmatch(r"[\d.eE+\-*/() ]*|abs\([\d.eE+\-*/() ]*\)", expr):
        raise ValueError(f"unsupported formula {formula!r}")
    return float(eval(expr, {"__builtins__": {}}, {"abs": abs}))


def number(text):
    m = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(m.group()) if m else None


def main(path: Path):
    sys.stdout.reconfigure(encoding="utf-8")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    z = ZipFile(path)
    doc = z.read("word/document.xml").decode("utf-8")
    settings = z.read("word/settings.xml").decode("utf-8")
    docvars = {a: html.unescape(b) for a, b in re.findall(r'<w:docVar w:name="([^"]+)" w:val="([^"]*)"', settings)}
    # Field results in document order, with the nearest table-row text before each.
    results = {}
    for m in re.finditer(r'<w:instrText[^>]*>\s*DOCVARIABLE\s+(\S+)', doc):
        end = doc.find('w:fldCharType="end"', m.end())
        sep = doc.find('w:fldCharType="separate"', m.end())
        res = "".join(html.unescape(t) for t in re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", doc[sep:end]))
        row_start = doc.rfind("<w:tr ", 0, m.start())
        label = " ".join(html.unescape(t) for t in re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", doc[row_start:m.start()])).strip()
        results.setdefault(m.group(1), []).append((res, label[-40:]))
    print(f"{path.name}: {len(z.namelist())} parts, {sum(len(v) for v in results.values())} DOCVARIABLE uses, "
          f"{len(results)} names, {len(docvars)} w:docVar entries")
    parts = sorted((n for n in z.namelist() if re.fullmatch(r"word/activeX/activeX\d+\.bin", n)),
                   key=lambda n: int(re.findall(r"\d+", n)[0]))
    tally = {"fields": 0, "cache_eq_var": 0, "computed_eq_cache": 0, "misses": []}
    seen = set()
    for part in parts:
        with olefile.OleFileIO(BytesIO(z.read(part))) as st:
            contents = st.openstream("Contents").read()
        s = viewer_state(contents)
        vals = tool_values(s)
        cam = s["camera"]
        print(f"\n== {part.split('/')[-1]} {cam['CameraModel']} raw {s['raw'].shape[1]}x{s['raw'].shape[0]} "
              f"E={cam['Emissivity']:.3g} OD={cam['ObjectDistance']:.3g} tools "
              + ", ".join(f"{t['label']}:{t['kind']}" + ("" if t["kind"] in ("spot", "polygon", "delta") else f" geometry {t['geometry']}") for t in s["tools"]))
        print("   computed: " + ", ".join(f"{k}={v:.3f}" for k, v in vals.items()))
        for fld in s["fields"]:
            name = fld["name"]
            seen.add(name)
            uses = results.get(name, [])
            var = docvars.get(name)
            cap = fld["caption"]
            # The caption's label names the tool; its member text can be stale
            # ("Ar1.Max. Temperature" on an average field), so the member
            # comes from the field's member code.
            lab = cap.split(".")[0]
            how = lab + FIELD_MEMBER.get(fld["member"], f" member {fld['member']}")
            if fld["code"] == 10:
                formula = next((t["formula"] for t in s["tools"] if t["label"] == lab), None)
                how = f"{lab} = {formula}"
                comp = vals.get(lab)
            else:
                comp = vals.get(lab + FIELD_MEMBER.get(fld["member"], "?"))
            cached = number(uses[0][0]) if uses else None
            tally["fields"] += 1
            tally["cache_eq_var"] += bool(uses) and all(number(u[0]) == number(var) for u in uses)
            ok = comp is not None and cached is not None and round(comp, 1) == cached
            tally["computed_eq_cache"] += ok
            if not ok:
                tally["misses"].append(f"{part.split('/')[-1]} {name} {cap}")
            maxinfo = ""
            print(f"   {name:<15} class {fld['code']:>2} member {fld['member']:>3} #{fld['number']} caption {cap!r:<24} var {number(var)} "
                  f"cached {[number(u[0]) for u in uses]} row {(uses[0][1] if uses else None)!r} "
                  f"computed {how}={'-' if comp is None else f'{comp:.3f}'}{maxinfo}{'' if ok else '  *'}")
    unused = sorted(set(results) - seen)
    print(f"\n{tally['fields']} viewer fields: cached result equals the w:docVar in {tally['cache_eq_var']}, "
          f"computed value equals the cached result in {tally['computed_eq_cache']}")
    print("mismatches: " + ("; ".join(tally["misses"]) or "none"))
    print(f"body DOCVARIABLE names held by no viewer: {len(unused)}")
    for name in unused:
        for res, row in results[name]:
            print(f"   {name:<15} var {number(docvars.get(name))} cached {number(res)} row {row.split('  ')[-1][-30:]!r}")
    print("file unchanged by the read:", hashlib.sha256(path.read_bytes()).hexdigest() == before)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
