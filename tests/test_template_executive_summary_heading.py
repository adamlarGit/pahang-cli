"""Templates are the single source of the EXECUTIVE SUMMARY heading, so its stored casing is guarded here (#201)."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HEADING = re.compile(r"executive\s+summary", re.IGNORECASE)
TEXT_PARTS = re.compile(r"word/(document|header\d*|footer\d*)\.xml")
TEMPLATES_WITH_HEADING = (
    "FULL REPORT/executive_summary_census.docx",
    "QUICK REPORT/CBM DEFECT IR SUMMARY.docx",
    "QUICK REPORT/CBM DEFECT IR+US+TEV SUMMARY.docx",
)


def _stored_headings(path: Path) -> list[str]:
    """Return each heading as stored, joining runs because Word can split a heading across them."""
    headings: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for part in filter(TEXT_PARTS.fullmatch, archive.namelist()):
            root = ElementTree.fromstring(archive.read(part))
            for paragraph in root.iter(f"{WORD_NS}p"):
                text = "".join(node.text or "" for node in paragraph.iter(f"{WORD_NS}t"))
                headings.extend(HEADING.findall(text))
    return headings


def test_templates_store_the_heading_in_capitals():
    stored = {
        path.relative_to(TEMPLATES_DIR).as_posix(): _stored_headings(path)
        for path in TEMPLATES_DIR.rglob("*.docx")
        if not path.name.startswith("~$")
    }

    assert all(stored[name] for name in TEMPLATES_WITH_HEADING), "the guard no longer finds the known headings"
    miscased = {name: found for name, found in stored.items() if any(h != "EXECUTIVE SUMMARY" for h in found)}
    assert miscased == {}
