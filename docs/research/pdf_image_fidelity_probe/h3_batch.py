"""H3: batch probe over every part of a multi-part report (one shared private Word instance).

For each part: native export -> restore -> invariance checks (text, links, annots, per-page image rects).
Then merge all restored parts with the production merge_pdfs_batch and check survival.
Usage: python -I h3_batch.py <repo> <workdir-with-src-parts> <glob>
"""
import gc, glob, os, sys, time
from pathlib import Path

repo, work, pattern = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(repo)); sys.path.insert(0, str(Path(__file__).parent))
import ctypes, ctypes.wintypes as wt
import fitz, pythoncom
import win32com.client as win32
import h2_swap as H

class _PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t),
                ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def peak_ws():
    pmc = _PMC(); pmc.cb = ctypes.sizeof(pmc)
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.PeakWorkingSetSize
out = work / "out"; out.mkdir(exist_ok=True)
parts = sorted(Path(p) for p in glob.glob(str(work / "src" / pattern)))
print(f"{len(parts)} parts")


def fingerprint(path):
    """Page-level invariants that must not change: content bytes, text, links, annots, drawn image placements."""
    d = fitz.open(path)
    fp = []
    for p in d:
        placed = sorted((tuple(round(v, 2) for v in i["bbox"]), tuple(round(v, 3) for v in i["transform"]))
                        for i in p.get_image_info())
        fp.append((p.read_contents(), p.get_text(), [l.get("uri") for l in p.get_links()],
                   len(list(p.annots())), placed, tuple(p.rect)))
    d.close()
    return fp


ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS|ES_SYSTEM_REQUIRED
pythoncom.CoInitialize()
word = win32.DispatchEx("Word.Application"); word.Visible = False; word.DisplayAlerts = 0
restored, totals = [], dict(exp=0.0, res=0.0, rep=0, unm=0, amb=0, sc=0, n=0, bytes_in=0, bytes_out=0)
peak = 0
try:
    for part in parts:
        native = out / f"{part.stem}__native.pdf"; rest = out / f"{part.stem}__restored.pdf"
        t0 = time.time()
        doc = word.Documents.Open(str(part.resolve()), ReadOnly=True, AddToRecentFiles=False)
        try:
            doc.ExportAsFixedFormat(OutputFileName=str(native.resolve()), ExportFormat=17, OpenAfterExport=False,
                                    OptimizeFor=0, Range=0, Item=0, IncludeDocProps=True, KeepIRM=True,
                                    CreateBookmarks=0, DocStructureTags=True, BitmapMissingFonts=True,
                                    UseISO19005_1=False)
        finally:
            doc.Close(SaveChanges=False)
        t1 = time.time()
        rep = H.restore(part, native, rest)
        t2 = time.time()
        gc.collect(); peak = max(peak, peak_ws())
        ok = fingerprint(native) == fingerprint(rest)
        n_rep = sum(r["action"].startswith("REPLACED") for r in rep)
        n_amb = sum(str(r.get("why", "")).startswith("ambiguous") for r in rep)
        n_sc = sum("self-check" in r["action"] for r in rep)
        n_unm = sum(r["match"] is None for r in rep)
        totals.update(exp=totals["exp"] + t1 - t0, res=totals["res"] + t2 - t1, rep=totals["rep"] + n_rep,
                      unm=totals["unm"] + n_unm, amb=totals["amb"] + n_amb, sc=totals["sc"] + n_sc, n=totals["n"] + len(rep),
                      bytes_in=totals["bytes_in"] + native.stat().st_size, bytes_out=totals["bytes_out"] + rest.stat().st_size)
        pages = fitz.open(rest).page_count
        print(f"{part.name[:60]:<60} {part.stat().st_size/1e6:5.1f}MB p{pages:>3} export {t1-t0:5.1f}s restore {t2-t1:5.1f}s "
              f"imgs {len(rep):>3} replaced {n_rep:>3} ambiguous {n_amb} selfchk {n_sc} invariant={'OK' if ok else 'FAIL'}", flush=True)
        if n_amb:
            for r in rep:
                if str(r.get("why", "")).startswith("ambiguous"):
                    print("      ", r["page"], r["pdf"], r["why"])
        restored.append(rest)
finally:
    word.Quit(); pythoncom.CoUninitialize()
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

from src.postprocessing.converters import ComDocumentConverter
merged = out / "MERGED.pdf"
t3 = time.time()
ComDocumentConverter.merge_pdfs_batch(None, restored, merged)
t4 = time.time()
src_sizes = {(im[2], im[3]) for r in restored for p in fitz.open(r) for im in p.get_images(full=True)}
m = fitz.open(merged)
m_sizes = {(im[2], im[3]) for p in m for im in p.get_images(full=True)}
print(f"\nTOTAL parts={len(parts)} export={totals['exp']:.0f}s restore={totals['res']:.0f}s merge={t4-t3:.1f}s "
      f"images={totals['n']} replaced={totals['rep']} unmatched={totals['unm']} ambiguous={totals['amb']} selfcheck_rejects={totals['sc']}")
print(f"native sum {totals['bytes_in']/1e6:.1f}MB -> restored sum {totals['bytes_out']/1e6:.1f}MB -> merged {merged.stat().st_size/1e6:.1f}MB "
      f"({m.page_count} pages); image sizes lost in merge: {sorted(src_sizes - m_sizes)}; peak working set {peak/1e6:.0f}MB")
