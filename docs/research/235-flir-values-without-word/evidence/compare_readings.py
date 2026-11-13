"""Compare values computed from each sample file with the owner's readings.

Usage: python -I compare_readings.py <samples dir>
<samples dir> holds original/, editted/ and IR-readings.csv (an xlsx file
despite its name). Column C is the original image, D the image after an edit
in FLIR Tools+, E the image after an edit in Word's CIRViewer.
"""
import math
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import flir_fff as F

FILES = {"C": "original/{n}.jpg", "D": "editted/{n}.jpg"}
SPECIAL = {
    ("FLIR0012", "D"): "editted/FLIR0012-editted-from-Software-FlirTools+-directly.jpg",
    ("FLIR0012", "E"): "editted/FLIR0012-editted-in-word-using-FlirTools+-CIRViewer.jpg",
}
COLS = {"C": "original", "D": "FLIR Tools+ edit", "E": "Word CIRViewer edit"}
KEY = {"Sp1": "Sp1", "Sp2": "Sp2", "Ar1 (avg)": "Ar1 avg", "Dt": "Dt"}
# Cells where the owner ticked "Show result as an absolute value" in Word
# (comment on #235, 2026-11-13). The tick is not stored in the image.
ABSOLUTE_DT = {("FLIR0012", "E")}


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
                if v.strip():
                    cells[col] = float(v)
            rows[(cells["A"], cells["B"])] = cells
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


def trunc(v):
    return math.trunc(v * 10) / 10


def main(s: Path):
    owner = owner_table(s / "IR-readings.csv")
    tally = {"round": 0, "trunc": 0, "n": 0, "maxabs": 0.0}
    for name in ["FLIR0011", "FLIR0012", "FLIR0013", "FLIR0014"]:
        for col in "CDE":
            if owner[(name, "Sp1")].get(col) is None:
                continue
            f = s / SPECIAL.get((name, col), FILES.get(col, "").format(n=name))
            r = F.readings(f)
            print(f"\n== {name} | {COLS[col]} | {f.relative_to(s).as_posix()}")
            cam = r["camera"]
            print("   params: " + ", ".join(f"{k}={cam[k]:.4g}" for k in (
                "Emissivity", "ObjectDistance", "ReflectedApparentTemperature",
                "AtmosphericTemperature", "RelativeHumidity", "IRWindowTransmission")))
            for tl in r["tools"]:
                print(f"   tool {tl['type']} #{tl['number']} label={tl['label']!r} params={tl['params']} extra={tl['extra'] or '-'}")
            print(f"   Ar1 shape: {r['values'].get('Ar1 shape')}")
            print(f"   {'value':<10}{'computed':>9}{'round':>7}{'trunc':>7}{'owner':>7}{'c-owner':>9}")
            for ok, ck in KEY.items():
                ok_label = ok
                c = r["values"][ck]
                if ck == "Dt" and (name, col) in ABSOLUTE_DT:
                    c, ok_label = abs(c), "|Dt|"
                o = round(owner[(name, ok)][col], 1)
                rr, tt = round(c, 1), trunc(c)
                tally["n"] += 1
                tally["round"] += abs(rr - o) < 1e-9
                tally["trunc"] += abs(tt - o) < 1e-9
                tally["maxabs"] = max(tally["maxabs"], abs(c - o))
                print(f"   {(ok_label if ck == 'Dt' and (name, col) in ABSOLUTE_DT else ok):<10}{c:>9.3f}{rr:>7.1f}{tt:>7.1f}{o:>7.1f}{c - o:>+9.3f}")
    print(f"\n{tally['n']} values: {tally['round']} equal after rounding, "
          f"{tally['trunc']} equal after truncation, "
          f"largest |computed - owner| = {tally['maxabs']:.3f} C")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
