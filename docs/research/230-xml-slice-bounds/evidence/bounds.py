"""PROTOTYPE for #230. Throwaway, read-only. Not production code.

Reads each Quick Report's word/document.xml, derives every slice bound from explicit page
breaks and heading paragraphs, and checks the CBM defect pieces. No Word.

    uv run --frozen python docs/research/230-xml-slice-bounds/evidence/bounds.py \
        --config <path to .cli_config.json> --out <temp dir>

With --com, it also runs WordComDocumentSlicer on temp copies of the five benchmark reports
and compares each COM slice with the prototype's slice. Output goes only to --out, except the
summary files written next to this script with --write-evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

import docx  # noqa: E402
from docx.table import Table  # noqa: E402

from src.full_report.attribution import verify_cbm_defect_attribution  # noqa: E402
from src.full_report.defect_parser import CbmDefectHeaderParser  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
V_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"

COND = "SUBSTATION CONDITION"
STICKER = "NORMAL/DEFECT STICKER"
VI = "VISUAL DEFECT"
VISUM = "VISUAL DEFECT SUMMARY"
CBMSUM = ("EXECUTIVE SUMMARY", "CBM DEFECT SUMMARY")
HEADINGS = (COND, STICKER, VI, VISUM, *CBMSUM)

BENCHMARKS = {
    "talapia": "005. TALAPIA",
    "sentosa": "007. CS RESTORAN SENTOSA",
    "094": "094. CHAN YIM SOM",
    "apmm": "01. PPU APMM",
    "pe157": "157. PERPUSTAKAAN AWAM",
}

PARSER = CbmDefectHeaderParser()


def norm(text: str) -> str:
    return " ".join(text.split()).upper()


# ---------------------------------------------------------------------------
# Unit stream: the body flattened into text segments, tables and page breaks.
# A paragraph holding a page break is split into the text before and after it.
# ---------------------------------------------------------------------------


@dataclass
class Unit:
    kind: str  # "text" | "tbl" | "break"
    elem: int  # index of the top-level body element
    text: str = ""
    w_t_count: int = 0  # how many w:t carried this text
    table: Table | None = None
    blips: int = 0
    objects: int = 0
    break_kind: str = ""  # "br" | "pageBreakBefore" | "sectPr"


def _paragraph_units(p, idx: int) -> list[Unit]:
    units: list[Unit] = []
    ppr = p.find(W + "pPr")
    if ppr is not None and ppr.find(W + "pageBreakBefore") is not None:
        val = ppr.find(W + "pageBreakBefore").get(W + "val", "true")
        if val not in ("0", "false", "off"):
            units.append(Unit("break", idx, break_kind="pageBreakBefore"))
    cur = Unit("text", idx)
    for el in p.iter():
        if el.tag == W + "t":
            cur.text += el.text or ""
            cur.w_t_count += 1
        elif el.tag == W + "tab":
            cur.text += " "
        elif el.tag == W + "br" and el.get(W + "type") == "page":
            units.append(cur)
            units.append(Unit("break", idx, break_kind="br"))
            cur = Unit("text", idx)
        elif el.tag in (A_BLIP, V_IMAGEDATA):
            cur.blips += 1
        elif el.tag == W + "object":
            cur.objects += 1
    units.append(cur)
    if ppr is not None and ppr.find(W + "sectPr") is not None:
        units.append(Unit("break", idx, break_kind="sectPr"))
    return units


def read_units(path: Path) -> tuple[list[Unit], dict]:
    d = docx.Document(str(path))
    body = d.element.body
    units: list[Unit] = []
    info = {"breaks_inside_tables": [], "lrpb_before_first_break": 0}
    for idx, el in enumerate(body):
        if el.tag == W + "p":
            units.extend(_paragraph_units(el, idx))
        elif el.tag == W + "tbl":
            t = Table(el, d._body)
            inner = [b for b in el.iter(W + "br") if b.get(W + "type") == "page"]
            if inner:
                info["breaks_inside_tables"].append({"elem": idx, "breaks": len(inner)})
            units.append(
                Unit(
                    "tbl",
                    idx,
                    text="".join(x.text or "" for x in el.iter(W + "t")),
                    table=t,
                    blips=sum(1 for x in el.iter() if x.tag in (A_BLIP, V_IMAGEDATA)),
                    objects=sum(1 for _ in el.iter(W + "object")),
                )
            )
        # sectPr, bookmarkEnd and other body children carry no slice content
    # Word's own saved layout, as a hint: a rendered page break before the first explicit
    # break means the front page spilled onto page 2 the last time Word saved the file.
    for el in body:
        if any(b.get(W + "type") == "page" for b in el.iter(W + "br")):
            break
        info["lrpb_before_first_break"] += sum(1 for _ in el.iter(W + "lastRenderedPageBreak"))
    return units, info


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


def heading_at(u: Unit) -> str | None:
    if u.kind != "text":
        return None
    t = norm(u.text)
    return t if t in HEADINGS else None


def find_heading(units: list[Unit], names, start: int = 0, end: int | None = None) -> int | None:
    names = (names,) if isinstance(names, str) else names
    end = len(units) if end is None else end
    for i in range(start, end):
        if heading_at(units[i]) in names:
            return i
    return None


def next_break(units: list[Unit], start: int, end: int | None = None) -> int:
    end = len(units) if end is None else end
    for i in range(start, end):
        if units[i].kind == "break":
            return i
    return end


def near_miss_headings(units: list[Unit]) -> list[dict]:
    """Paragraphs that look like a slicer heading but don't equal one: retyped or split."""
    out = []
    texts = [(i, norm(u.text)) for i, u in enumerate(units) if u.kind == "text" and u.text.strip()]
    for i, t in texts:
        if t in HEADINGS:
            continue
        for h in HEADINGS:
            if h in t and len(t) <= len(h) + 15:
                out.append({"unit": i, "elem": units[i].elem, "shape": "heading retyped", "heading": h})
                break
            if h.replace(" ", "") == t.replace(" ", ""):
                out.append({"unit": i, "elem": units[i].elem, "shape": "heading retyped", "heading": h})
                break
    for (i, a), (j, b) in zip(texts, texts[1:]):
        joined = f"{a} {b}"
        if joined in HEADINGS and a not in HEADINGS:
            out.append({"unit": i, "elem": units[i].elem, "shape": "heading split", "heading": joined})
    return out


