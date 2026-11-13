"""Compare FLIR Atlas SDK's own values with the owner's readings.

Usage: python -I compare_atlas_to_readings.py <samples dir> <atlas-values log>
The log is the output of atlas_values.ps1 on <samples dir> (the folder that
holds Flir T640/ and Flir T440/). The owner's readings and the cases come
from ../file-read/compare_readings.py, with the same absolute-Dt ticks and
the same corrected value. Atlas's Dt is its delta between two spots, in
Atlas's own order; on a camera original with no Sp2 it is the camera's
Bx1Mx - Sp1 delta.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "file-read"))
import compare_readings as C  # noqa: E402


def atlas_log(path):
    out, cur = {}, None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("== "):
            cur = line[3:].strip(); out[cur] = {"deltas": []}
        elif m := re.match(r"\s+spot (\S+) at .*value=([-\d.E]+)", line):
            out[cur][m.group(1)] = float(m.group(2))
        elif m := re.match(r"\s+(?:rect|polygon|ellipse) (\S+) .*avg=([-\d.E]+)", line):
            out[cur]["Ar1 (avg)"] = float(m.group(2))
        elif m := re.match(r"\s+delta \S* ?(\S+)/(\w+) - (\S+)/(\w+) value=([-\d.E]+)", line):
            out[cur]["deltas"].append((m.group(2) == "Value" and m.group(4) == "Value", float(m.group(5))))
    for v in out.values():
        spot = [d for ok, d in v["deltas"] if ok]
        v["Dt"] = spot[0] if spot else (v["deltas"][0][1] if len(v["deltas"]) == 1 else None)
    return out


def main(samples: Path, log: str):
    sys.stdout.reconfigure(encoding="utf-8")
    atlas = atlas_log(log)
    n = hits = 0
    misses, post = [], [0, 0]
    for cam in ("Flir T640", "Flir T440"):
        s = samples / cam
        for name, col, f, own in C.cases(s):
            rel = f.relative_to(samples).as_posix()
            a = atlas[rel]
            print(f"\n== {rel} | {C.COLS[col]}")
            for key in C.KEY:
                if key not in own:
                    continue
                v = a.get(key)
                if key == "Dt" and v is not None and (name, col) in C.ABSOLUTE_DT:
                    v = abs(v)
                o = round(C.CORRECTED.get((name, col, key), own[key]), 1)
                ok = v is not None and abs(round(v, 1) - o) < 1e-9
                n += 1; hits += ok
                if col != "C":
                    post[0] += 1; post[1] += ok
                if not ok:
                    misses.append(f"{cam} {name} {C.COLS[col]} {key}")
                print(f"   {key:<10} Atlas {v:>9.4f}  shown {o:>6.1f}{'' if ok else '  *'}")
    print(f"\n{n} values: {hits} equal after rounding; after an edit {post[1]} of {post[0]}")
    print("misses: " + ("; ".join(misses) or "none"))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
