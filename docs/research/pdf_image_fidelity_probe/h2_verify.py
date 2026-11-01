"""Verify a restored PDF against its native original.

1. Layout invariance: text, links, annotations and page-level render diff (at 50 dpi) must match.
2. Pipeline survival: merge restored PDF with another PDF via the production merge_pdfs_batch,
   then re-save with the us_audio save options; image dimensions must survive.
3. Zoom crops for human inspection.
Usage: python -I h2_verify.py <repo> <native_pdf> <restored_pdf> <extra_pdf> <outdir> <page:x0,y0,x1,y1>...
"""
import sys
from pathlib import Path

repo = Path(sys.argv[1]); sys.path.insert(0, str(repo))
import fitz
from PIL import Image, ImageChops

native, restored, extra, outdir = map(Path, sys.argv[2:6])
crops = sys.argv[6:]


def dims(path):
    d = fitz.open(path)
    out = sorted({(im[2], im[3]) for p in d for im in p.get_images(full=True)}, key=lambda x: -x[0] * x[1])
    d.close()
    return out


a, b = fitz.open(native), fitz.open(restored)
assert a.page_count == b.page_count, "page count changed"
worst = 0.0
for i in range(a.page_count):
    pa, pb = a[i], b[i]
    assert pa.get_text() == pb.get_text(), f"text changed p{i+1}"
    assert [l.get("uri") for l in pa.get_links()] == [l.get("uri") for l in pb.get_links()], f"links changed p{i+1}"
    xa = pa.get_pixmap(dpi=50); xb = pb.get_pixmap(dpi=50)
    ima = Image.frombytes("RGB", (xa.width, xa.height), xa.samples)
    imb = Image.frombytes("RGB", (xb.width, xb.height), xb.samples)
    d = ImageChops.difference(ima, imb).convert("L")
    mean = sum(d.getdata()) / (d.width * d.height)
    worst = max(worst, mean)
print(f"layout: {a.page_count} pages, text+links identical, worst page render diff @50dpi = {worst:.2f}/255")

from src.postprocessing.converters import ComDocumentConverter
merged = outdir / "merged_check.pdf"
ComDocumentConverter.merge_pdfs_batch(None, [restored, extra], merged)
m = fitz.open(merged); m.save(outdir / "merged_resaved.pdf", garbage=3, deflate=True); m.close()
rd, md = dims(restored), dims(outdir / "merged_resaved.pdf")
missing = [x for x in rd if x not in md]
print(f"pipeline survival: restored has {len(rd)} distinct image sizes, missing after merge+resave: {missing}")

for spec in crops:
    # spec = page:xref -> zoom into the middle third of that image's placement on the page
    pno, xref = map(int, spec.split(":"))
    r = a[pno - 1].get_image_rects(xref)[0]
    clip = fitz.Rect(r.x0 + r.width / 3, r.y0 + r.height / 3, r.x0 + 2 * r.width / 3, r.y0 + 2 * r.height / 3)
    for tag, doc in (("native", a), ("restored", b)):
        pix = doc[pno - 1].get_pixmap(dpi=600, clip=clip)
        pix.save(outdir / f"zoom_p{pno}_x{xref}_{tag}.png")
print("zoom crops written")
