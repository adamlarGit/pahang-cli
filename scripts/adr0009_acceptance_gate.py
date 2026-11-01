"""ADR 0009 live acceptance gate (ticket #149).

Drives the production "Post-Process Full Reports" action (`postprocess_full_reports_action`) on real data, with
three harness-only differences that leave the conversion path itself untouched:

* the interactive selectors are answered automatically (dataset filter, "proceed" = yes);
* deliverables are redirected to a scratch folder via `FullReportPostProcessingWorkflow.process(output_dir=...)`,
  so operator-owned PDFs under the project are never written (ADR 0010);
* `restore_source_images` is wrapped to keep copies of each part's native export and restored PDF, and the
  converter is wrapped to time the export and count pages. Both wrappers delegate unchanged.

Subcommands:
    run      run the action for one dataset from a given repo checkout (BEFORE = throwaway checkout, AFTER = main tree)
    analyze  verify a finished run (layout invariance, image fidelity, merge, audio, idempotence)
    compare  compare page counts of two runs

Scope and limits:
* DATASETS and `_select` are pinned to the dated 2026 data named in ticket #149 (11kV Cameron Highland 17-08-2026
  reports 093-102; 33kV GEBENG 07-10-2026 "01. PPU APMM 3311kV"). Re-point them to gate other data.
* Word PID and memory figures come from `tasklist` sampled every 3 s, so they undercount short-lived processes and
  peak memory. Word recycles are counted exactly (a wrapper counter on `BatchComSession.restart_word`), not from PIDs.
* Only Word processes that appear during the run count as orphans; a Word the operator already had open is ignored.
* Any Word owner file (`~$*`) seen in the source folder during the run (polled every second) is recorded.
* The image-fidelity comparison is a rendered 100 dpi pixel diff per restored placement, not a per-image visual pass.

Usage (from any directory, with the project's .venv python):
    python scripts/adr0009_acceptance_gate.py run --repo <checkout> --label before --dataset 11kv --scratch <dir>
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

DATASETS = {
    "11kv": {
        "project": "ktn_rau_chl_2026_3",
        "target": ("FULL REPORT", "CAMERON HIGHLAND", "01. AUGUST", "17-08-2026"),
    },
    "33kv": {
        "project": "thunder_cycle_4_2026_4",
        "target": ("FULL REPORT", "GEBENG", "01. OCTOBER", "07-10-2026"),
    },
}


def _select(dataset: str, stem: str) -> bool:
    if dataset == "11kv":
        m = re.match(r"^(\d+)\.", stem)
        return bool(m) and 93 <= int(m.group(1)) <= 102
    return stem == "01. PPU APMM 3311kV"


# --------------------------------------------------------------------------- process memory


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _pmc() -> _PMC:
    k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(pmc)
    if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return pmc


def _own_peak_mb() -> float:
    return _pmc().PeakWorkingSetSize / 1048576


def _own_now_mb() -> float:
    return _pmc().WorkingSetSize / 1048576


def _word_procs() -> list[tuple[int, float]]:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"], capture_output=True, text=True
    ).stdout
    procs = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 5 and parts[0].strip('"').upper() == "WINWORD.EXE":
            kb = int(re.sub(r"[^\d]", "", parts[4]) or 0)
            procs.append((int(parts[1]), kb / 1024))
    return procs


class _WordSampler(threading.Thread):
    def __init__(self, watch_dir: Path | None = None) -> None:
        super().__init__(daemon=True)
        self.watch_dir = watch_dir
        self.lock_files_seen: set[str] = set()
        self.stop = threading.Event()
        self.peak_word_mb = 0.0
        self.pids: set[int] = set()
        self.peak_count = 0

    def run(self) -> None:
        tick = 0
        while not self.stop.wait(1.0):
            tick += 1
            if self.watch_dir is not None:
                try:
                    self.lock_files_seen.update(p.name for p in self.watch_dir.glob("~$*"))
                except OSError:
                    pass
            if tick % 3:
                continue
            try:
                procs = _word_procs()
            except Exception:
                continue
            self.pids.update(p for p, _ in procs)
            self.peak_count = max(self.peak_count, len(procs))
            for _, mb in procs:
                self.peak_word_mb = max(self.peak_word_mb, mb)


# --------------------------------------------------------------------------- run


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_state(repo: Path) -> dict:
    def git(*a: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout

    return {
        "head": git("rev-parse", "HEAD").strip(),
        "dirty": bool(git("status", "--porcelain").strip()),
        "status_porcelain": git("status", "--porcelain").splitlines(),
        "diff_head_sha256": hashlib.sha256(git("diff", "HEAD").encode("utf-8", "replace")).hexdigest(),
    }


def _import_guard(repo: Path) -> None:
    import src  # noqa: E402

    if Path(src.__file__).resolve().parent != repo / "src":
        raise SystemExit(f"Wrong src imported: {src.__file__} (expected under {repo})")


def cmd_run(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    _import_guard(repo)

    ds = DATASETS[args.dataset]
    work = Path(args.scratch).resolve() / args.label / args.dataset
    out_dir = Path(args.shared_out).resolve() if args.shared_out else work / "out"
    native_dir = work / "parts_native"
    restored_dir = work / "parts_restored"
    for d in (native_dir, restored_dir):
        d.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    from src import cli_selectors
    from src.postprocessing import converters as conv_mod
    from src.postprocessing import image_restoration as ir_mod
    from src.project.environment import create_project_environment
    from src.project_workflow_actions import postprocess_full_reports_action
    from src.workflows.full_report_postprocessing import FullReportPostProcessingWorkflow

    import fitz

    env = create_project_environment(ds["project"])
    target = Path(env.base_path, *ds["target"])
    if not target.is_dir():
        raise SystemExit(f"Target folder missing: {target}")
    if work in target.parents or out_dir == target:
        raise SystemExit("Scratch must not be inside the project target")

    # snapshot inputs so we can prove the run never touched them
    docx_inputs = sorted(target.glob("*.docx"))
    inputs_before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in docx_inputs}

    parts_log: list[dict] = []
    state = {"cur": None, "n": 0}

    # --- wrappers (delegate unchanged) ------------------------------------------------------------------------
    real_restore = ir_mod.restore_source_images
    recycles = {"n": 0}
    real_restart = conv_mod.BatchComSession.restart_word

    def counting_restart(self, *a, **k):
        recycles["n"] += 1
        return real_restart(self, *a, **k)

    conv_mod.BatchComSession.restart_word = counting_restart

    def restore_wrapper(docx_bytes, native_pdf, output_pdf):
        entry = state["cur"]
        idx = entry["idx"]
        shutil.copyfile(native_pdf, native_dir / f"{idx:03d}.pdf")
        with fitz.open(native_pdf) as d:
            entry["native_pages"] = d.page_count
        entry["docx_bytes_sha"] = hashlib.sha256(docx_bytes).hexdigest()[:16]
        t0 = time.perf_counter()
        try:
            report = real_restore(docx_bytes, native_pdf, output_pdf)
        finally:
            entry["restore_wall_s"] = time.perf_counter() - t0
        shutil.copyfile(output_pdf, restored_dir / f"{idx:03d}.pdf")
        entry["peak_mb_after_restore"] = _own_peak_mb()
        entry["restore_report"] = {
            "images_total": report.images_total,
            "restored": report.restored,
            "unmatched": report.unmatched,
            "ambiguous": report.ambiguous,
            "self_check_rejected": report.self_check_rejected,
            "elapsed_s": report.elapsed_s,
            "entries": [
                {"page": e.page, "xref": e.xref, "pdf_size": list(e.pdf_size), "source": e.source, "action": e.action}
                for e in report.entries
            ],
        }
        return report

    ir_mod.restore_source_images = restore_wrapper

    class GateConverter(conv_mod.ComDocumentConverter):
        def _export_fixed_format(self, doc, pdf_path):
            t0 = time.perf_counter()
            try:
                super()._export_fixed_format(doc, pdf_path)
            finally:
                state["cur"]["export_s"] = state["cur"].get("export_s", 0.0) + time.perf_counter() - t0
                state["cur"]["export_calls"] = state["cur"].get("export_calls", 0) + 1

        def convert_docx_to_pdf(self, docx_path, pdf_path, *a, **kw):
            state["n"] += 1
            entry = {"idx": state["n"], "docx": Path(docx_path).name, "docx_bytes": Path(docx_path).stat().st_size}
            state["cur"] = entry
            parts_log.append(entry)
            t0 = time.perf_counter()
            try:
                return super().convert_docx_to_pdf(docx_path, pdf_path, *a, **kw)
            finally:
                entry["convert_wall_s"] = time.perf_counter() - t0
                try:
                    with fitz.open(pdf_path) as d:
                        entry["final_pages"] = d.page_count
                        entry["final_bytes"] = Path(pdf_path).stat().st_size
                except Exception as exc:
                    entry["final_pages"] = None
                    entry["final_error"] = str(exc)
                lc = getattr(self, "last_conversion", None)
                if lc is not None:
                    entry["fell_back"] = lc.fell_back
                    entry["warning"] = lc.warning

    class GateWorkflow(FullReportPostProcessingWorkflow):
        def process(self, target, environment, **kw):
            kw["output_dir"] = out_dir
            return super().process(target, environment, **kw)

    # --- automatic answers to the interactive selectors ---------------------------------------------------------
    chosen_meta: list[str] = []

    def auto_select(targets, **kwargs):
        picked = [t for t in targets if _select(args.dataset, t.stem) and (not args.only or args.only in t.stem)]
        chosen_meta.extend(t.stem for t in picked)
        return picked

    cli_selectors.select_substations_interactive = auto_select
    cli_selectors.confirm = lambda *a, **k: True

    workflow = GateWorkflow(converter=GateConverter())
    word_before = {pid for pid, _ in _word_procs()}
    locks_before = sorted(p.name for p in target.glob("~$*"))
    sampler = _WordSampler(watch_dir=target)
    sampler.start()
    t_start = time.perf_counter()
    buf = io.StringIO()

    class Tee(io.TextIOBase):
        def write(self, s):
            buf.write(s)
            sys.__stdout__.write(s)
            return len(s)

        def flush(self):
            sys.__stdout__.flush()

    result = None
    error = None
    try:
        with contextlib.redirect_stdout(Tee()):
            result = postprocess_full_reports_action(env, workflow=workflow, target=target)
    except BaseException as exc:  # recorded below, then re-raised
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        wall = time.perf_counter() - t_start
        sampler.stop.set()
        # Word may still be shutting down when the action returns; only Word PIDs new to this run count as orphans
        t_end = time.perf_counter()
        new_at_return = [(p, mb) for p, mb in _word_procs() if p not in word_before]
        while any(p not in word_before for p, _ in _word_procs()) and time.perf_counter() - t_end < 60:
            time.sleep(1)
        orphan_linger_s = time.perf_counter() - t_end
        if error is not None:
            (work / "run.json").write_text(
                json.dumps(
                    {
                        "label": args.label,
                        "dataset": args.dataset,
                        "error": error,
                        "wall_s": wall,
                        "git": _git_state(repo),
                        "parts": parts_log,
                        "word_recycles": recycles["n"],
                        "lock_files_seen_in_source": sorted(sampler.lock_files_seen),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (work / "run_stdout.txt").write_text(buf.getvalue(), encoding="utf-8")

    reports = []
    if result is not None:
        for t in result.telemetries:
            reports.append(
                {
                    "stem": t.stem,
                    "parts": len(t.part_docx_paths),
                    "target_pdf": str(t.target_pdf_path),
                    "restored": t.images_restored,
                    "unmatched": t.images_unmatched,
                    "ambiguous": t.images_ambiguous,
                    "fallbacks": t.fallback_count,
                    "banner": t.restoration_banner,
                    "testsheet_pdf": str(t.testsheet_pdf_path) if t.testsheet_pdf_path else None,
                }
            )
    inputs_after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(target.glob("*.docx"))}
    leftovers = [str(p) for p in out_dir.rglob(".tmp*")] + [str(p) for p in out_dir.rglob("*.tmp")]
    summary = {
        "label": args.label,
        "dataset": args.dataset,
        "repo": str(repo),
        "head": _git_state(repo)["head"],
        "git": _git_state(repo),
        "word_recycles": recycles["n"],
        "lock_files_seen_in_source": sorted(sampler.lock_files_seen),
        "lock_files_before": locks_before,
        "lock_files_after": sorted(p.name for p in target.glob("~$*")),
        "out_dir": str(out_dir),
        "wall_s": wall,
        "python_peak_ws_mb": _own_peak_mb(),
        "python_end_ws_mb": _own_now_mb(),
        "word_peak_ws_mb_sampled": sampler.peak_word_mb,
        "word_pids_seen": sorted(sampler.pids),
        "word_max_concurrent": sampler.peak_count,
        "word_new_alive_at_action_return": new_at_return,
        "word_linger_after_return_s": round(orphan_linger_s, 1),
        "orphan_word_after_run": [(p, mb) for p, mb in _word_procs() if p not in word_before],
        "word_preexisting_pids_ignored": sorted(word_before),
        "tmp_leftovers_in_out": leftovers,
        "inputs_unchanged": inputs_before == inputs_after,
        "selected": chosen_meta,
        "result": None
        if result is None
        else {
            "total": result.total_reports,
            "succeeded": result.succeeded_count,
            "failed": result.failed_count,
            "duration_s": result.duration_seconds,
            "warnings": list(result.warnings),
            "errors": list(result.errors),
            "deliverables": [str(p) for p in result.deliverables],
        },
        "reports": reports,
        "parts": parts_log,
    }
    (work / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (work / "run_stdout.txt").write_text(buf.getvalue(), encoding="utf-8")
    print(f"\n[GATE] run.json -> {work / 'run.json'}")
    return 0 if result is not None and result.failed_count == 0 else 1


# --------------------------------------------------------------------------- analyze


def _norm_links(page):
    return [
        (lk.get("kind"), tuple(round(v, 2) for v in lk["from"]), lk.get("uri"), lk.get("page"))
        for lk in page.get_links()
    ]


def _img_sizes(doc) -> dict[int, tuple[int, int]]:
    sizes = {}
    for pno in range(doc.page_count):
        for it in doc[pno].get_images(full=True):
            sizes[it[0]] = (it[2], it[3])
    return sizes


def _sound_annots(doc):
    """(page, rect) of every Sound annotation, read from the raw annotation dictionaries."""
    out = []
    for pno in range(doc.page_count):
        page = doc[pno]
        annots = page.annots()
        if not annots:
            continue
        for a in annots:
            xref = a.xref
            sub = doc.xref_get_key(xref, "Subtype")[1]
            if "Sound" in sub or doc.xref_get_key(xref, "Sound")[0] != "null":
                out.append((pno, tuple(a.rect)))
    return out


def cmd_analyze(args: argparse.Namespace) -> int:
    import fitz
    from PIL import Image, ImageChops

    repo = Path(args.repo).resolve()
    sys.path.insert(0, str(repo))
    _import_guard(repo)
    from src.postprocessing.image_restoration import harvest_sources
    from src.project.environment import create_project_environment

    target = Path(create_project_environment(DATASETS[args.dataset]["project"]).base_path, *DATASETS[args.dataset]["target"])
    work = Path(args.scratch).resolve() / args.label / args.dataset
    run = json.loads((work / "run.json").read_text(encoding="utf-8"))
    native_dir, restored_dir = work / "parts_native", work / "parts_restored"
    report: dict = {"parts": [], "deliverables": []}
    worst_overall = 0.0

    for part in run["parts"]:
        idx = part["idx"]
        n_path, r_path = native_dir / f"{idx:03d}.pdf", restored_dir / f"{idx:03d}.pdf"
        rec = {"idx": idx, "docx": part["docx"], "native_pages": None, "restored_pages": None}
        if not n_path.exists() or not r_path.exists():
            rec["note"] = "no restoration pair (fallback or failure)"
            report["parts"].append(rec)
            continue
        nd, rd = fitz.open(n_path), fitz.open(r_path)
        rec["native_pages"], rec["restored_pages"] = nd.page_count, rd.page_count
        if nd.page_count != rd.page_count:
            rec.update(
                text_identical=False,
                links_identical=False,
                placement_identical=False,
                note="page count differs between native and restored; per-page checks skipped",
            )
            report["parts"].append(rec)
            continue
        text_ok = links_ok = place_ok = True
        for p in range(nd.page_count):
            if nd[p].get_text() != rd[p].get_text():
                text_ok = False
            if _norm_links(nd[p]) != _norm_links(rd[p]):
                links_ok = False
            a = [(tuple(round(v, 2) for v in i["bbox"])) for i in nd[p].get_image_info()]
            b = [(tuple(round(v, 2) for v in i["bbox"])) for i in rd[p].get_image_info()]
            if a != b:
                place_ok = False
        rec.update(text_identical=text_ok, links_identical=links_ok, placement_identical=place_ok)

        # source-pixel + wrong-source check, per restored entry. garbage=3 renumbers xrefs on save, so a restored
        # image is found by placement (identical bbox on the same page) and compared as rendered at 100 dpi.
        restored_entries = [e for e in part["restore_report"]["entries"] if e["action"] == "restored"]
        bigger = 0
        worst_diff = 0.0
        strong_max = 0.0
        worst_where = None
        r_sizes = {}
        src_sizes: dict[str, set] = {}  # labels repeat when one file is cropped differently, so keep every size
        for src_ in harvest_sources((target / part["docx"]).read_bytes()):
            src_sizes.setdefault(src_.label, set()).add(tuple(src_.size))
        size_mismatch = []
        for e in restored_entries:
            pno, x = e["page"] - 1, e["xref"]
            n_info = [i for i in nd[pno].get_image_info(xrefs=True) if i["xref"] == x]
            if not n_info:
                rec.setdefault("compare_errors", []).append(f"native xref {x} not placed on page {e['page']}")
                continue
            for ni_ in n_info:
                bbox = tuple(round(v, 2) for v in ni_["bbox"])
                r_info = [i for i in rd[pno].get_image_info(xrefs=True) if tuple(round(v, 2) for v in i["bbox"]) == bbox]
                if not r_info:
                    rec.setdefault("compare_errors", []).append(f"no restored placement at {bbox} p{e['page']}")
                    continue
                n_px, r_px = ni_["width"] * ni_["height"], r_info[0]["width"] * r_info[0]["height"]
                r_sizes[(pno, x)] = (r_info[0]["width"], r_info[0]["height"])
                want = src_sizes.get(e["source"])
                if want is not None and r_sizes[(pno, x)] not in want:
                    size_mismatch.append((e["page"], e["source"], sorted(want), r_sizes[(pno, x)]))
                if r_px > n_px * 1.001:
                    bigger += 1
                clip = fitz.Rect(bbox)
                if clip.width < 2 or clip.height < 2:
                    rec["size_check_skipped"] = rec.get("size_check_skipped", 0) + 1
                    continue
                pa = nd[pno].get_pixmap(dpi=100, clip=clip, alpha=False)
                pb = rd[pno].get_pixmap(dpi=100, clip=clip, alpha=False)
                ia = Image.frombytes("RGB", (pa.width, pa.height), pa.samples).convert("L")
                ib = Image.frombytes("RGB", (pb.width, pb.height), pb.samples).convert("L")
                hist = ImageChops.difference(ia, ib).histogram()
                total = sum(hist)
                mean = sum(i * c for i, c in enumerate(hist)) / total
                strong = 100.0 * sum(hist[48:]) / total
                if strong >= strong_max:
                    worst_where = {"page": e["page"], "bbox": bbox, "source": e["source"]}
                worst_diff = max(worst_diff, mean)
                strong_max = max(strong_max, strong)
                break
        rec.update(
            restored=len(restored_entries),
            restored_larger_than_native=bigger,
            source_dimension_mismatches=size_mismatch,
            worst_mean_grey_diff=round(worst_diff, 3),
            worst_strong_pct=round(strong_max, 3),
            worst_where=worst_where,
            restore_counts={k: part["restore_report"][k] for k in ("images_total", "restored", "unmatched", "ambiguous", "self_check_rejected")},
        )
        worst_overall = max(worst_overall, strong_max)
        rec["restored_sizes"] = sorted(set(r_sizes.values()), reverse=True)[:6]
        report["parts"].append(rec)
        nd.close()
        rd.close()

    # deliverables: page counts, merge preservation, audio
    parts_by_stem: dict[str, list[dict]] = {}
    # map parts to reports by order of the run
    cursor = 0
    for rep in run["reports"]:
        parts_by_stem[rep["stem"]] = run["parts"][cursor : cursor + rep["parts"]]
        cursor += rep["parts"]

    for rep in run["reports"]:
        pdf = Path(rep["target_pdf"])
        rec = {"stem": rep["stem"], "parts": rep["parts"], "restored": rep["restored"], "unmatched": rep["unmatched"],
               "ambiguous": rep["ambiguous"], "fallbacks": rep["fallbacks"]}
        if not pdf.exists():
            rec["error"] = "deliverable missing"
            report["deliverables"].append(rec)
            continue
        d = fitz.open(pdf)
        ts = Path(rep["testsheet_pdf"]) if rep["testsheet_pdf"] else None
        ts_pages = fitz.open(ts).page_count if ts and ts.exists() else None
        part_pages = [p.get("final_pages") for p in parts_by_stem[rep["stem"]]]
        rec.update(
            pages=d.page_count,
            bytes=pdf.stat().st_size,
            part_pages=part_pages,
            testsheet_pages=ts_pages,
            pages_expected=(sum(part_pages) + (ts_pages or 0)) if all(part_pages) else None,
        )
        native_pages = [p.get("native_pages") for p in parts_by_stem[rep["stem"]]]
        rec["native_part_pages"] = native_pages
        rec["pages_equal_native_plus_testsheet"] = (
            d.page_count == sum(native_pages) + (ts_pages or 0) if all(native_pages) else None
        )
        # merge: every restored image size of every part must still exist in the deliverable (multiset by size)
        deliv_sizes = sorted(_img_sizes(d).values())
        deliv_set = set(deliv_sizes)
        lost = []
        for p in parts_by_stem[rep["stem"]]:
            r_path = restored_dir / f"{p['idx']:03d}.pdf"
            if not r_path.exists():
                continue
            rd = fitz.open(r_path)
            rs = _img_sizes(rd)
            for e in p["restore_report"]["entries"]:
                if e["action"] == "restored" and e["xref"] in rs and tuple(rs[e["xref"]]) not in deliv_set:
                    lost.append((p["idx"], e["xref"], rs[e["xref"]]))
            rd.close()
        rec["restored_images_lost_in_merge"] = lost
        # audio: Sound annotations and whether each sits over an image (speaker icon)
        sounds = _sound_annots(d)
        anchored = 0
        for pno, rect in sounds:
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            for info in d[pno].get_image_info():
                b = info["bbox"]
                if b[0] - 2 <= cx <= b[2] + 2 and b[1] - 2 <= cy <= b[3] + 2:
                    anchored += 1
                    break
        rec.update(sound_annotations=len(sounds), sound_anchored_over_image=anchored)
        d.close()
        report["deliverables"].append(rec)

    report["worst_strong_pct_overall"] = worst_overall
    (work / "analysis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


# --------------------------------------------------------------------------- idempotence / compare


def cmd_idempotent(args: argparse.Namespace) -> int:
    """Run restoration again on each kept restored part against its DOCX: expect zero new replacements."""
    repo = Path(args.repo).resolve()
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    from src.postprocessing.image_restoration import restore_source_images
    from src.project.environment import create_project_environment

    ds = DATASETS[args.dataset]
    work = Path(args.scratch).resolve() / args.label / args.dataset
    run = json.loads((work / "run.json").read_text(encoding="utf-8"))
    env = create_project_environment(ds["project"])
    target = Path(env.base_path, *ds["target"])
    tmp = work / "idem"
    tmp.mkdir(exist_ok=True)
    rows = []
    for part in run["parts"]:
        r_path = work / "parts_restored" / f"{part['idx']:03d}.pdf"
        if not r_path.exists():
            continue
        rep = restore_source_images((target / part["docx"]).read_bytes(), r_path, tmp / "again.pdf")
        rows.append({"idx": part["idx"], "restored_again": rep.restored, "ambiguous": rep.ambiguous,
                     "self_check_rejected": rep.self_check_rejected})
    shutil.rmtree(tmp, ignore_errors=True)
    total = sum(r["restored_again"] for r in rows)
    print(json.dumps({"parts": len(rows), "total_new_replacements": total, "rows": rows}, indent=2))
    (work / "idempotence.json").write_text(json.dumps({"total_new_replacements": total, "rows": rows}, indent=2))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    scratch = Path(args.scratch).resolve()
    rows = []
    ok = True
    for ds in ("11kv", "33kv"):
        a = json.loads((scratch / "before" / ds / "analysis.json").read_text())
        b = json.loads((scratch / "after" / ds / "analysis.json").read_text())
        ra = json.loads((scratch / "before" / ds / "run.json").read_text())
        rb = json.loads((scratch / "after" / ds / "run.json").read_text())
        for da, db in zip(a["deliverables"], b["deliverables"]):
            same = da.get("pages") == db.get("pages") and da["part_pages"] == db["part_pages"]
            ok &= same
            rows.append((ds, da["stem"], da.get("pages"), db.get("pages"), da["part_pages"] == db["part_pages"], same))
        for pa, pb in zip(ra["parts"], rb["parts"]):
            ok &= pa.get("final_pages") == pb.get("final_pages")
    for r in rows:
        print(r)
    print("PAGE COUNTS IDENTICAL:", ok)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "analyze", "idempotent", "compare"):
        p = sub.add_parser(name)
        p.add_argument("--scratch", required=True)
        if name != "compare":
            p.add_argument("--label", required=True)
            p.add_argument("--dataset", choices=sorted(DATASETS), required=True)
        if name in ("run", "idempotent", "analyze"):
            p.add_argument("--repo", required=True)
        if name == "run":
            p.add_argument("--only", help="restrict to stems containing this text (quick single-report check)")
            p.add_argument("--shared-out", help="write deliverables here (used to test the run lock)")
    args = ap.parse_args()
    args.scratch = str(Path(args.scratch).resolve())  # before any chdir into the repo
    if getattr(args, "shared_out", None):
        args.shared_out = str(Path(args.shared_out).resolve())
    return {"run": cmd_run, "analyze": cmd_analyze, "idempotent": cmd_idempotent, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
