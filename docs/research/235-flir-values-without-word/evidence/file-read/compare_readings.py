"""Compare values computed from each sample file with the owner's readings.

Usage: python -I compare_readings.py <camera dir> [<camera dir> ...]
Each <camera dir> (samples/Flir T640, samples/Flir T440) holds original/,
editted/ and IR-readings.csv (the first T640 version was an xlsx despite its
name). Column C is the original image, D the image after an edit in FLIR
Tools+, E the image after an edit in Word's CIRViewer. "nil" or blank: not read.
Row labels are matched by prefix, so the T440 sheet's "Ar1 (avg)->El1(avg)"
and "Dt (Bx1Mx-Sp1)->Sp1-Sp2" count as Ar1 (avg) and Dt. Dt is the file's spot-to-spot difference tool in
its own order, else its only difference tool (Bx1Mx - Sp1); see readings().
"""
import math
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import flir_fff as F

# A row named after a whole file stem (the T640 ellipse save) maps to editted/<stem>.jpg.
FILES = {"C": "original/{n}.jpg", "D": "editted/{n}.jpg", "E": "editted/{n}.jpg"}
SPECIAL = {
    ("FLIR0012", "D"): "editted/FLIR0012-editted-from-Software-FlirTools+-directly.jpg",
    ("FLIR0012", "E"): "editted/FLIR0012-editted-in-word-using-FlirTools+-CIRViewer.jpg",
}
COLS = {"C": "original", "D": "FLIR Tools+ edit", "E": "Word CIRViewer edit"}
KEY = {"Sp1": "Sp1", "Sp2": "Sp2", "Ar1 (avg)": "Ar1 avg", "Dt": "Dt"}
# Cells where the owner ticked "Show result as an absolute value" in Word
# (comment on #235, 2026-11-13). The tick is not stored in the image.
ABSOLUTE_DT = {("FLIR0012", "E"),
               ("FLIR0012-editted-in-word-using-FlirTools+-CIRViewer-elips", "E")}
# Readings the owner corrected after the sheet was written. 2026-11-13, in the
# agent session: FLIR Tools+ shows Dt as 0.1, not the sheet's -0.1, for the
# FLIR Tools+ edit of FLIR0012, whose tool 1 is labelled Sp2.
CORRECTED = {("FLIR0012", "D", "Dt"): 0.1}


def owner_table(path: Path) -> dict:
    """Owner's readings: a CSV, or (first version) an xlsx saved as .csv."""
    raw = path.read_bytes()
    rows = {}
    if raw[:2] != b"PK":
        import csv
        letters = "ABCDE"
        for i, rec in enumerate(csv.reader(raw.decode("utf-8-sig").splitlines())):
            if i == 0 or not rec:
                continue
            cells = {"A": rec[0], "B": rec[1]}
            for col, v in zip(letters[2:], rec[2:]):
                if v.strip() and v.strip().lower() != "nil":
                    cells[col] = float(v)
            rows[(cells["A"], canonical(cells["B"]))] = cells
        return rows
    z = zipfile.ZipFile(path)
    ss = re.findall(r"<t[^>]*>(.*?)</t>", z.read("xl/sharedStrings.xml").decode())
    for row in re.findall(r"<row[^>]*>(.*?)</row>", z.read("xl/worksheets/sheet1.xml").decode())[1:]:
        cells = {}
        for attrs, body in re.findall(r"<c ([^>]*?)(?:/>|>(.*?)</c>)", row):
            col = re.search(r'r="([A-Z]+)', attrs).group(1)
            v = re.search(r"<v>(.*?)</v>", body or "")
            if v:
                cells[col] = ss[int(v.group(1))] if 't="s"' in attrs else float(v.group(1))
        rows[(cells["A"], cells["B"])] = cells
    return rows


def canonical(label: str) -> str:
    return next((k for k in KEY if label.startswith(k)), label)


def cases(s: Path):
    """(name, column, file, {KEY row: owner value}) for every image read."""
    owner = owner_table(s / "IR-readings.csv")
    names = list(dict.fromkeys(n for n, _ in owner))
    for name in names:
        for col in "CDE":
            own = {k: owner[(name, k)][col] for k in KEY
                   if (name, k) in owner and owner[(name, k)].get(col) is not None}
            if not own:
                continue
            f = s / SPECIAL.get((name, col), FILES.get(col, "").format(n=name))
            yield name, col, f, own


def trunc(v):
    return math.trunc(v * 10) / 10


def main(dirs):
    tally = {"round": 0, "trunc": 0, "n": 0, "maxabs": 0.0, "misses": []}
    for s in dirs:
        for name, col, f, own in cases(s):
            r = F.readings(f)
            print(f"\n== {s.name} | {name} | {COLS[col]} | {f.relative_to(s).as_posix()}")
            cam = r["camera"]
            print("   params: " + ", ".join(f"{k}={cam[k]:.4g}" for k in (
                "Emissivity", "ObjectDistance", "ReflectedApparentTemperature",
                "AtmosphericTemperature", "RelativeHumidity", "IRWindowTransmission")))
            for tl in r["tools"]:
                print(f"   tool {tl['type']} #{tl['number']} label={tl['label']!r} params={tl['params']} extra={tl['extra'] or '-'}")
            print(f"   Ar1 shape: {r['values'].get('Ar1 shape')}")
            deltas = {k: v for k, v in r["values"].items() if k.startswith("delta ")}
            print("   difference tools: " + (", ".join(f"{k[6:]}={v:.3f}" for k, v in deltas.items()) or "-"))
            print(f"   {'value':<10}{'computed':>9}{'round':>7}{'trunc':>7}{'owner':>7}{'c-owner':>9}")
            for ok, ck in KEY.items():
                if ok not in own:
                    continue
                c = r["values"][ck]
                shown = ok
                if ck == "Dt" and (name, col) in ABSOLUTE_DT:
                    c, shown = abs(c), "|Dt|"
                o = round(CORRECTED.get((name, col, ok), own[ok]), 1)
                if (name, col, ok) in CORRECTED:
                    shown += " (corr.)"
                rr, tt = round(c, 1), trunc(c)
                tally["n"] += 1
                tally["round"] += abs(rr - o) < 1e-9
                tally["trunc"] += abs(tt - o) < 1e-9
                tally["maxabs"] = max(tally["maxabs"], abs(c - o))
                if abs(rr - o) > 1e-9:
                    tally["misses"].append(f"{s.name} {name} {COLS[col]} {ok}")
                print(f"   {shown:<10}{c:>9.3f}{rr:>7.1f}{tt:>7.1f}{o:>7.1f}{c - o:>+9.3f}{'' if abs(rr - o) < 1e-9 else '  *'}")
    print(f"\n{tally['n']} values: {tally['round']} equal after rounding, "
          f"{tally['trunc']} equal after truncation, "
          f"largest |computed - owner| = {tally['maxabs']:.3f} C")
    print("misses after rounding: " + ("; ".join(tally["misses"]) or "none"))


if __name__ == "__main__":
    main([Path(a) for a in sys.argv[1:]])