def parse_defect_table(t: Table):
    try:
        return PARSER.parse(t), None
    except Exception as exc:  # not a defect header, or it fails to parse
        return None, str(exc)[:120]


def has_content(units: list[Unit]) -> bool:
    return any((u.kind == "text" and u.text.strip()) or u.kind == "tbl" or u.blips or u.objects for u in units)


def rule_b(units: list[Unit], front_end: int, cond: int, visum: int | None, station: str,
           master_cbm: int | None) -> dict:
    """Variant: cut the CBM region at each defect table, not at each page break.

    Rests on the owner's rule that one CBM defect fills exactly one page and no page holds
    two. Between two defect tables, the cut goes at the last page break if there is one,
    otherwise at the start of the second table.
    """
    out: dict = {"failures": []}
    defects: list[int] = []
    for i in range(front_end + 1, cond):
        u = units[i]
        if u.kind == "tbl":
            meta, _ = parse_defect_table(u.table)
            if meta is not None:
                defects.append(i)

    def last_break(lo: int, hi: int) -> int | None:
        for j in range(hi - 1, lo, -1):
            if units[j].kind == "break":
                return j
        return None

    def cut_before(prev_end: int, table_idx: int) -> tuple[int, int]:
        """(end of the previous piece, start of the piece holding table_idx)."""
        b = last_break(prev_end, table_idx)
        return (b, b + 1) if b is not None else (table_idx, table_idx)

    cbm: list[list] = []
    if defects:
        summary_end, start = cut_before(front_end, defects[0])
    else:
        summary_end = last_break(front_end, cond) or cond
        start = None
    for k, d in enumerate(defects):
        if k + 1 < len(defects):
            end, nxt = cut_before(d, defects[k + 1])
        else:
            b = last_break(d, cond)
            end, nxt = (b if b is not None else cond), None
        meta, _ = parse_defect_table(units[d].table)
        span = units[start:end]
        others = sum(1 for u in span if u.kind == "tbl") - 1
        loose_images = sum(u.blips + u.objects for u in span if u.kind == "text")
        ok = bool(verify_cbm_defect_attribution(meta, station)) if station else True
        if not ok:
            out["failures"].append({"shape": "other", "detail": "CBM header names another substation"})
        if others or loose_images:
            out.setdefault("notes", []).append(
                f"CBM piece {k}: {others} other table(s), {loose_images} image(s) outside tables")
        cbm.append([start, end, meta.filename])
        start = nxt

    # The summary area runs from the front page to the first CBM piece. It may hold only
    # the summaries; anything else would be a page the structural rule can't place.
    summary_units = units[front_end + 1:summary_end]
    stray_tables = [u for u in summary_units if u.kind == "tbl" and not norm(
        "".join(u.table.cell(0, 0).text.split()) if u.table.rows else "").startswith("NO")]
    if stray_tables:
        out["failures"].append({"shape": "other", "detail": f"{len(stray_tables)} non-summary table(s) in the summary area"})

    out["slices"] = {}
    if visum is not None:
        ends = [next_break(units, visum, cond), cond]
        if defects and defects[0] > visum:
            ends.append(summary_end)
        out["slices"]["vi_summary"] = [visum, min(ends)]
    out["cbm_pieces"] = len(cbm)
    out["cbm_slices"] = cbm
    if master_cbm is None:
        out["count_check"] = "no Master match"
    elif master_cbm == len(cbm):
        out["count_check"] = "match"
    else:
        out["count_check"] = "mismatch"
        out["failures"].append({"shape": "count mismatch", "detail": f"{len(cbm)} CBM pieces, Master has {master_cbm}"})
    return out


