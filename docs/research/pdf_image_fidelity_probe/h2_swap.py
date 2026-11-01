"""H2 prototype: restore source-resolution images into a Word-native PDF.

Usage: python -I h2_swap.py <docx> <native_pdf> <out_pdf>

Sources harvested from the DOCX:
  * DrawingML / VML raster blips (jpeg/png/gif/bmp/tiff), with srcRect / VML crop applied
  * 24/32-bit DIBs embedded in WMF/EMF metafiles (StretchDIB / DibStretchBlt / EMR_STRETCHDIBITS)
Each PDF image XObject is matched to a source by aspect ratio + pixel similarity, and replaced only when
the source is strictly better (more pixels, or lossless where the PDF copy is JPEG).
Page content streams are never touched: only image streams are replaced, so layout is byte-for-byte stable.
"""
from __future__ import annotations

import io, re, struct, sys, time, zipfile
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageOps

RASTER = (".jpeg", ".jpg", ".png", ".gif", ".bmp", ".tif", ".tiff")
MATCH_THRESHOLD = 10.0  # mean abs grayscale diff on 0..255 at thumbnail scale
ASPECT_TOL = 0.04


@dataclass
class Source:
    label: str
    img: Image.Image          # RGB(A), already cropped as displayed
    raw: bytes | None         # original bytes usable verbatim (uncropped raster only)
    lossless: bool


def _crop_frac(img: Image.Image, l: float, t: float, r: float, b: float) -> Image.Image | None:
    if min(l, t, r, b) < 0:
        return None  # negative crop = padding; not representable as pixels
    w, h = img.size
    box = (round(w * l), round(h * t), round(w * (1 - r)), round(h * (1 - b)))
    if box[2] - box[0] < 4 or box[3] - box[1] < 4:
        return None
    return img.crop(box)


def _vml_frac(v: str | None) -> float:
    if not v:
        return 0.0
    return int(v[:-1]) / 65536 if v.endswith("f") else float(v)


