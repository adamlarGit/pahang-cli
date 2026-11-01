"""Source Image Restoration (ADR 0009, ticket #146).

Word's native PDF export resamples pictures above ~200 PPI and re-encodes FLIR previews as JPEG. This module puts
the original pixels from the DOCX back into the exported PDF of exactly one Full Report Part, by rewriting image
XObjects in place. Page content streams, text, links, annotations and geometry are never modified; an invariance
gate proves it before anything is published.

No COM, Word or printer dependency: the DOCX arrives as the caller's byte snapshot.
"""

from __future__ import annotations

import io
import logging
import posixpath
import struct
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageChops, ImageOps, ImageStat

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from .converters import safe_replace_with_retry

logger = logging.getLogger(__name__)

RASTER_EXTS = (".jpeg", ".jpg", ".png", ".gif", ".bmp", ".tif", ".tiff")
METAFILE_EXTS = (".wmf", ".emf")

ASPECT_TOL = 0.04
THUMB_SIZE = (64, 64)
STAGE1_MAX_DIFF = 10.0  # mean abs grey diff on the 64 px thumbnail
STAGE1_KEEP = 6
STRONG_DIFF = 48  # grey level difference counted as "strongly differing"
ACCEPT_PCT = 0.5  # true matches measured <= 0.23 %
IMPOSTOR_PCT = 1.5  # look-alikes measured >= 2.2 %; below this a runner-up is a threat
MORE_PIXELS_RATIO = 1.02
MIN_CROP_PX = 4

_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "v": "urn:schemas-microsoft-com:vml",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
_R_EMBED = f"{{{_NS['r']}}}embed"
_R_ID = f"{{{_NS['r']}}}id"


class RestorationError(Exception):
    """Restoration failed; the caller must keep the native PDF."""


@dataclass(frozen=True)
class RestorationEntry:
    page: int
    xref: int
    pdf_size: tuple[int, int]
    source: str | None
    action: str  # restored | kept | unmatched | ambiguous | self_check_rejected


