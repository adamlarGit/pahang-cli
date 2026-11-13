"""Look for the readings themselves inside a file's FLIR metadata records.

Usage: python -I search_stored_values.py <samples dir>
For every record except RawData and EmbeddedImage (the pixel data), scans
each 4-byte alignment for float32 and float64 within 0.06 of a reading in
deg C or kelvin, and for int16 tenths of a degree (e.g. 425 for 42.5).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import compare_readings as C
import flir_fff as F

SKIP = {"RawData", "EmbeddedImage"}


def main(s: Path):
    owner = C.owner_table(s / "IR-readings.csv")
    for name in ["FLIR0011", "FLIR0012", "FLIR0013", "FLIR0014"]:
        for col in "CDE":
            if owner[(name, "Sp1")].get(col) is None:
                continue
            f = s / C.SPECIAL.get((name, col), C.FILES.get(col, "").format(n=name))
            targets = {k: owner[(name, k)][col] for k in C.KEY}
            d = F.load(f)
            hits = []
            for r in d["records"]:
                if r["name"] in SKIP:
                    continue
                b = r["data"]
                for off in range(0, len(b) - 3):
                    v32 = struct.unpack("<f", b[off:off + 4])[0]
                    i16 = struct.unpack("<h", b[off:off + 2])[0]
                    for k, t in targets.items():
                        if abs(t) < 0.5:
                            continue  # Dt near 0 matches any zero bytes
                        for unit, tv in (("C", t), ("K", t + 273.15)):
                            if abs(v32 - tv) < 0.06:
                                hits.append(f"{r['name']}+{off:#x} float32 {v32:.3f} ~ {k} {unit}")
                        if off % 2 == 0 and i16 == round(t * 10) and abs(t) >= 5:
                            hits.append(f"{r['name']}+{off:#x} int16 {i16} ~ {k} x10")
            print(f"{name} {C.COLS[col]:<20} records searched: "
                  f"{[r['name'] for r in d['records'] if r['name'] not in SKIP]}")
            for h in hits:
                print("   HIT", h)
            if not hits:
                print("   no reading found")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