def _dibs_from_metafile(b: bytes) -> list[Image.Image]:
    out = []
    i = 0
    while True:
        i = b.find(struct.pack("<I", 40), i)
        if i < 0 or i + 40 > len(b):
            break
        w, h, planes, bpp, comp = struct.unpack_from("<iiHHI", b, i + 4)
        if planes == 1 and bpp in (24, 32) and comp == 0 and 8 <= w <= 20000 and 8 <= abs(h) <= 20000:
            stride = ((w * bpp + 31) // 32) * 4
            size = stride * abs(h)
            if i + 40 + size <= len(b):
                bmp = b"BM" + struct.pack("<IHHI", 14 + 40 + size, 0, 0, 54) + b[i:i + 40 + size]
                try:
                    im = Image.open(io.BytesIO(bmp)); im.load()
                    out.append(im.convert("RGB"))
                    i += 40 + size
                    continue
                except Exception:
                    pass
        i += 4
    return out


def harvest(docx: Path) -> list[Source]:
    z = zipfile.ZipFile(docx)
    sources: list[Source] = []
    seen: set[tuple] = set()
    parts = [n for n in z.namelist() if re.match(r"word/(document|header\d*|footer\d*)\.xml$", n)]
    for part in parts:
        rel_path = part.replace("word/", "word/_rels/") + ".rels"
        if rel_path not in z.namelist():
            continue
        rels = z.read(rel_path).decode("utf8")
        rid = {}
        for m in re.finditer(r"<Relationship\b[^>]*>", rels):
            tag = m.group(0)
            i = re.search(r'Id="([^"]+)"', tag); t = re.search(r'Target="([^"]+)"', tag)
            if i and t:
                rid[i.group(1)] = "word/" + t.group(1).lstrip("/").replace("word/", "")
        x = z.read(part).decode("utf8")
        uses: list[tuple[str, tuple[float, float, float, float]]] = []
        for m in re.finditer(r"<a:blip\b[^>]*r:embed=\"([^\"]+)\".*?</pic:blipFill>", x, re.S):
            crop = re.search(r"<a:srcRect([^/]*)/>", m.group(0))
            fr = [0.0] * 4
            if crop:
                for k, key in enumerate("ltrb"):
                    v = re.search(rf'\b{key}="(-?\d+)"', crop.group(1))
                    fr[k] = int(v.group(1)) / 100000 if v else 0.0
            uses.append((m.group(1), tuple(fr)))
        for m in re.finditer(r"<v:imagedata\b([^>]*)/?>", x):
            a = m.group(1)
            r = re.search(r'r:id="([^"]+)"', a)
            if not r:
                continue
            g = lambda k: _vml_frac((re.search(rf'\b{k}="([^"]+)"', a) or [None, None])[1])
            uses.append((r.group(1), (g("cropleft"), g("croptop"), g("cropright"), g("cropbottom"))))
        for r_id, fr in uses:
            target = rid.get(r_id)
            if not target or target not in z.namelist() or (target, fr) in seen:
                continue
            seen.add((target, fr))
            data = z.read(target)
            ext = Path(target).suffix.lower()
            if ext in RASTER:
                im = Image.open(io.BytesIO(data)); im.load()
                uncropped = not any(fr)
                img = im if uncropped else _crop_frac(im, *fr)
                if img is None:
                    continue
                sources.append(Source(f"{Path(target).name}{'' if uncropped else ' crop'}", img,
                                      data if uncropped else None, lossless=ext != ".jpeg" and ext != ".jpg"))
            elif ext in (".wmf", ".emf"):
                # metafile crop is applied to the whole picture; inner bitmaps are matched uncropped and cropped
                for k, dib in enumerate(_dibs_from_metafile(data)):
                    key = (target, k)
                    if key in seen:
                        continue
                    seen.add(key)
                    sources.append(Source(f"{Path(target).name}#dib{k}", dib, None, lossless=True))
    return sources


def _thumb(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA"); bg.paste(rgba, mask=rgba.split()[3]); img = bg
    return ImageOps.grayscale(img.convert("RGB")).resize(size, Image.BILINEAR)


def _score(a: Image.Image, b: Image.Image) -> float:
    w = 64; h = max(4, round(64 * a.size[1] / a.size[0]))
    d = ImageChops.difference(_thumb(a, (w, h)), _thumb(b, (w, h)))
    return sum(d.getdata()) / (w * h)


ACCEPT_PCT = 0.5      # true matches measured <= 0.23 % strongly-differing pixels at PDF resolution
IMPOSTOR_PCT = 1.5    # distinct look-alikes measured >= 2.2 %
STRONG_DIFF = 48
TOP_K = 6


def _flat(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA"); bg.paste(rgba, mask=rgba.split()[3]); return bg
    return img.convert("RGB")


def full_pct(pdf_img: Image.Image, src_img: Image.Image) -> float:
    """% of pixels differing strongly once the source is resampled to the PDF image's own size."""
    d = ImageOps.grayscale(ImageChops.difference(pdf_img, _flat(src_img).resize(pdf_img.size, Image.LANCZOS)))
    h = d.histogram()
    return 100.0 * sum(h[STRONG_DIFF:]) / max(1, sum(h))


def choose(pimg: Image.Image, sources: list[Source]) -> tuple[Source | None, str]:
    pa = pimg.width / pimg.height
    pre = []
    for s in sources:
        sa = s.img.size[0] / s.img.size[1]
        if abs(sa - pa) / pa > ASPECT_TOL:
            continue
        sc = _score(pimg, s.img)
        if sc <= MATCH_THRESHOLD:
            pre.append((sc, s))
    pre.sort(key=lambda t: t[0])
    scored = sorted(((full_pct(pimg, s.img), s) for _, s in pre[:TOP_K]), key=lambda t: t[0])
    if not scored or scored[0][0] > ACCEPT_PCT:
        return None, "unmatched"
    best = scored[0][1]
    equivalent = [best]
    for pct, s in scored[1:]:
        if pct >= IMPOSTOR_PCT:
            continue
        # a close runner-up is fine only if it shows the same content as the best (same photo inserted twice)
        if full_pct(_flat(best.img).resize(pimg.size, Image.LANCZOS), s.img) <= ACCEPT_PCT:
            if pct <= ACCEPT_PCT:
                equivalent.append(s)
        else:
            return None, f"ambiguous({best.label}|{s.label})"
    # always restore the closest source; never substitute a "content-equivalent" different file
    return best, f"{scored[0][0]:.3f}%"


def _encode(src: Source) -> bytes:
    if src.raw is not None:
        return src.raw
    buf = io.BytesIO()
    if src.lossless:
        src.img.save(buf, "PNG", optimize=True)
    else:
        src.img.convert("RGB").save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


def replace_xobject(doc: fitz.Document, xref: int, payload: bytes) -> None:
    """Rewrite one image XObject in place. Pages, content streams and resources are untouched."""
    im = Image.open(io.BytesIO(payload))
    im.load()
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if im.format == "JPEG" and im.mode in ("RGB", "L"):
        doc.update_stream(xref, payload, compress=False)
        doc.xref_set_key(xref, "Filter", "/DCTDecode")
        cs = "/DeviceRGB" if im.mode == "RGB" else "/DeviceGray"
    else:
        base = im.convert("RGBA" if has_alpha else ("L" if im.mode in ("L", "1") else "RGB"))
        rgb = base.convert("RGB") if has_alpha else base
        doc.update_stream(xref, rgb.tobytes(), compress=True)
        cs = "/DeviceGray" if rgb.mode == "L" else "/DeviceRGB"
    doc.xref_set_key(xref, "DecodeParms", "null")
    doc.xref_set_key(xref, "Decode", "null")
    doc.xref_set_key(xref, "Width", str(im.width))
    doc.xref_set_key(xref, "Height", str(im.height))
    doc.xref_set_key(xref, "BitsPerComponent", "8")
    doc.xref_set_key(xref, "ColorSpace", cs)
    if has_alpha:
        alpha = im.convert("RGBA").split()[3].tobytes()
        sm = doc.get_new_xref()
        doc.update_object(sm, f"<</Type/XObject/Subtype/Image/Width {im.width}/Height {im.height}"
                              f"/ColorSpace/DeviceGray/BitsPerComponent 8>>")
        doc.update_stream(sm, alpha, compress=True)
        doc.xref_set_key(xref, "SMask", f"{sm} 0 R")
    else:
        # an old SMask sized for Word's pixels would no longer fit the new image
        doc.xref_set_key(xref, "SMask", "null")


def restore(docx: Path, native_pdf: Path, out_pdf: Path) -> list[dict]:
    sources = harvest(docx)
    doc = fitz.open(native_pdf)
    smasks = set()
    users: dict[int, int] = {}
    for pno, page in enumerate(doc):
        for im in page.get_images(full=True):
            if im[1]:
                smasks.add(im[1])
            users.setdefault(im[0], pno)
    report = []
    for xref, pno in users.items():
        if xref in smasks:
            continue
        info = doc.xref_get_key(xref, "Filter")[1]
        pix = fitz.Pixmap(doc, xref)
        if pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        if pix.colorspace and pix.colorspace.n != 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        pimg = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        best, why = choose(pimg, sources)
        row = dict(page=pno + 1, xref=xref, pdf=f"{pix.width}x{pix.height} {info}", match=None, action="keep", why=why)
        if best is not None:
            row["match"] = f"{best.label} {best.img.size[0]}x{best.img.size[1]} ({why})"
            src_px = best.img.size[0] * best.img.size[1]
            pdf_px = pix.width * pix.height
            more_px = src_px > pdf_px * 1.02
            # never trade pixels for losslessness: a smaller source means the PDF image is a rasterised composite
            lossless_gain = best.lossless and "DCT" in info and src_px >= pdf_px
            if more_px or lossless_gain:
                payload = _encode(best)
                # pre-write self-check: the exact bytes we insert must still look like Word's rendering
                if full_pct(pimg, Image.open(io.BytesIO(payload))) > ACCEPT_PCT:
                    row["action"] = "keep (self-check failed)"
                else:
                    replace_xobject(doc, xref, payload)
                    row["action"] = "REPLACED" + (" (+px)" if more_px else "") + (" (lossless)" if lossless_gain else "")
        report.append(row)
    doc.save(out_pdf, garbage=3, deflate=True)
    doc.close()
    return report


if __name__ == "__main__":
    t0 = time.time()
    rep = restore(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    for r in rep:
        print(f"p{r['page']:>2} xref{r['xref']:>4} {r['pdf']:<24} -> {r['action']:<26} {r['match'] or ''}")
    n = sum(r["action"].startswith("REPLACED") for r in rep)
    um = sum(r["match"] is None for r in rep)
    print(f"replaced={n} unmatched={um} total={len(rep)} in {time.time()-t0:.1f}s; "
          f"{Path(sys.argv[2]).stat().st_size//1024}KB -> {Path(sys.argv[3]).stat().st_size//1024}KB")