@dataclass
class Piece:
    start: int
    end: int  # exclusive
    kind: str = ""
    defect_tables: int = 0
    other_tables: int = 0
    meta: dict = field(default_factory=dict)
    note: str = ""


def derive(path: Path, station: str, master_cbm: int | None) -> dict:
    units, info = read_units(path)
    res: dict = {
        "file": path.name,
        "units": len(units),
        "page_breaks": {
            k: sum(1 for u in units if u.kind == "break" and u.break_kind == k)
            for k in ("br", "pageBreakBefore", "sectPr")
        },
        "master_cbm": master_cbm,
        "failures": [],
        "notes": [],
    }
    fail = res["failures"]

    if info["breaks_inside_tables"]:
        fail.append({"shape": "template with a break inside it", "where": info["breaks_inside_tables"]})

    for h in HEADINGS:
        idx = find_heading(units, h)
        if idx is not None and units[idx].w_t_count != 1:
            res["notes"].append(f"heading {h!r} spans {units[idx].w_t_count} w:t")
    misses = near_miss_headings(units)
    if misses:
        res["near_miss_headings"] = misses

    front_end = next_break(units, 0)
    cond = find_heading(units, COND)
    if cond is None:
        fail.append({"shape": "heading split or retyped", "detail": "no SUBSTATION CONDITION"})
        return res
    sticker = find_heading(units, STICKER, cond)
    if sticker is None:
        fail.append({"shape": "heading split or retyped", "detail": "no NORMAL/DEFECT STICKER after condition"})
        return res
    vi = find_heading(units, VI, cond, sticker)
    visum = find_heading(units, VISUM, front_end, cond)
    cbmsum = find_heading(units, CBMSUM, 0, cond)

    if front_end >= cond:
        fail.append({"shape": "deleted page break", "detail": "no page break before SUBSTATION CONDITION"})
    if find_heading(units, HEADINGS, 0, front_end) is not None:
        fail.append({"shape": "deleted page break", "detail": "a slicer heading sits on the front page"})
    res["front_page_lrpb"] = info["lrpb_before_first_break"]

    slices: dict[str, tuple[int, int]] = {"front_page": (0, front_end)}
    if visum is not None:
        slices["vi_summary"] = (visum, next_break(units, visum, cond))
    slices["condition_pages"] = (cond, vi if vi is not None else sticker)
    if vi is not None:
        slices["vi_defect_pages"] = (vi, sticker)
    slices["sticker_page"] = (sticker, len(units))

    # CBM region: every piece between the front page and SUBSTATION CONDITION.
    pieces: list[Piece] = []
    s = front_end + 1
    while s < cond:
        e = next_break(units, s, cond)
        pieces.append(Piece(s, e))
        s = e + 1
    summary_heads = {i for i in (visum, cbmsum) if i is not None}
    cbm_pieces: list[Piece] = []
    for pc in pieces:
        span = units[pc.start:pc.end]
        if any(pc.start <= h < pc.end for h in summary_heads):
            pc.kind = "summary"
        for u in span:
            if u.kind != "tbl":
                continue
            meta, err = parse_defect_table(u.table)
            if meta is None:
                pc.other_tables += 1
                continue
            pc.defect_tables += 1
            if not pc.meta:
                pc.meta = {
                    "file": meta.filename,
                    "substation_ok": bool(verify_cbm_defect_attribution(meta, station)) if station else None,
                }
        if pc.kind == "summary":
            if pc.defect_tables:
                fail.append({"shape": "deleted page break", "detail": "defect table inside a summary piece", "unit": pc.start})
            continue
        if pc.defect_tables == 1:
            pc.kind = "cbm"
            cbm_pieces.append(pc)
            if pc.other_tables:
                res["notes"].append(f"CBM piece at unit {pc.start} also holds {pc.other_tables} other table(s)")
            if pc.meta.get("substation_ok") is False:
                fail.append({"shape": "other", "detail": "CBM header names another substation", "unit": pc.start})
        elif pc.defect_tables > 1:
            pc.kind = "cbm-multi"
            fail.append({"shape": "deleted page break", "detail": f"{pc.defect_tables} defect tables in one piece", "unit": pc.start})
        elif has_content(span):
            pc.kind = "unclassified"
            fail.append({"shape": "other", "detail": "piece with content but no defect table", "unit": pc.start,
                         "tables": pc.other_tables})
        else:
            pc.kind = "empty"
            res["notes"].append(f"empty piece at unit {pc.start} (an added page break)")

    res["b"] = rule_b(units, front_end, cond, visum, station, master_cbm)

    # Which tables carry a page break inside them, and are they defect tables?
    if info["breaks_inside_tables"]:
        for u in units:
            if u.kind == "tbl" and any(w["elem"] == u.elem for w in info["breaks_inside_tables"]):
                meta, _ = parse_defect_table(u.table)
                for w in info["breaks_inside_tables"]:
                    if w["elem"] == u.elem:
                        w["defect_table"] = meta.filename if meta else None

    # Defect tables outside the CBM region would be missed by the structural rule.
    stray = 0
    for i, u in enumerate(units):
        if u.kind == "tbl" and not (front_end < i < cond):
            if parse_defect_table(u.table)[0] is not None:
                stray += 1
    if stray:
        fail.append({"shape": "other", "detail": f"{stray} defect table(s) outside the CBM region"})

    res["cbm_pieces"] = len(cbm_pieces)
    res["piece_kinds"] = [p.kind for p in pieces]
    if master_cbm is None:
        res["count_check"] = "no Master match"
    elif master_cbm == len(cbm_pieces):
        res["count_check"] = "match"
    else:
        res["count_check"] = "mismatch"
        fail.append({"shape": "count mismatch", "detail": f"{len(cbm_pieces)} CBM pieces, Master has {master_cbm}"})

    res["slices"] = {k: list(v) for k, v in slices.items()}
    res["cbm_slices"] = [[p.start, p.end, p.meta.get("file", "")] for p in cbm_pieces]
    res["_units"] = units  # dropped before writing JSON
    return res


