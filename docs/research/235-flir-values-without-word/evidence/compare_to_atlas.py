"""Compare the reader's unrounded values with FLIR's Atlas SDK, tool by tool.

Usage: python -I compare_to_atlas.py <samples dir> <atlas-values log>
The log is the output of atlas/atlas_values.ps1 on the same samples dir.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import flir_fff as F


def atlas_log(path):
    out, cur = {}, None
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("== "):
            cur = line[3:].strip(); out[cur] = {}
        elif m := re.match(r"\s+spot (\S+) at .*value=([-\d.E]+)", line):
            out[cur][m.group(1)] = float(m.group(2))
        elif m := re.match(r"\s+(?:rect|polygon) (\S+) .*avg=([-\d.E]+)", line):
            out[cur]["Ar1 avg"] = float(m.group(2))
        elif m := re.match(r"\s+delta .*?(\S+)/Value - (\S+)/Value value=([-\d.E]+)", line):
            out[cur][f"{m.group(1)}-{m.group(2)}"] = float(m.group(3))
    return out


def main(s, log):
    worst = 0.0
    n = 0
    for rel, vals in atlas_log(log).items():
        mine = F.readings(s / rel)["values"]
        for k, a in vals.items():
            if "-" in k:
                p, q = k.split("-")
                c = mine[p] - mine[q]
            else:
                c = mine[k]
            n += 1
            worst = max(worst, abs(c - a))
            print(f"{rel:<66} {k:<8} reader {c:>10.5f}  Atlas {a:>10.5f}  diff {c - a:+.6f}")
    print(f"\n{n} values, largest |reader - Atlas| = {worst:.6f} C")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
