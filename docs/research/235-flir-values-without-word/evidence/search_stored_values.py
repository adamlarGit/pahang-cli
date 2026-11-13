"""Look for the readings themselves inside a file's FLIR metadata records.

Usage: python -I search_stored_values.py <camera dir> [<camera dir> ...]
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


def main(dirs):
    for s in dirs:
        for name, col, f, targets in C.cases(s):
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
            print(f"{s.name} {name} {C.COLS[col]:<20} records searched: "
                  f"{[r['name'] for r in d['records'] if r['name'] not in SKIP]}")
            for h in hits:
                print("   HIT", h)
            if not hits:
                print("   no reading found")


if __name__ == "__main__":
    main([Path(a) for a in sys.argv[1:]])
