"""Check the reader's ellipse pixels against Atlas's own, pixel by pixel.

Usage: python -I check_ellipse_mask.py <samples dir> <values dir>
<values dir> is the output of atlas/atlas_ellipse_pixels.ps1. Atlas lists an
ellipse's pixels row by row from the outside in: top row, bottom row, second
row, second-from-bottom, ..., each row left to right. This script lists the
reader's mask (flir_fff.ellipse_mask) in that order and compares the two
sequences value by value.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import flir_fff as F


def atlas_order(t, m):
    rows = [r for r in range(m.shape[0]) if m[r].any()]
    order = []
    while rows:
        order.append(rows.pop(0))
        if rows:
            order.append(rows.pop())
    return np.concatenate([t[r][m[r]] for r in order])


def main(s: Path, vals: Path):
    for f in sorted(vals.glob("*.txt")):
        stem, tool = f.stem.rsplit("_", 1)
        rel = next(p for p in s.rglob("*.jpg")
                   if p.relative_to(s).with_suffix("").as_posix().replace("/", "_").replace(" ", "_") == stem)
        d = F.load(rel)
        t = F.raw2temp(d["raw"], d["camera"])
        el = next(x for x in F.measurement_tools(d["by"]["MeasurementInfo"])
                  if x["type"] == "ellipse" and x["label"] == tool)
        rect = F.ellipse_rect(el)
        m = F.ellipse_mask(t.shape, rect)
        mine, atlas = atlas_order(t, m), np.loadtxt(f)
        same = len(mine) == len(atlas) and float(np.abs(mine - atlas).max()) < 1e-4
        print(f"{rel.relative_to(s).as_posix()} {tool}: params {el['params']}, rect {rect}")
        print(f"   pixels reader {len(mine)}, Atlas {len(atlas)}; same pixels in the same order: {same}"
              + (f"; largest value diff {np.abs(mine - atlas).max():.2e} C" if len(mine) == len(atlas) else ""))
        print(f"   avg reader {mine.mean():.6f}, Atlas {atlas.mean():.6f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
