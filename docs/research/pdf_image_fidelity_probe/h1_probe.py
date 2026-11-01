"""H1 probe: does w14:defaultImageDpi control Word native PDF export downsampling?

Writes only inside this probe directory. Uses a private Word instance (DispatchEx).
Usage: python -I h1_probe.py <workdir> <stem> <variant>[,<variant>...]
variant: 'base' (unchanged) or an integer DPI value written into w14:defaultImageDpi.
"""
import collections, re, shutil, sys, time, zipfile
from pathlib import Path

import fitz
import pythoncom
import win32com.client as win32

work = Path(sys.argv[1])
stem = sys.argv[2]
variants = sys.argv[3].split(",")
src = work / "src" / f"{stem}.docx"
out = work / "out"


def make_variant(v: str) -> Path:
    dst = work / "var" / f"{stem}__{v}.docx"
    dst.parent.mkdir(exist_ok=True)
    if v == "base":
        shutil.copy(src, dst)
        return dst
    zin = zipfile.ZipFile(src)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/settings.xml":
                s = data.decode("utf8")
                s = re.sub(r"<w14:defaultImageDpi[^>]*/>", "", s)
                tag = f'<w14:defaultImageDpi w14:val="{v}"/>'
                s = s.replace("<w14:docId", tag + "<w14:docId", 1) if "<w14:docId" in s else s.replace("</w:settings>", tag + "</w:settings>")
                data = s.encode("utf8")
            zout.writestr(item, data)
    return dst


def summarize(pdf: Path) -> str:
    d = fitz.open(pdf)
    c = collections.Counter()
    seen = set()
    for p in d:
        for im in p.get_images(full=True):
            if im[0] in seen:
                continue
            seen.add(im[0])
            c[(im[2], im[3], im[8])] += 1
    d.close()
    big = sorted(c.items(), key=lambda x: -x[0][0] * x[0][1])[:12]
    return "; ".join(f"{w}x{h} {f} x{n}" for (w, h, f), n in big)


pythoncom.CoInitialize()
word = win32.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    for v in variants:
        docx = make_variant(v)
        pdf = out / f"{stem}__{v}.pdf"
        t0 = time.time()
        doc = word.Documents.Open(str(docx.resolve()), ReadOnly=True, AddToRecentFiles=False)
        try:
            doc.ExportAsFixedFormat(
                OutputFileName=str(pdf.resolve()), ExportFormat=17, OpenAfterExport=False,
                OptimizeFor=0, Range=0, Item=0, IncludeDocProps=True, KeepIRM=True,
                CreateBookmarks=0, DocStructureTags=True, BitmapMissingFonts=True, UseISO19005_1=False,
            )
        finally:
            doc.Close(SaveChanges=False)
        print(f"[{v}] {time.time()-t0:.1f}s {pdf.stat().st_size//1024}KB :: {summarize(pdf)}", flush=True)
finally:
    word.Quit()
    pythoncom.CoUninitialize()