@dataclass(frozen=True)
class RestorationReport:
    images_total: int
    restored: int
    unmatched: int
    ambiguous: int
    self_check_rejected: int
    elapsed_s: float
    entries: tuple[RestorationEntry, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- sources


@dataclass(eq=False)
class _Source:
    """A harvested DOCX picture. Holds encoded bytes, header size and a thumbnail; pixels decode on demand."""

    label: str
    data: bytes
    size: tuple[int, int]  # size after crop
    lossless: bool
    crop: tuple[float, float, float, float] | None  # left, top, right, bottom fractions
    thumb: Image.Image
    dib_span: tuple[int, int] | None = None  # (offset, length) of a DIB inside a metafile blob

    @property
    def verbatim(self) -> bool:
        return self.crop is None and self.dib_span is None

    def load(self) -> Image.Image:
        if self.dib_span is not None:
            im = _dib_image(self.data, self.dib_span)
        else:
            im = Image.open(io.BytesIO(self.data))
        im.load()
        if self.crop is not None:
            box = _crop_box(im.size, self.crop)
            if box is None:  # pragma: no cover - guarded at harvest
                raise RestorationError(f"Invalid crop for {self.label}")
            im = im.crop(box)
        return im


def _dib_image(blob: bytes, span: tuple[int, int]) -> Image.Image:
    off, length = span
    bmp = b"BM" + struct.pack("<IHHI", 14 + length, 0, 0, 54) + blob[off : off + length]
    im = Image.open(io.BytesIO(bmp))
    im.load()
    return im


def _crop_box(size: tuple[int, int], fr: tuple[float, float, float, float]) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = fr
    if min(fr) < 0:  # negative crop is padding, not representable as pixels
        return None
    w, h = size
    box = (round(w * left), round(h * top), round(w * (1 - right)), round(h * (1 - bottom)))
    if box[2] - box[0] < MIN_CROP_PX or box[3] - box[1] < MIN_CROP_PX:
        return None
    return box


def _flat(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        return bg
    return img.convert("RGB")


def _thumb(img: Image.Image) -> Image.Image:
    return ImageOps.grayscale(_flat(img)).resize(THUMB_SIZE, Image.BILINEAR)


def _vml_frac(value: str | None) -> float:
    if not value:
        return 0.0
    value = value.strip()
    try:
        return int(value[:-1]) / 65536 if value.endswith("f") else float(value)
    except ValueError:
        return 0.0


def _dibs_in_metafile(blob: bytes) -> list[tuple[int, int]]:
    """Spans (offset, length) of uncompressed 24/32-bit BITMAPINFOHEADER DIBs embedded in a WMF/EMF."""
    spans: list[tuple[int, int]] = []
    marker = struct.pack("<I", 40)
    i = 0
    while True:
        i = blob.find(marker, i)
        if i < 0 or i + 40 > len(blob):
            break
        w, h, planes, bpp, comp = struct.unpack_from("<iiHHI", blob, i + 4)
        if planes == 1 and bpp in (24, 32) and comp == 0 and 8 <= w <= 20000 and 8 <= abs(h) <= 20000:
            size = ((w * bpp + 31) // 32) * 4 * abs(h)
            if i + 40 + size <= len(blob):
                spans.append((i, 40 + size))
                i += 40 + size
                continue
        i += 4
    return spans


def _read_rels(zf: zipfile.ZipFile, part: str) -> dict[str, str]:
    rel_path = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if rel_path not in zf.namelist():
        return {}
    out: dict[str, str] = {}
    for rel in ET.fromstring(zf.read(rel_path)).findall("rel:Relationship", _NS):
        if rel.get("TargetMode") == "External":
            continue  # linked picture: never harvested
        rid, target = rel.get("Id"), rel.get("Target")
        if not rid or not target:
            continue
        if target.startswith("/"):
            out[rid] = target.lstrip("/")
        else:
            out[rid] = posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
    return out


def _picture_uses(root: ET.Element) -> list[tuple[str, tuple[float, float, float, float]]]:
    uses: list[tuple[str, tuple[float, float, float, float]]] = []
    for fill in root.iter(f"{{{_NS['pic']}}}blipFill"):
        blip = fill.find("a:blip", _NS)
        if blip is None or not blip.get(_R_EMBED):
            continue
        fr = [0.0] * 4
        rect = fill.find("a:srcRect", _NS)
        if rect is not None:
            for k, key in enumerate("ltrb"):
                try:
                    fr[k] = int(rect.get(key, "0")) / 100000
                except ValueError:
                    fr[k] = 0.0
        uses.append((blip.get(_R_EMBED), (fr[0], fr[1], fr[2], fr[3])))
    for node in root.iter(f"{{{_NS['v']}}}imagedata"):
        rid = node.get(_R_ID)
        if not rid:
            continue
        uses.append(
            (
                rid,
                (
                    _vml_frac(node.get("cropleft")),
                    _vml_frac(node.get("croptop")),
                    _vml_frac(node.get("cropright")),
                    _vml_frac(node.get("cropbottom")),
                ),
            )
        )
    return uses


def harvest_sources(docx_bytes: bytes) -> list[_Source]:
    """Collect candidate source pictures from the DOCX byte snapshot (never from a path)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(docx_bytes))
    except (zipfile.BadZipFile, OSError) as exc:
        raise RestorationError(f"DOCX snapshot is not a valid archive: {exc}") from exc
    sources: list[_Source] = []
    seen: set[tuple] = set()
    with zf:
        try:
            parts = [
                n
                for n in zf.namelist()
                if n.startswith("word/")
                and "/" not in n[5:]
                and (n == "word/document.xml" or (n.endswith(".xml") and n[5:].startswith(("header", "footer"))))
            ]
            for part in parts:
                rels = _read_rels(zf, part)
                for rid, crop in _picture_uses(ET.fromstring(zf.read(part))):
                    target = rels.get(rid)
                    if not target or target not in zf.namelist():
                        continue
                    ext = posixpath.splitext(target)[1].lower()
                    if ext in RASTER_EXTS:
                        key: tuple = (target, crop)
                        if key in seen:
                            continue
                        seen.add(key)
                        src = _raster_source(target, zf.read(target), crop, ext)
                        if src is not None:
                            sources.append(src)
                    elif ext in METAFILE_EXTS:
                        if (target, "meta") in seen:
                            continue
                        seen.add((target, "meta"))
                        blob = zf.read(target)
                        for k, span in enumerate(_dibs_in_metafile(blob)):
                            src = _dib_source(f"{posixpath.basename(target)}#dib{k}", blob, span)
                            if src is not None:
                                sources.append(src)
        except RestorationError:
            raise
        except Exception as exc:
            raise RestorationError(f"Failed to harvest DOCX pictures: {exc}") from exc
    return sources


def _raster_source(target: str, data: bytes, crop, ext: str) -> _Source | None:
    uncropped = not any(crop)
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            size = im.size
            if uncropped:
                cropped_size, thumb = size, _thumb(im)
                use_crop = None
            else:
                box = _crop_box(size, crop)
                if box is None:
                    return None
                piece = im.crop(box)
                cropped_size, thumb = piece.size, _thumb(piece)
                use_crop = crop
    except Exception as exc:
        logger.debug("Skipping undecodable picture %s: %s", target, exc)
        return None
    label = posixpath.basename(target) + ("" if uncropped else " crop")
    return _Source(label, data, cropped_size, ext not in (".jpg", ".jpeg"), use_crop, thumb)


def _dib_source(label: str, blob: bytes, span: tuple[int, int]) -> _Source | None:
    try:
        im = _dib_image(blob, span)
        size, thumb = im.size, _thumb(im)
        im.close()
    except Exception as exc:
        logger.debug("Skipping undecodable DIB %s: %s", label, exc)
        return None
    return _Source(label, blob, size, True, None, thumb, span)


# --------------------------------------------------------------------------- matching


def _strong_pct(a: Image.Image, b: Image.Image) -> float:
    """% of pixels whose grey difference is >= STRONG_DIFF. Both images must share a size."""
    hist = ImageOps.grayscale(ImageChops.difference(a, b)).histogram()
    return 100.0 * sum(hist[STRONG_DIFF:]) / max(1, sum(hist))


def _resized_flat(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return _flat(img).resize(size, Image.LANCZOS)


def _pct_vs_source(pdf_img: Image.Image, source_pixels: Image.Image) -> float:
    return _strong_pct(pdf_img, _resized_flat(source_pixels, pdf_img.size))


def _stage2(pdf_img: Image.Image, source: _Source) -> float:
    px = source.load()
    try:
        return _pct_vs_source(pdf_img, px)
    finally:
        px.close()


def _mutual_pct(size: tuple[int, int], a: _Source, b: _Source) -> float:
    pa, pb = a.load(), b.load()
    try:
        return _strong_pct(_resized_flat(pa, size), _resized_flat(pb, size))
    finally:
        pa.close()
        pb.close()


def _choose(pdf_img: Image.Image, sources: list[_Source]) -> tuple[_Source | None, str]:
    """Return (best_source, status) where status is matched | unmatched | ambiguous."""
    pa = pdf_img.width / pdf_img.height
    pdf_thumb = _thumb(pdf_img)
    pre: list[tuple[float, _Source]] = []
    for s in sources:
        sa = s.size[0] / s.size[1]
        if abs(sa - pa) / pa > ASPECT_TOL:
            continue
        diff = ImageStat.Stat(ImageChops.difference(pdf_thumb, s.thumb)).mean[0]
        if diff <= STAGE1_MAX_DIFF:
            pre.append((diff, s))
    pre.sort(key=lambda t: t[0])
    scored = sorted(((_stage2(pdf_img, s), s) for _, s in pre[:STAGE1_KEEP]), key=lambda t: t[0])
    if not scored or scored[0][0] > ACCEPT_PCT:
        return None, "unmatched"
    best = scored[0][1]
    for pct, other in scored[1:]:
        if pct >= IMPOSTOR_PCT:
            continue
        if _mutual_pct(pdf_img.size, best, other) > ACCEPT_PCT:
            return None, "ambiguous"
    return best, "matched"


# --------------------------------------------------------------------------- replacement


def _encode_payload(source: _Source, pixels: Image.Image) -> bytes:
    if source.verbatim:
        return source.data
    buf = io.BytesIO()
    if source.lossless:
        pixels.save(buf, "PNG", optimize=True)
    else:
        pixels.convert("RGB").save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


def _replace_xobject(doc, xref: int, payload: bytes) -> None:
    """Rewrite one image XObject in place; pages, content streams and resources stay untouched."""
    with Image.open(io.BytesIO(payload)) as im:
        im.load()
        width, height = im.size
        has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        if im.format == "JPEG" and im.mode in ("RGB", "L"):
            doc.update_stream(xref, payload, compress=False)
            doc.xref_set_key(xref, "Filter", "/DCTDecode")
            cs = "/DeviceRGB" if im.mode == "RGB" else "/DeviceGray"
            alpha = None
        else:
            base = im.convert("RGBA" if has_alpha else ("L" if im.mode in ("L", "1") else "RGB"))
            alpha = base.split()[3].tobytes() if has_alpha else None
            rgb = base.convert("RGB") if has_alpha else base
            doc.update_stream(xref, rgb.tobytes(), compress=True)
            cs = "/DeviceGray" if rgb.mode == "L" else "/DeviceRGB"
    doc.xref_set_key(xref, "DecodeParms", "null")
    doc.xref_set_key(xref, "Decode", "null")
    doc.xref_set_key(xref, "Width", str(width))
    doc.xref_set_key(xref, "Height", str(height))
    doc.xref_set_key(xref, "BitsPerComponent", "8")
    doc.xref_set_key(xref, "ColorSpace", cs)
    if alpha is not None:
        sm = doc.get_new_xref()
        doc.update_object(
            sm,
            f"<</Type/XObject/Subtype/Image/Width {width}/Height {height}"
            f"/ColorSpace/DeviceGray/BitsPerComponent 8>>",
        )
        doc.update_stream(sm, alpha, compress=True)
        doc.xref_set_key(xref, "SMask", f"{sm} 0 R")
    else:
        # an old SMask sized for Word's pixels no longer fits the new image
        doc.xref_set_key(xref, "SMask", "null")


def _pdf_image(doc, xref: int) -> Image.Image:
    pix = fitz.Pixmap(doc, xref)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    if pix.colorspace is None or pix.colorspace.n != 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _restore_into(doc, sources: list[_Source]) -> list[RestorationEntry]:
    smasks: set[int] = set()
    first_page: dict[int, int] = {}
    for pno, page in enumerate(doc):
        for item in page.get_images(full=True):
            if item[1]:
                smasks.add(item[1])
            first_page.setdefault(item[0], pno + 1)

    entries: list[RestorationEntry] = []
    for xref, pno in first_page.items():
        if xref in smasks:
            continue
        try:
            entries.append(_restore_one(doc, xref, pno, sources))
        except RestorationError:
            raise
        except Exception as exc:
            logger.debug("Image xref %s left as rendered: %s", xref, exc)
            entries.append(RestorationEntry(pno, xref, (0, 0), None, "unmatched"))
    return entries


def _restore_one(doc, xref: int, pno: int, sources: list[_Source]) -> RestorationEntry:
    filt = doc.xref_get_key(xref, "Filter")[1]
    pdf_img = _pdf_image(doc, xref)
    size = pdf_img.size
    best, status = _choose(pdf_img, sources)
    if best is None:
        return RestorationEntry(pno, xref, size, None, status)

    src_px = best.size[0] * best.size[1]
    pdf_px = size[0] * size[1]
    more_px = src_px > pdf_px * MORE_PIXELS_RATIO
    lossless_gain = best.lossless and "DCT" in filt and src_px >= pdf_px
    if not (more_px or lossless_gain):
        return RestorationEntry(pno, xref, size, best.label, "kept")

    pixels = best.load()
    try:
        payload = _encode_payload(best, pixels)
    finally:
        pixels.close()
    # pre-write self-check: the exact bytes we insert must still look like Word's rendering
    with Image.open(io.BytesIO(payload)) as check:
        check.load()
        mismatch = _pct_vs_source(pdf_img, check)
    if mismatch > ACCEPT_PCT:
        return RestorationEntry(pno, xref, size, best.label, "self_check_rejected")
    try:
        _replace_xobject(doc, xref, payload)
    except Exception as exc:
        # the XObject may be half-rewritten (new stream under old dictionary keys): never ship this document
        raise RestorationError(f"Failed to rewrite image xref {xref}: {exc}") from exc
    return RestorationEntry(pno, xref, size, best.label, "restored")


# --------------------------------------------------------------------------- invariance gate


def _placements(page) -> list[tuple]:
    return [
        (tuple(round(v, 3) for v in info["bbox"]), tuple(round(v, 3) for v in info["transform"]))
        for info in page.get_image_info()
    ]


def _links(page) -> list[tuple]:
    return [
        (lk.get("kind"), tuple(round(v, 3) for v in lk["from"]), lk.get("uri"), lk.get("page"), lk.get("nameddest"))
        for lk in page.get_links()
    ]


def verify_invariance(native_pdf: Path, candidate_pdf: Path) -> None:
    """Raise RestorationError unless candidate differs from native only in image stream pixels."""
    try:
        with fitz.open(native_pdf) as a, fitz.open(candidate_pdf) as b:
            if a.page_count != b.page_count:
                raise RestorationError("Invariance: page count changed")
            for i in range(a.page_count):
                pa, pb = a[i], b[i]
                where = f"page {i + 1}"
                if tuple(pa.rect) != tuple(pb.rect):
                    raise RestorationError(f"Invariance: {where} geometry changed")
                if pa.read_contents() != pb.read_contents():
                    raise RestorationError(f"Invariance: {where} content stream changed")
                if pa.get_text() != pb.get_text():
                    raise RestorationError(f"Invariance: {where} text changed")
                if _links(pa) != _links(pb):
                    raise RestorationError(f"Invariance: {where} links changed")
                if len(list(pa.annots())) != len(list(pb.annots())):
                    raise RestorationError(f"Invariance: {where} annotation count changed")
                if _placements(pa) != _placements(pb):
                    raise RestorationError(f"Invariance: {where} image placement changed")
    except RestorationError:
        raise
    except Exception as exc:
        raise RestorationError(f"Invariance check failed: {exc}") from exc


# --------------------------------------------------------------------------- public API


def restore_source_images(docx_bytes: bytes, native_pdf: Path, output_pdf: Path) -> RestorationReport:
    """Restore DOCX source pixels into ``native_pdf`` and publish the result atomically at ``output_pdf``.

    ``output_pdf`` is always produced on success, even when nothing was replaced. Known limitation: the
    self-check compares in RGB, so CMYK/ICC colour shifts and EXIF-rotated JPEG sources are not distinguished from
    Word's rendering; such sources either match within tolerance or are left as Word rendered them.

    Inputs are never modified. Raises RestorationError on any failure; the caller then keeps the native PDF.
    """
    t0 = time.perf_counter()
    native_pdf, output_pdf = Path(native_pdf), Path(output_pdf)
    tmp = output_pdf.with_name(f".tmp_restore_{uuid.uuid4().hex[:8]}_{output_pdf.name}")
    try:
        sources = harvest_sources(docx_bytes)
        with fitz.open(native_pdf) as doc:
            entries = _restore_into(doc, sources)
            doc.save(tmp, garbage=3, deflate=True)
        verify_invariance(native_pdf, tmp)
        if not safe_replace_with_retry(tmp, output_pdf):
            raise RestorationError(f"Could not publish restored PDF to {output_pdf}")
    except RestorationError:
        raise
    except Exception as exc:
        raise RestorationError(f"Source Image Restoration failed: {exc}") from exc
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best effort
            logger.debug("Could not remove temp file %s", tmp)

    def count(action: str) -> int:
        return sum(1 for e in entries if e.action == action)

    return RestorationReport(
        images_total=len(entries),
        restored=count("restored"),
        unmatched=count("unmatched"),
        ambiguous=count("ambiguous"),
        self_check_rejected=count("self_check_rejected"),
        elapsed_s=time.perf_counter() - t0,
        entries=tuple(entries),
    )
