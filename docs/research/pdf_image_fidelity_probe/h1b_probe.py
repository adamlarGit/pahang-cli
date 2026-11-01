"""H1b probe: ExportAsFixedFormat2(OptimizeForImageQuality) and LastPdfExportImageDownsampleOption.

Usage: python -I h1b_probe.py <workdir> <stem> <case>[,<case>...]
case: efx1 | efx2q (ExportAsFixedFormat2 OptimizeForImageQuality=True) | reg0 | reg2 (registry value, efx1)
Registry value is restored afterwards. Private Word instance per case (option may be read at startup).
"""
import collections, sys, time, winreg
from pathlib import Path

import fitz
import pythoncom
import win32com.client as win32

KEY = r"Software\Microsoft\Office\16.0\Word\Options"
NAME = "LastPdfExportImageDownsampleOption"
work = Path(sys.argv[1]); stem = sys.argv[2]; cases = sys.argv[3].split(",")
src = (work / "src" / f"{stem}.docx").resolve()


def summarize(pdf):
    d = fitz.open(pdf); c = collections.Counter(); seen = set()
    for p in d:
        for im in p.get_images(full=True):
            if im[0] in seen: continue
            seen.add(im[0]); c[(im[2], im[3], im[8])] += 1
    d.close()
    return "; ".join(f"{w}x{h} {f} x{n}" for (w, h, f), n in sorted(c.items(), key=lambda x: -x[0][0]*x[0][1])[:10])


def get_reg():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            return winreg.QueryValueEx(k, NAME)[0]
    except FileNotFoundError:
        return None


def set_reg(v):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        if v is None: winreg.DeleteValue(k, NAME)
        else: winreg.SetValueEx(k, NAME, 0, winreg.REG_DWORD, v)


orig = get_reg()
print("registry original:", orig)
pythoncom.CoInitialize()
try:
    for case in cases:
        if case.startswith("reg"):
            set_reg(int(case[3:]))
        word = win32.DispatchEx("Word.Application"); word.Visible = False; word.DisplayAlerts = 0
        pdf = (work / "out" / f"{stem}__{case}.pdf").resolve()
        t0 = time.time()
        try:
            doc = word.Documents.Open(str(src), ReadOnly=True, AddToRecentFiles=False)
            try:
                common = dict(OutputFileName=str(pdf), ExportFormat=17, OpenAfterExport=False, OptimizeFor=0,
                              Range=0, Item=0, IncludeDocProps=True, KeepIRM=True, CreateBookmarks=0,
                              DocStructureTags=True, BitmapMissingFonts=True, UseISO19005_1=False)
                if case == "efx2q":
                    doc.ExportAsFixedFormat2(OptimizeForImageQuality=True, **common)
                else:
                    doc.ExportAsFixedFormat(**common)
            finally:
                doc.Close(SaveChanges=False)
            print(f"[{case}] {time.time()-t0:.1f}s {pdf.stat().st_size//1024}KB :: {summarize(pdf)}", flush=True)
        except Exception as e:
            print(f"[{case}] ERROR {e!r}", flush=True)
        finally:
            word.Quit()
            if case.startswith("reg"):
                set_reg(orig)
finally:
    set_reg(orig) if get_reg() != orig else None
    print("registry restored:", get_reg())
    pythoncom.CoUninitialize()
