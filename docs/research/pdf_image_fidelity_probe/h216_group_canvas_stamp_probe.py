"""Probe for #216 / ADR 0012: what Word writes into a tagged PDF for a group and a canvas of pictures.

Usage: python h216_group_canvas_stamp_probe.py <workdir>. Builds a DOCX, stamps it (make_export_copy), exports with Word, prints the
structure and the restoration result. Starts real Word: close Word and Excel first.
"""
import sys, re, io, time
from pathlib import Path
sys.path.insert(0, r"C:\Users\ADAM\Desktop\pahang-cli-33kv")
import pythoncom, win32com.client as win32, pymupdf as fitz, zipfile
from PIL import Image, ImageDraw
import random

work = Path(sys.argv[1]); work.mkdir(exist_ok=True, parents=True)

def graph(seed, size=(600, 400)):
    rnd = random.Random(seed); im = Image.new("RGB", size, "white"); d = ImageDraw.Draw(im)
    for i in range(20):
        h = rnd.randint(40, 280); col = tuple(rnd.randint(0, 200) for _ in range(3))
        d.rectangle([i*30+2, size[1]-h, (i+1)*30-2, size[1]], fill=col)
    return im

pngs = []
for k in range(1, 6):
    p = work / f"p{k}.png"; graph(k).save(p); pngs.append(str(p))

src = work / "groups.docx"
import io
from docx import Document
from docx.oxml import parse_xml
NSX = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
       'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
       'xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"')
doc = Document()
doc.add_paragraph("Group and canvas probe")
def picxml(rid, idx, x, y, cx, cy):
    return (f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{idx}" name="pic{idx}.png"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>')
def anchor(docpr_id, name, uri, body, W, H):
    return (f'<w:r {NSX}><w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="1" '
            f'behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1"><wp:simplePos x="0" y="0"/>'
            f'<wp:positionH relativeFrom="column"><wp:posOffset>0</wp:posOffset></wp:positionH>'
            f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>300000</wp:posOffset></wp:positionV>'
            f'<wp:extent cx="{W}" cy="{H}"/><wp:wrapNone/><wp:docPr id="{docpr_id}" name="{name}"/><wp:cNvGraphicFramePr/>'
            f'<a:graphic><a:graphicData uri="{uri}">{body}</a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>')
rids = [doc.part.get_or_add_image(open(p, "rb"))[0] for p in pngs]
W, H, w, h = 3600000, 1200000, 1700000, 1100000
grp = (f'<wpg:wgp><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{W}" cy="{H}"/>'
       f'<a:chOff x="0" y="0"/><a:chExt cx="{W}" cy="{H}"/></a:xfrm></wpg:grpSpPr>'
       + picxml(rids[0], 10, 0, 0, w, h) + picxml(rids[1], 11, 1800000, 0, w, h) + "</wpg:wgp>")
cnv = ('<wpc:wpc><wpc:bg/><wpc:whole/>' + picxml(rids[2], 20, 0, 0, w, h) + picxml(rids[3], 21, 1800000, 0, w, h) + "</wpc:wpc>")
body = doc.element.body
p1 = doc.add_paragraph("group:"); p1._p.append(parse_xml(anchor(1, "Group 1", "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup", grp, W, H)))
for _ in range(8): doc.add_paragraph("")
p2 = doc.add_paragraph("canvas:"); p2._p.append(parse_xml(anchor(2, "Canvas 2", "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas", cnv, W, H)))
for _ in range(8): doc.add_paragraph("")
doc.add_picture(pngs[4])  # control: a plain inline picture
doc.save(src)

with zipfile.ZipFile(src) as zf:
    xml = zf.read("word/document.xml").decode()
print("docPr:", re.findall(r"<wp:docPr [^>]*>", xml))
print("wgp:", xml.count("<wpg:wgp"), "wpc:", xml.count("<wpc:wpc"), "pic:pic:", xml.count("<pic:pic"), "blipFill:", xml.count("blipFill"))

from src.postprocessing.converters import make_export_copy
copy = work / "groups_copy.docx"
print("make_export_copy ->", make_export_copy(src, copy))
with zipfile.ZipFile(copy) as zf:
    print("stamped docPr:", re.findall(r'<wp:docPr [^>]*descr="PSRID[^>]*>', zf.read("word/document.xml").decode()))

pdf = work / "groups.pdf"
word = win32.DispatchEx("Word.Application"); word.Visible = False; word.DisplayAlerts = 0
try:
    doc = word.Documents.Open(str(copy), ReadOnly=True, AddToRecentFiles=False)
    doc.ExportAsFixedFormat(OutputFileName=str(pdf), ExportFormat=17, OpenAfterExport=False, OptimizeFor=0, Range=0, Item=0,
        IncludeDocProps=True, KeepIRM=True, CreateBookmarks=0, DocStructureTags=True, BitmapMissingFonts=True, UseISO19005_1=False)
    doc.Close(SaveChanges=False)
finally:
    word.Quit()
    pythoncom.CoUninitialize()

d = fitz.open(pdf)
print("--- struct elements with /Alt or Figure/InlineShape ---")
for x in range(1, d.xref_length()):
    try:
        s = d.xref_get_key(x, "S")[1]
        alt = d.xref_get_key(x, "Alt")
    except Exception:
        continue
    if s in ("/Figure", "/InlineShape") or (alt[0] == "string" and "PSRID" in alt[1]):
        print(x, s, "Alt=", alt[1], "K=", d.xref_get_key(x, "K")[1], "Pg=", d.xref_get_key(x, "Pg")[1])
for pno, page in enumerate(d):
    print(f"--- page {pno+1} images: {[(i[0], i[2], i[3], i[7]) for i in page.get_images(full=True)]}; forms: {[(x[0], x[1]) for x in page.get_xobjects()]}")
    c = page.read_contents().decode("latin-1")
    print(re.sub(r"\s+", " ", c)[:1500])
d.close()

from src.postprocessing.image_restoration import restore_source_images
out = work / "groups_restored.pdf"
rep = restore_source_images(src.read_bytes(), pdf, out)
print("RESTORE:", rep.images_total, "restored", rep.restored, "unmatched", rep.unmatched, "ambiguous", rep.ambiguous)
for e in rep.entries: print("  ", e)
