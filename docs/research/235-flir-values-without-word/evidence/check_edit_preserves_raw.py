"""Check what an edit changes in the FLIR records of each sample.

Usage: python -I check_edit_preserves_raw.py <samples dir>
Compares each edited file's RawData plane and CameraInfo record with the
original's, and prints record lists and MeasurementInfo sizes.
"""
import hashlib
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import flir_fff as F

PAIRS = [
    ("FLIR0011", "editted/FLIR0011.jpg"),
    ("FLIR0012", "editted/FLIR0012-editted-from-Software-FlirTools+-directly.jpg"),
    ("FLIR0012", "editted/FLIR0012-editted-in-word-using-FlirTools+-CIRViewer.jpg"),
    ("FLIR0013", "editted/FLIR0013.jpg"),
    ("FLIR0014", "editted/FLIR0014.jpg"),
]


def main(s: Path):
    for name, edited in PAIRS:
        a, b = F.load(s / "original" / f"{name}.jpg"), F.load(s / edited)
        same_raw = np.array_equal(a["raw"], b["raw"])
        same_cam = a["by"]["CameraInfo"] == b["by"]["CameraInfo"]
        print(f"{edited}")
        print(f"   raw plane identical: {same_raw}  sha256 {hashlib.sha256(b['raw'].tobytes()).hexdigest()[:16]}")
        print(f"   CameraInfo identical: {same_cam}")
        print(f"   records original: {[(r['name'], r['length']) for r in a['records']]}")
        print(f"   records edited:   {[(r['name'], r['length']) for r in b['records']]}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
