"""Templates are the single source of the headings below, so their stored casing is guarded here (#201, #202)."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TEXT_PARTS = re.compile(r"word/(document|header\d*|footer\d*)\.xml")
TEMPLATES_BY_HEADING = {
    "EXECUTIVE SUMMARY": (
        "FULL REPORT/executive_summary_census.docx",
        "QUICK REPORT/CBM DEFECT IR SUMMARY.docx",
        "QUICK REPORT/CBM DEFECT IR+US+TEV SUMMARY.docx",
    ),
    "VISUAL DEFECT SUMMARY": (
        "QUICK REPORT/2. VI SUMMARY TEMPLATE Jinja2 DYNAMIC.docx",
    ),
}


def _node_text(node: ElementTree.Element) -> str:
    """Return a node's visible text, counting Word's tabs and line breaks as the spaces they display as."""
    if node.tag == f"{WORD_NS}t":
        return node.text or ""
    return " " if node.tag in (f"{WORD_NS}tab", f"{WORD_NS}br") else ""


def _stored_headings(path: Path, heading: str) -> list[str]:
    """Return every occurrence of the heading as stored, joining runs because Word can split it across them."""
    pattern = re.compile(r"\s+".join(heading.split()), re.IGNORECASE)
    headings: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for part in filter(TEXT_PARTS.fullmatch, archive.namelist()):
            root = ElementTree.fromstring(archive.read(part))
            for paragraph in root.iter(f"{WORD_NS}p"):
                text = "".join(_node_text(node) for node in paragraph.iter())
                headings.extend(pattern.findall(text))
    return headings


@pytest.mark.parametrize("heading", TEMPLATES_BY_HEADING)
def test_templates_store_the_heading_in_capitals(heading: str):
    stored = {
        path.relative_to(TEMPLATES_DIR).as_posix(): _stored_headings(path, heading)
        for path in TEMPLATES_DIR.rglob("*.docx")
        if not path.name.startswith("~$")
    }

    assert all(stored[name] for name in TEMPLATES_BY_HEADING[heading]), "the guard no longer finds the known headings"
    miscased = {name: found for name, found in stored.items() if any(h != heading for h in found)}
    assert miscased == {}
