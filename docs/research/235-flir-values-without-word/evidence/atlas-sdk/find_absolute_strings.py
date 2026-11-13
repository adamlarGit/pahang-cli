"""List strings mentioning an absolute value in FLIR's installed binaries.

Usage: python -I find_absolute_strings.py "<FLIR Systems folder>"
Prints ASCII and UTF-16 strings matching absolut/Substract per binary.
"""
import re
import sys
from pathlib import Path

PAT = re.compile(r"absolut|Substract", re.I)
for f in sorted(Path(sys.argv[1]).rglob("*")):
    if f.suffix.lower() not in {".dll", ".exe", ".ocx"} or "LicProtector" in f.name:
        continue
    b = f.read_bytes()
    found = {m.group().decode() for m in re.finditer(rb"[A-Za-z_][A-Za-z0-9_ ]{3,60}", b) if PAT.search(m.group().decode())}
    found |= {"u16:" + m.group().decode("utf-16-le") for m in re.finditer(rb"(?:[ -~]\x00){4,80}", b)
              if PAT.search(m.group().decode("utf-16-le"))}
    found = {w for w in found if not re.search(r"humidity|width|AbsoluteUri|font size|ABSOLUTE_PATH|AbsolutePosition|AbsoluteTime|RadAbsDose|AbsHumidity", w, re.I)}
    if found:
        print(f"{f.relative_to(sys.argv[1]).as_posix()}: {sorted(found)}")