# ---------------------------------------------------------------------------
# Fingerprints, for comparing a prototype slice with a COM slice without storing content.
# ---------------------------------------------------------------------------


def fingerprint_units(units: list[Unit], front: bool = False) -> dict:
    text = "".join(u.text for u in units if u.kind in ("text", "tbl"))
    if front:
        text = text.replace("QUICK SCANNING REPORT", "FULL SCANNING REPORT")
    text = "".join(text.split())
    return {
        "chars": len(text),
        "sha": hashlib.sha256(text.encode()).hexdigest()[:16],
        "tables": sum(1 for u in units if u.kind == "tbl"),
        "images": sum(u.blips for u in units),
        "objects": sum(u.objects for u in units),
        "_text": text,
    }


def fingerprint_file(path: Path) -> dict:
    units, _ = read_units(path)
    return fingerprint_units([u for u in units if u.kind != "break"])


def first_diff(a: str, b: str) -> int:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def compare_with_com(qr: Path, res: dict, station: str, vi_count: int, out: Path) -> dict:
    from src.full_report.slicer import WordComDocumentSlicer

    work = out / "com" / qr.stem
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    copy = work / "source.docx"
    shutil.copy2(qr, copy)
    target = work / "sliced"
    t0 = time.perf_counter()
    try:
        sliced = WordComDocumentSlicer().slice_sections(
            source_path=copy,
            target_dir=target,
            station=station,
            has_vi_summary=True,
            has_vi_defects=True,
            expected_vi_defect_count=vi_count,
        )
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    secs = round(time.perf_counter() - t0, 1)

    units = res["_units"]
    cmp: dict = {"com_seconds": secs, "sections": {}, "cbm": {}}
    for name, (s, e) in res["slices"].items():
        com_path = getattr(sliced, name)
        mine = fingerprint_units([u for u in units[s:e] if u.kind != "break"], front=(name == "front_page"))
        if com_path is None:
            cmp["sections"][name] = {"com": None, "xml": {k: v for k, v in mine.items() if k != "_text"}}
            continue
        theirs = fingerprint_file(Path(com_path))
        same = mine["sha"] == theirs["sha"] and all(mine[k] == theirs[k] for k in ("tables", "images", "objects"))
        row = {"same": same}
        if not same:
            row["xml"] = {k: v for k, v in mine.items() if k != "_text"}
            row["com"] = {k: v for k, v in theirs.items() if k != "_text"}
            row["first_diff_at"] = first_diff(mine["_text"], theirs["_text"])
        cmp["sections"][name] = row
    for name in ("vi_summary", "vi_defect_pages"):
        if name not in res["slices"] and getattr(sliced, name) is not None:
            cmp["sections"][name] = {"same": False, "xml": None, "com": "present"}

    com_cbm = [fingerprint_file(Path(p)) for p in sliced.cbm_defect_pages]

    def cbm_compare(cbm_slices) -> dict:
        mine_cbm = {}
        for s, e, _ in cbm_slices:
            fp = fingerprint_units([u for u in units[s:e] if u.kind != "break"])
            mine_cbm[fp["sha"]] = fp
        matched = sum(1 for fp in com_cbm if fp["sha"] in mine_cbm)
        row = {"xml": len(cbm_slices), "com": len(com_cbm), "text_matched": matched}
        if matched != len(com_cbm) or len(com_cbm) != len(cbm_slices):
            row["unmatched_com"] = [
                {k: v for k, v in fp.items() if k != "_text"} for fp in com_cbm if fp["sha"] not in mine_cbm
            ]
            row["unmatched_xml"] = [
                {k: v for k, v in fp.items() if k != "_text"} for sha, fp in mine_cbm.items()
                if sha not in {c["sha"] for c in com_cbm}
            ]
        return row

    cmp["cbm"] = cbm_compare(res["cbm_slices"])
    cmp["b"] = {"cbm": cbm_compare(res["b"]["cbm_slices"])}
    if "vi_summary" in res["b"]["slices"] and sliced.vi_summary is not None:
        s, e = res["b"]["slices"]["vi_summary"]
        mine = fingerprint_units([u for u in units[s:e] if u.kind != "break"])
        theirs = fingerprint_file(Path(sliced.vi_summary))
        cmp["b"]["vi_summary"] = {"same": mine["sha"] == theirs["sha"] and all(
            mine[k] == theirs[k] for k in ("tables", "images", "objects"))}
    return cmp


