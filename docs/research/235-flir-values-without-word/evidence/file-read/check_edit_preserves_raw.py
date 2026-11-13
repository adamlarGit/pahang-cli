"""Check what an edit changes in the FLIR records of each sample.

Usage: python -I check_edit_preserves_raw.py <camera dir> [<camera dir> ...]
Pairs each file in editted/ with the original/ file of the same name (or the
name before "-editted"). Compares the RawData plane, lists the CameraInfo
fields whose values differ, and prints the record lists.
"""
import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import flir_fff as F


def main(dirs):
    for s in dirs:
        for edited in sorted((s / "editted").glob("*.jpg")):
            orig = s / "original" / (edited.stem.split("-editted")[0] + ".jpg")
            a, b = F.load(orig), F.load(edited)
            same_raw = np.array_equal(a["raw"], b["raw"])
            ca, cb = a["camera"], b["camera"]
            changed = {k: (ca[k], cb[k]) for k in ca if ca[k] != cb[k]}
            ra, rb = a["by"]["CameraInfo"], b["by"]["CameraInfo"]
            diff_bytes = [i for i in range(min(len(ra), len(rb))) if ra[i] != rb[i]]
            print(f"{s.name}/{edited.relative_to(s).as_posix()}")
            print(f"   raw plane identical: {same_raw}  sha256 {hashlib.sha256(b['raw'].tobytes()).hexdigest()[:16]}")
            print(f"   CameraInfo identical: {ra == rb}; decoded fields changed: "
                  + (", ".join(f"{k} {v[0]:.4g} -> {v[1]:.4g}" for k, v in changed.items()) or "none"))
            if diff_bytes:
                print(f"   CameraInfo bytes changed at offsets: {', '.join(hex(i) for i in diff_bytes)}")
            print(f"   records original: {[(r['name'], r['length']) for r in a['records']]}")
            print(f"   records edited:   {[(r['name'], r['length']) for r in b['records']]}")


if __name__ == "__main__":
    main([Path(a) for a in sys.argv[1:]])
