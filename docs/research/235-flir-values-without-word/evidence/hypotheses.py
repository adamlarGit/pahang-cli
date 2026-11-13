"""Score alternative reading rules against the owner's 1-decimal readings.

Usage: python -I hypotheses.py <samples dir>
For each rule, counts how many spot and area values equal the owner's after
rounding to one decimal, and the largest absolute error.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import compare_readings as C  # noqa: E402  (runs nothing at import: guarded below)
import flir_fff as F


def cases(s):
    owner = C.owner_table(s / "IR-readings.csv")
    for name in ["FLIR0011", "FLIR0012", "FLIR0013", "FLIR0014"]:
        for col in "CDE":
            if owner[(name, "Sp1")].get(col) is None:
                continue
            f = s / C.SPECIAL.get((name, col), C.FILES.get(col, "").format(n=name))
            yield name, col, f, {k: owner[(name, k)][col] for k in C.KEY}


def spots(tools):
    for tl in tools:
        if tl["type"] == "spot":
            yield (tl["label"] if tl["label"].startswith("Sp") else f"Sp{tl['number']}"), tl["params"]


def model(cam, variant):
    c = dict(cam)
    if variant == "no-atmosphere":
        c["ObjectDistance"] = 0.0
    return c


def main(s):
    data = []
    for name, col, f, own in cases(s):
        d = F.load(f)
        tools = F.measurement_tools(d["by"]["MeasurementInfo"])
        data.append((name, col, d, tools, own))

    rules = {}
    for variant in ["full", "no-atmosphere"]:
        for (dx, dy) in [(0, 0), (-1, 0), (0, -1), (-1, -1), (1, 0), (0, 1), (1, 1)]:
            rules[f"spot {variant} pixel offset ({dx},{dy})"] = ("spot", variant, ("px", dx, dy))
        rules[f"spot {variant} 3x3 mean"] = ("spot", variant, ("mean", 1))
        rules[f"spot {variant} 3x3 mean of raw then convert"] = ("spot", variant, ("rawmean", 1))
        rules[f"spot {variant} 5x5 mean"] = ("spot", variant, ("mean", 2))
        for edge in ["x..x+w-1", "x..x+w", "x+1..x+w-1"]:
            rules[f"box {variant} {edge}"] = ("box", variant, edge)
        rules[f"box {variant} mean of raw then convert"] = ("box", variant, "raw")

    for rname, (kind, variant, how) in rules.items():
        hits = n = 0
        worst = 0.0
        for name, col, d, tools, own in data:
            cam = model(d["camera"], variant)
            raw = d["raw"].astype(float)
            t = F.raw2temp(raw, cam)
            if kind == "spot":
                for lab, (x, y) in spots(tools):
                    if how[0] == "px":
                        v = t[y + how[2], x + how[1]]
                    elif how[0] == "mean":
                        r = how[1]
                        v = t[y - r:y + r + 1, x - r:x + r + 1].mean()
                    else:
                        r = how[1]
                        v = F.raw2temp(raw[y - r:y + r + 1, x - r:x + r + 1].mean(), cam)
                    o = own[lab]
                    n += 1; hits += round(float(v), 1) == round(o, 1); worst = max(worst, abs(v - o))
            else:
                for tl in tools:
                    if tl["type"] != "box":
                        continue
                    x, y, w, h = tl["params"]
                    if how == "x..x+w-1":
                        v = t[y:y + h, x:x + w].mean()
                    elif how == "x..x+w":
                        v = t[y:y + h + 1, x:x + w + 1].mean()
                    elif how == "x+1..x+w-1":
                        v = t[y + 1:y + h, x + 1:x + w].mean()
                    else:
                        v = F.raw2temp(raw[y:y + h, x:x + w].mean(), cam)
                    o = own["Ar1 (avg)"]
                    n += 1; hits += round(float(v), 1) == round(o, 1); worst = max(worst, abs(v - o))
        print(f"{rname:<52} {hits:>2}/{n}  worst {worst:.3f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