# ---------------------------------------------------------------------------
# Master counts, from FullReportWorkflow.inspect() (pandas over QR03 CBA, no COM)
# ---------------------------------------------------------------------------


def master_counts(config: dict, log) -> dict[str, dict]:
    from src.project.environment import ProjectEnvironment
    from src.project.models import ProjectMetadata
    from src.project.storage import LocalWorkspaceStorage
    from src.workflows.full_report import FullReportWorkflow
    from src.quick_report.compiler import FakeDocumentCompiler
    from src.quick_report.cbm_defect_planner import CbmDefectPlanner

    out: dict[str, dict] = {}
    for key, p in config["projects"].items():
        meta = ProjectMetadata(
            key=key, name=p["name"], po_number=p["po_number"], state=p["state"], voltage_type=p["type"],
            year=p["year"], cycle=p["cycle"], technologies=tuple(p["technologies"]), base_path=p["base_path"],
        )
        env = ProjectEnvironment(metadata=meta, storage=LocalWorkspaceStorage(Path(p["base_path"])))
        wf = FullReportWorkflow(compiler=FakeDocumentCompiler())
        t0 = time.perf_counter()
        # The same calls FullReportWorkflow._inspect_single_package makes, keeping the records.
        pkgs, _, errors = wf.discover_packages(None, env)
        planner = CbmDefectPlanner()
        for pkg in pkgs:
            try:
                qr = wf._resolve_quick_report_path(env, pkg)
            except Exception:
                continue
            if not qr:
                continue
            cbm, vi = wf._extract_defects_safe(pkg, env)
            try:
                pages = expected_cbm_pages(planner.plan(cbm, env))
            except Exception as exc:
                pages = None
                log(f"  planner failed for {pkg.substation_number}: {type(exc).__name__}")
            out[os.path.normcase(str(Path(qr).resolve()))] = {
                "station": wf._resolve_substation_display_name(pkg),
                "cbm_rows": len(cbm),
                "cbm": pages,
                "vi": len(vi),
            }
        log(f"discover {key}: {len(pkgs)} packages, {len(errors)} errors, {time.perf_counter() - t0:.1f}s")
    return out


def expected_cbm_pages(family_plans) -> int:
    """Pages CbmDefectPageBuilder.build renders: one overview per group, one per detail defect."""
    n = 0
    for fp in family_plans:
        roles_with_template = {rid for rid, path in fp.detail_templates if Path(path).exists()}
        for g in fp.groups:
            n += 1
            for dg in g.detail_groups:
                if dg.role_id in roles_with_template:
                    n += len(dg.defects)
    return n


# ---------------------------------------------------------------------------
# Read-only guard
# ---------------------------------------------------------------------------


def snapshot(roots: list[Path]) -> dict[str, tuple[int, int]]:
    snap = {}
    for r in roots:
        for dp, _, files in os.walk(r):
            for f in files:
                fp = os.path.join(dp, f)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                snap[fp] = (st.st_size, st.st_mtime_ns)
    return snap


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--com", action="store_true", help="also run the COM slicer on the five benchmarks")
    ap.add_argument("--write-evidence", action="store_true")
    ap.add_argument("--com-extra", nargs="*", default=[], metavar="KEY=PREFIX",
                    help="more reports for the COM comparison, by file name prefix")
    ap.add_argument("--reuse-masters", action="store_true", help="reuse masters.json from --out")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    logf = open(args.out / "run.log", "w", encoding="utf-8")

    def log(msg: str) -> None:
        print(msg)
        logf.write(msg + "\n")
        logf.flush()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    bases = {k: Path(p["base_path"]) for k, p in config["projects"].items()}
    before = snapshot(list(bases.values()))
    log(f"snapshot: {len(before)} files under {len(bases)} project folders")

    cache = args.out / "masters.json"
    if args.reuse_masters and cache.exists():
        masters = json.loads(cache.read_text(encoding="utf-8"))
        log(f"masters: {len(masters)} reused from an earlier run")
    else:
        masters = master_counts(config, log)
        cache.write_text(json.dumps(masters), encoding="utf-8")

    reports: list[tuple[str, Path]] = []
    for key, base in bases.items():
        for dp, _, files in os.walk(base / "QUICK REPORT"):
            for f in sorted(files):
                if f.lower().endswith(".docx") and not f.startswith("~$"):
                    reports.append((key, Path(dp) / f))
    log(f"quick reports: {len(reports)}")

    results = []
    live_rows = []
    for key, qr in reports:
        m = masters.get(os.path.normcase(str(qr.resolve())))
        station = m["station"] if m else ""
        try:
            res = derive(qr, station, m["cbm"] if m else None)
        except Exception as exc:
            res = {"file": qr.name, "failures": [{"shape": "unreadable", "detail": f"{type(exc).__name__}: {exc}"[:200]}]}
        res["project"] = key
        res["path"] = "<BASE>/" + qr.relative_to(bases[key]).as_posix()
        res["vi_master"] = m["vi"] if m else None
        res["master_cbm_rows"] = m["cbm_rows"] if m else None
        res["station"] = station
        results.append(res)
        st = qr.stat()
        live_rows.append([key, res["path"], st.st_size, sha256(qr), date.today().isoformat()])

    com_results = {}
    if args.com:
        targets = dict(BENCHMARKS)
        targets.update(dict(x.split("=", 1) for x in args.com_extra))
        for bkey, prefix in targets.items():
            cands = [r for r in results if r["file"].startswith(prefix) and "/New folder/" not in r["path"]]
            if not cands:
                com_results[bkey] = {"error": "report not found"}
                continue
            r = cands[0]
            qr = bases[r["project"]] / r["path"].removeprefix("<BASE>/")
            if "_units" not in r:
                com_results[bkey] = {"error": "prototype could not derive bounds", "path": r["path"]}
                continue
            log(f"COM slicing {bkey}: {r['path']}")
            com_results[bkey] = {"path": r["path"], **compare_with_com(qr, r, r["station"], r["vi_master"] or 0, args.out)}

    after = snapshot(list(bases.values()))
    changed = [p for p in set(before) | set(after) if before.get(p) != after.get(p)]
    log(f"read-only guard: {len(changed)} files changed under project folders")
    for p in changed[:20]:
        for base in bases.values():
            if p.startswith(str(base)):
                p = "<BASE>/" + Path(p).relative_to(base).as_posix()
        log(f"  changed: {p}")

    for r in results:
        r.pop("_units", None)

    # Why the rule B count mismatches happen: the Master has no CBM rows, or the report holds
    # extra overview views (OVERVIEW_TOP, _REAR, _LHS ...) that the generator never names.
    def suffixed(name: str) -> bool:
        return bool(re.search(r"_OVERVIEW_[A-Z]", name))

    b_rows = [r for r in results if "b" in r and r["b"]["count_check"] in ("match", "mismatch")]
    mismatch_causes = {"master_has_no_cbm_rows": 0, "report_has_more_pages": 0, "report_has_fewer_pages": 0}
    suffixed_stats = {}
    for label in ("match", "mismatch"):
        rs = [r for r in b_rows if r["b"]["count_check"] == label]
        names = [c[2] for r in rs for c in r["b"]["cbm_slices"]]
        suffixed_stats[label] = {
            "reports": len(rs), "cbm_pages": len(names),
            "suffixed_overview_pages": sum(map(suffixed, names)),
            "reports_with_one": sum(1 for r in rs if any(suffixed(c[2]) for c in r["b"]["cbm_slices"])),
        }
    for r in b_rows:
        if r["b"]["count_check"] != "mismatch":
            continue
        if r["master_cbm"] == 0 and r["master_cbm_rows"] == 0:
            mismatch_causes["master_has_no_cbm_rows"] += 1
        elif r["b"]["cbm_pieces"] > r["master_cbm"]:
            mismatch_causes["report_has_more_pages"] += 1
        else:
            mismatch_causes["report_has_fewer_pages"] += 1
    passed = [r for r in results if not r["failures"] and r.get("count_check") == "match"]
    no_master = [r for r in results if not r["failures"] and r.get("count_check") == "no Master match"]
    failed = [r for r in results if r["failures"]]
    shapes: dict[str, int] = {}
    for r in failed:
        for f in r["failures"]:
            shapes[f["shape"]] = shapes.get(f["shape"], 0) + 1
    b_passed = [r for r in results if "b" in r and not [f for f in r["failures"] if f["shape"] in (
        "heading split or retyped", "unreadable")] and not r["b"]["failures"] and r["b"]["count_check"] == "match"]
    b_failed = [r for r in results if "b" not in r or r["b"]["failures"]]
    b_shapes: dict[str, int] = {}
    for r in b_failed:
        for f in (r["b"]["failures"] if "b" in r else r["failures"]):
            b_shapes[f["shape"]] = b_shapes.get(f["shape"], 0) + 1
    summary = {
        "rule_b_passed_every_check": len(b_passed),
        "rule_b_failed": len(b_failed),
        "rule_b_failure_shapes": b_shapes,
        "reports": len(results),
        "passed_every_check": len(passed),
        "structure_ok_no_master_match": len(no_master),
        "failed": len(failed),
        "failure_shapes": shapes,
        "front_page_lrpb_nonzero": sum(1 for r in results if r.get("front_page_lrpb")),
        "read_only_changed_files": len(changed),
        "rule_b_mismatch_causes": mismatch_causes,
        "rule_b_suffixed_overview_pages": suffixed_stats,
    }
    log(json.dumps(summary, indent=2))
    for name, obj in (("results.json", results), ("com_compare.json", com_results), ("summary.json", summary)):
        (args.out / name).write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    with open(args.out / "live_data_read.tsv", "w", encoding="utf-8") as fh:
        fh.write("project\tpath\tbytes\tsha256\tread_on\n")
        for row in live_rows:
            fh.write("\t".join(map(str, row)) + "\n")
    if args.write_evidence:
        # The committed copy names each CBM page by kind, not by its D37 file name, which
        # carries equipment and feeder ids from the client's headers.
        def kind(name: str | None) -> str | None:
            if name is None:
                return None
            return "overview-suffixed" if suffixed(name) else ("overview" if "_OVERVIEW" in name else "detail")

        for r in results:
            r["cbm_slices"] = [[a, b, kind(n)] for a, b, n in r.get("cbm_slices", [])]
            if "b" in r:
                r["b"]["cbm_slices"] = [[a, b, kind(n)] for a, b, n in r["b"]["cbm_slices"]]
            for f in r.get("failures", []):
                for w in f.get("where", []) if isinstance(f.get("where"), list) else []:
                    if "defect_table" in w:
                        w["defect_table"] = kind(w["defect_table"])
        here = Path(__file__).parent
        (here / "results.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
        for name in ("com_compare.json", "summary.json", "live_data_read.tsv", "run.log"):
            shutil.copy2(args.out / name, here / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
