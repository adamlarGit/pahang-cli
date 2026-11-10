"""Behavior tests for Source Image Restoration (ticket #146, ADR 0009).

Seam: ``restore_source_images(docx_bytes, native_pdf, output_pdf) -> RestorationReport`` plus
``verify_invariance`` (the gate). Fixtures are synthetic (python-docx + PyMuPDF); no client data.
"""

from __future__ import annotations

import io
import random
import struct
from pathlib import Path

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml
from PIL import Image, ImageDraw

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from src.postprocessing import image_restoration as ir
from src.postprocessing.image_restoration import (
    RestorationError,
    restore_source_images,
    verify_invariance,
)

NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)


# ---------------------------------------------------------------- fixture helpers


def graph(seed: int, size=(600, 400)) -> Image.Image:
    rnd = random.Random(seed)
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    n = 20
    bw = size[0] // n
    for i in range(n):
        h = rnd.randint(40, int(size[1] * 0.7))
        col = (rnd.randint(0, 200), rnd.randint(0, 200), rnd.randint(0, 200))
        d.rectangle([i * bw + 2, size[1] - h, (i + 1) * bw - 2, size[1]], fill=col)
    return im


def panel(digits: list[int], size=(600, 400)) -> Image.Image:
    """A mostly-white table panel (like a US/TEV reading panel) whose only content is a few rows of digit blocks."""
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    for row in range(8):
        d.rectangle([20, 20 + row * 40, 560, 24 + row * 40], fill="black")  # rule line
        for col in range(6):
            x = 30 + col * 90
            d.rectangle([x, 30 + row * 40, x + 40, 50 + row * 40], fill="black")
            if (digits[row] >> col) & 1:  # this reading differs: the block is drawn with a gap in it
                d.rectangle([x + 10, 34 + row * 40, x + 30, 46 + row * 40], fill="white")
    return im


def png_bytes(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def jpeg_bytes(im: Image.Image, q=60) -> bytes:
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=q)
    return b.getvalue()


def docx_with_pictures(pictures: list[bytes]) -> bytes:
    doc = Document()
    for p in pictures:
        doc.add_picture(io.BytesIO(p))
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def docx_with_srccrop(picture: bytes, l=0, t=0, r=0, b=0) -> bytes:
    doc = Document()
    doc.add_picture(io.BytesIO(picture))
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    blip_fill = doc.element.body.xpath(".//pic:blipFill")[0]
    blip = blip_fill.xpath("./a:blip")[0]
    src = parse_xml(
        f'<a:srcRect xmlns:a="{ns["a"]}" l="{l}" t="{t}" r="{r}" b="{b}"/>'
    )
    blip.addnext(src)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def docx_with_vml_crop(picture: bytes, **crop: str) -> bytes:
    doc = Document()
    rid, _ = doc.part.get_or_add_image(io.BytesIO(picture))
    attrs = " ".join(f'{k}="{v}"' for k, v in crop.items())
    run = parse_xml(
        f'<w:r {NS}><w:pict><v:shape style="width:100pt;height:80pt">'
        f'<v:imagedata r:id="{rid}" {attrs}/></v:shape></w:pict></w:r>'
    )
    doc.add_paragraph()._p.append(run)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def wmf_with_dib(im: Image.Image) -> bytes:
    """Fake placeable-WMF blob carrying one 24-bit uncompressed DIB (bottom-up)."""
    w, h = im.size
    stride = ((w * 24 + 31) // 32) * 4
    rows = []
    rgb = im.convert("RGB")
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b = rgb.getpixel((x, y))
            row += bytes((b, g, r))
        row += b"\x00" * (stride - len(row))
        rows.append(bytes(row))
    hdr = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, stride * h, 0, 0, 0, 0)
    return b"\xd7\xcd\xc6\x9a" + b"\x00" * 22 + hdr + b"".join(rows)


def docx_with_wmf(wmf: bytes) -> bytes:
    doc = Document()
    part = Part(PackURI("/word/media/obj1.wmf"), "image/x-wmf", wmf, doc.part.package)
    rid = doc.part.relate_to(part, RT.IMAGE)
    run = parse_xml(
        f'<w:r {NS}><w:pict><v:shape style="width:100pt;height:80pt">'
        f'<v:imagedata r:id="{rid}"/></v:shape></w:pict></w:r>'
    )
    doc.add_paragraph()._p.append(run)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def native_pdf(path: Path, images: list[bytes], link: str | None = "https://example.com/x") -> Path:
    """A PDF as Word would have exported: pictures embedded at the given (already downsampled) bytes."""
    doc = fitz.open()
    for i, data in enumerate(images):
        page = doc.new_page(width=595, height=842)
        page.insert_image(fitz.Rect(50, 100, 350, 300), stream=data)
        page.insert_text((50, 60), f"Page {i + 1} text")
        if link and i == 0:
            page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(50, 40, 150, 70), "uri": link})
    doc.save(path)
    doc.close()
    return path


def pdf_images(path: Path) -> list[tuple[int, int, str]]:
    out = []
    with fitz.open(path) as doc:
        seen = set()
        smasks = {im[1] for p in doc for im in p.get_images(full=True) if im[1]}
        for p in doc:
            for im in p.get_images(full=True):
                if im[0] in seen or im[0] in smasks:
                    continue
                seen.add(im[0])
                out.append((im[2], im[3], doc.xref_get_key(im[0], "Filter")[1]))
    return out


def pdf_pixels(path: Path, index: int = 0) -> Image.Image:
    with fitz.open(path) as doc:
        xrefs = []
        for p in doc:
            for im in p.get_images(full=True):
                if im[0] not in xrefs:
                    xrefs.append(im[0])
        pix = fitz.Pixmap(doc, xrefs[index])
        if pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def mean_abs_diff(a: Image.Image, b: Image.Image) -> float:
    assert a.size == b.size
    pa, pb = a.convert("RGB").tobytes(), b.convert("RGB").tobytes()
    return sum(abs(x - y) for x, y in zip(pa, pb)) / len(pa)


@pytest.fixture
def paths(tmp_path: Path):
    return tmp_path / "native.pdf", tmp_path / "out.pdf"


def leftovers(dir_: Path) -> list[Path]:
    return [p for p in dir_.iterdir() if p.name.startswith(".tmp_restore_")]


# ---------------------------------------------------------------- restoration behavior


def test_downsampled_png_is_restored_to_source_pixels(paths):
    native, out = paths
    src = graph(1)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert report.restored == 1 and report.images_total == 1
    assert pdf_images(out)[0][:2] == (600, 400)
    assert mean_abs_diff(pdf_pixels(out), src) == 0
    assert report.entries[0].action == "restored"


def test_jpeg_reencoded_lossless_source_is_restored_losslessly(paths):
    native, out = paths
    src = graph(2)
    native_pdf(native, [jpeg_bytes(src, q=40)])
    assert "DCT" in pdf_images(native)[0][2]
    report = restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert report.restored == 1
    assert "DCT" not in pdf_images(out)[0][2]
    assert mean_abs_diff(pdf_pixels(out), src) == 0


def test_drawingml_cropped_source_is_restored_to_cropped_region(paths):
    native, out = paths
    src = graph(3)
    cropped = src.crop((60, 40, 540, 360))  # l=10% t=10% r=10% b=10%
    native_pdf(native, [png_bytes(cropped.resize((240, 160), Image.LANCZOS))])
    docx = docx_with_srccrop(png_bytes(src), l=10000, t=10000, r=10000, b=10000)
    report = restore_source_images(docx, native, out)
    assert report.restored == 1
    assert pdf_images(out)[0][:2] == (480, 320)
    assert mean_abs_diff(pdf_pixels(out), cropped) == 0


def test_vml_cropped_source_is_restored_to_cropped_region(paths):
    native, out = paths
    src = graph(4)
    cropped = src.crop((60, 40, 540, 360))
    native_pdf(native, [png_bytes(cropped.resize((240, 160), Image.LANCZOS))])
    docx = docx_with_vml_crop(
        png_bytes(src), croptop="6554f", cropbottom="6554f", cropleft="6554f", cropright="6554f"
    )
    report = restore_source_images(docx, native, out)
    assert report.restored == 1
    w, h = pdf_images(out)[0][:2]
    assert abs(w - 480) <= 2 and abs(h - 320) <= 2


def test_dib_inside_wmf_is_restored(paths):
    native, out = paths
    src = graph(5, size=(320, 240))
    native_pdf(native, [jpeg_bytes(src.resize((160, 120), Image.LANCZOS), q=80)])
    report = restore_source_images(docx_with_wmf(wmf_with_dib(src)), native, out)
    assert report.restored == 1
    assert pdf_images(out)[0][:2] == (320, 240)
    assert mean_abs_diff(pdf_pixels(out), src) == 0


def test_look_alike_graphs_each_map_to_their_own_source(paths):
    native, out = paths
    srcs = [graph(s) for s in (11, 12, 13)]
    native_pdf(native, [png_bytes(s.resize((300, 200), Image.LANCZOS)) for s in srcs])
    # DOCX lists the sources in a different order than the PDF pages
    docx = docx_with_pictures([png_bytes(srcs[2]), png_bytes(srcs[0]), png_bytes(srcs[1])])
    report = restore_source_images(docx, native, out)
    assert report.restored == 3
    for i, s in enumerate(srcs):
        assert mean_abs_diff(pdf_pixels(out, i), s) == 0


def test_ambiguous_match_is_skipped(paths):
    native, out = paths
    a = graph(21)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([10, 10, 39, 29], fill="black")  # ~0.7 % of the content pixels strongly different
    native_pdf(native, [png_bytes(a.resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(a), png_bytes(b)]), native, out)
    assert report.ambiguous == 1 and report.restored == 0
    assert pdf_images(out)[0][:2] == (300, 200)


def test_clearly_different_look_alike_does_not_block_restoration(paths):
    # #214, #219: a twin that differs by over 1 % of its content pixels is a different picture, not a rival for the exact match
    native, out = paths
    a = graph(21)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([10, 10, 79, 49], fill="black")
    native_pdf(native, [png_bytes(a.resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(a), png_bytes(b)]), native, out)
    assert report.ambiguous == 0 and report.restored == 1
    assert mean_abs_diff(pdf_pixels(out, 0), a) == 0


def test_near_twin_panels_are_told_apart_by_their_content_pixels(paths):
    # #219: the twins differ in 4 digit blocks, under 1 % of the whole image but about a tenth of the content pixels
    native, out = paths
    a = panel([0, 0, 0, 0, 0, 0, 0, 0])
    b = panel([1, 2, 4, 8, 0, 0, 0, 0])
    native_pdf(native, [png_bytes(a.resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(b), png_bytes(a)]), native, out)
    assert report.ambiguous == 0 and report.restored == 1
    assert mean_abs_diff(pdf_pixels(out, 0), a) == 0


def test_unrelated_image_is_unmatched(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(31).resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(graph(32))]), native, out)
    assert report.unmatched == 1 and report.restored == 0


def test_smaller_source_never_replaces_larger_pdf_image(paths):
    native, out = paths
    small = graph(41, size=(150, 100))
    big = small.resize((600, 400), Image.LANCZOS)
    native_pdf(native, [png_bytes(big)])
    report = restore_source_images(docx_with_pictures([png_bytes(small)]), native, out)
    assert report.restored == 0
    assert pdf_images(out)[0][:2] == (600, 400)


def test_alpha_is_preserved(paths):
    native, out = paths
    src = graph(51).convert("RGBA")
    ImageDraw.Draw(src).rectangle([0, 0, 9, 9], fill=(255, 255, 255, 0))
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert report.restored == 1
    with fitz.open(out) as doc:
        im = doc[0].get_images(full=True)[0]
        assert im[1] != 0  # SMask present
        assert (im[2], im[3]) == (600, 400)
        mask = fitz.Pixmap(doc, im[1])
        assert (mask.width, mask.height) == (600, 400)
        assert mask.samples[0] == 0 and mask.samples[mask.width * 200 + 300] == 255


def logo(seed: int, size=(600, 400)) -> Image.Image:
    """Logo-like RGBA picture: mostly transparent background, a few opaque coloured blocks."""
    rnd = random.Random(seed)
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for _ in range(5):
        x, y = rnd.randint(0, size[0] // 2), rnd.randint(0, size[1] // 2)
        w, h = rnd.randint(size[0] // 5, size[0] // 2), rnd.randint(size[1] // 5, size[1] // 2)
        d.rectangle([x, y, x + w, y + h], fill=(rnd.randint(0, 200), rnd.randint(0, 200), rnd.randint(0, 200), 255))
    return im


def test_transparent_background_logo_is_restored_and_keeps_transparency(paths):
    native, out = paths
    src = logo(61)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert report.restored == 1 and report.unmatched == 0
    with fitz.open(out) as doc:
        im = doc[0].get_images(full=True)[0]
        assert im[1] != 0  # SMask kept
        assert (im[2], im[3]) == (600, 400)


def test_different_transparent_logo_of_same_size_is_unmatched(paths):
    native, out = paths
    native_pdf(native, [png_bytes(logo(62).resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(logo(63))]), native, out)
    assert report.unmatched == 1 and report.restored == 0


def test_self_check_rejects_payload_that_does_not_match(paths, monkeypatch):
    native, out = paths
    src = graph(61)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    # Private seam on purpose: a payload that disagrees with Word's pixels cannot be produced through the
    # public interface, because the encoder derives it from the very source that was matched.
    monkeypatch.setattr(ir, "_encode_payload", lambda source, pixels: png_bytes(graph(99)))
    report = restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert report.self_check_rejected == 1 and report.restored == 0
    assert pdf_images(out)[0][:2] == (300, 200)


def test_restoring_a_restored_pdf_is_a_no_op(paths, tmp_path):
    native, out = paths
    src = graph(71)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    docx = docx_with_pictures([png_bytes(src)])
    restore_source_images(docx, native, out)
    again = restore_source_images(docx, out, tmp_path / "again.pdf")
    assert again.restored == 0


def test_cropped_jpeg_is_reencoded_as_jpeg_not_lossless(paths):
    native, out = paths
    src = graph(81)
    jpg = jpeg_bytes(src, q=90)
    native_pdf(native, [jpeg_bytes(Image.open(io.BytesIO(jpg)).crop((60, 40, 540, 360)).resize((240, 160)))])
    docx = docx_with_srccrop(jpg, l=10000, t=10000, r=10000, b=10000)
    report = restore_source_images(docx, native, out)
    assert report.restored == 1
    assert "DCT" in pdf_images(out)[0][2]
    assert pdf_images(out)[0][:2] == (480, 320)


# ---------------------------------------------------------------- safety


def test_inputs_are_never_modified_and_no_temp_left(paths):
    native, out = paths
    src = graph(91)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    before = native.read_bytes()
    restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert native.read_bytes() == before
    assert leftovers(out.parent) == []


def test_corrupt_docx_snapshot_raises_and_leaves_no_files(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(1).resize((300, 200)))])
    with pytest.raises(RestorationError):
        restore_source_images(b"not a zip", native, out)
    assert not out.exists()
    assert leftovers(out.parent) == []


def test_gate_failure_raises_and_leaves_no_files(paths, monkeypatch):
    native, out = paths
    src = graph(2)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])

    def boom(*_a, **_k):
        raise RestorationError("tampered")

    monkeypatch.setattr(ir, "verify_invariance", boom)
    with pytest.raises(RestorationError):
        restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert not out.exists()
    assert leftovers(out.parent) == []


def test_invariance_gate_accepts_identical_and_rejects_tampered(tmp_path):
    a = native_pdf(tmp_path / "a.pdf", [png_bytes(graph(1))])
    same = tmp_path / "same.pdf"
    same.write_bytes(a.read_bytes())
    verify_invariance(a, same)  # no raise

    def tampered(name: str, mutate) -> Path:
        p = tmp_path / name
        with fitz.open(a) as d:
            mutate(d)
            d.save(p)
        return p

    cases = {
        "text": lambda d: d[0].insert_text((50, 400), "extra"),
        "link": lambda d: d[0].insert_link(
            {"kind": fitz.LINK_URI, "from": fitz.Rect(1, 1, 20, 20), "uri": "https://evil"}
        ),
        "annot": lambda d: d[0].add_text_annot((300, 400), "note"),
        "page": lambda d: d.new_page(),
        "placement": lambda d: d[0].insert_image(fitz.Rect(400, 400, 500, 500), stream=png_bytes(graph(2))),
    }
    for name, mutate in cases.items():
        with pytest.raises(RestorationError):
            verify_invariance(a, tampered(f"{name}.pdf", mutate))


# ---------------------------------------------------------------- review follow-ups


def test_smaller_lossless_source_never_replaces_larger_jpeg_pdf_image(paths):
    native, out = paths
    small = graph(101, size=(150, 100))
    native_pdf(native, [jpeg_bytes(small.resize((600, 400), Image.LANCZOS), q=70)])
    report = restore_source_images(docx_with_pictures([png_bytes(small)]), native, out)
    assert report.restored == 0
    assert pdf_images(out)[0][:2] == (600, 400)
    assert "DCT" in pdf_images(out)[0][2]


def test_idempotent_for_lossless_over_jpeg_and_cropped_jpeg(paths, tmp_path):
    native, out = paths
    src = graph(111)
    native_pdf(native, [jpeg_bytes(src, q=40)])
    docx = docx_with_pictures([png_bytes(src)])
    assert restore_source_images(docx, native, out).restored == 1
    assert restore_source_images(docx, out, tmp_path / "again.pdf").restored == 0

    jpg = jpeg_bytes(graph(112), q=90)
    crop = Image.open(io.BytesIO(jpg)).crop((60, 40, 540, 360))
    native2, out2 = tmp_path / "n2.pdf", tmp_path / "o2.pdf"
    native_pdf(native2, [jpeg_bytes(crop.resize((240, 160)))])
    docx2 = docx_with_srccrop(jpg, l=10000, t=10000, r=10000, b=10000)
    assert restore_source_images(docx2, native2, out2).restored == 1
    assert restore_source_images(docx2, out2, tmp_path / "again2.pdf").restored == 0


def test_failure_while_rewriting_an_xobject_raises_instead_of_reporting_unmatched(paths, monkeypatch):
    native, out = paths
    src = graph(121)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    real = fitz.Document.xref_set_key
    calls = {"n": 0}

    def flaky(self, xref, key, value):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("disk on fire")
        return real(self, xref, key, value)

    monkeypatch.setattr(fitz.Document, "xref_set_key", flaky)
    with pytest.raises(RestorationError):
        restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert not out.exists()
    assert leftovers(out.parent) == []


def test_invariance_gate_rejects_changed_internal_link(tmp_path):
    def build(name: str, target: int) -> Path:
        d = fitz.open()
        d.new_page()
        d.new_page()
        d[0].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(10, 10, 60, 40), "page": target})
        p = tmp_path / name
        d.save(p)
        d.close()
        return p

    with pytest.raises(RestorationError):
        verify_invariance(build("a.pdf", 1), build("b.pdf", 0))


def test_opaque_source_removes_old_smask(paths):
    native, out = paths
    src = graph(131)
    rgba = src.resize((300, 200), Image.LANCZOS).convert("RGBA")
    native_pdf(native, [png_bytes(rgba)])
    with fitz.open(native) as d:
        assert d[0].get_images(full=True)[0][1] != 0  # Word-style copy carries an SMask
    assert restore_source_images(docx_with_pictures([png_bytes(src)]), native, out).restored == 1
    with fitz.open(out) as d:
        assert d[0].get_images(full=True)[0][1] == 0


def test_same_xref_on_two_pages_is_rewritten_once_and_smasks_are_not_counted(paths):
    native, out = paths
    src = graph(141).convert("RGBA")
    data = png_bytes(src.resize((300, 200), Image.LANCZOS))
    doc = fitz.open()
    first = doc.new_page()
    xref = first.insert_image(fitz.Rect(50, 100, 350, 300), stream=data)
    second = doc.new_page()
    second.insert_image(fitz.Rect(50, 100, 350, 300), xref=xref)
    doc.save(native)
    doc.close()
    report = restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert report.images_total == 1 and report.restored == 1  # SMask not counted, shared xref once


def test_negative_crop_and_external_link_are_skipped(paths):
    native, out = paths
    src = graph(151)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    docx = docx_with_srccrop(png_bytes(src), l=-5000)  # padding crop: not representable
    assert restore_source_images(docx, native, out).unmatched == 1
    assert ir.harvest_sources(docx) == []


def test_header_pictures_are_harvested():
    doc = Document()
    hdr = doc.sections[0].header
    hdr.paragraphs[0].add_run().add_picture(io.BytesIO(png_bytes(graph(161))))
    out = io.BytesIO()
    doc.save(out)
    assert len(ir.harvest_sources(out.getvalue())) == 1


# ---------------------------------------------------------------- picture stamps (#214, ADR 0012)


def tag_figures(path: Path, stamps: list[str], before_image: bytes = b"") -> Path:
    """Tag each page's picture as a figure whose /Alt is the given stamp, the way Word's tagged export does."""
    import re

    with fitz.open(path) as doc:
        root = doc.get_new_xref()
        doc.update_object(root, "<<>>")
        elems = []
        for page, stamp in zip(doc, stamps):
            page.clean_contents()
            xref = page.get_contents()[0]
            content = re.sub(rb"(/\S+ Do)", rb"/P <</MCID 0>> BDC " + before_image + rb"\1 EMC", doc.xref_stream(xref))
            doc.update_stream(xref, content)
            elem = doc.get_new_xref()
            doc.update_object(
                elem, f"<</Type/StructElem/S/Figure/Alt({stamp})/K 0/Pg {page.xref} 0 R/P {root} 0 R>>"
            )
            elems.append(elem)
        doc.update_object(
            root, "<</Type/StructTreeRoot/K[" + " ".join(f"{e} 0 R" for e in elems) + "]>>"
        )
        doc.xref_set_key(doc.pdf_catalog(), "StructTreeRoot", f"{root} 0 R")
        doc.saveIncr()
    return path


def figure_alts(path: Path) -> list[str]:
    with fitz.open(path) as doc:
        return [
            doc.xref_get_key(x, "Alt")[1]
            for x in range(1, doc.xref_length())
            if doc.xref_get_key(x, "S")[1] == "/Figure" and doc.xref_get_key(x, "Alt")[0] == "string"
        ]


def test_stamp_resolves_a_look_alike_pair_pixels_cannot(paths):
    native, out = paths
    a = graph(21)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([10, 10, 39, 29], fill="black")  # ~0.7 % of content apart: pixels call it ambiguous
    docx = docx_with_pictures([png_bytes(a), png_bytes(b)])
    native_pdf(native, [png_bytes(b.resize((300, 200), Image.LANCZOS))])
    tag_figures(native, ["PSRID:2"])  # the second picture in the DOCX
    report = restore_source_images(docx, native, out)
    assert (report.ambiguous, report.restored) == (0, 1)
    assert report.entries[0].evidence == "id"
    assert mean_abs_diff(pdf_pixels(out, 0), b) == 0


def test_stamp_that_disagrees_with_the_pixels_keeps_words_copy(paths):
    native, out = paths
    shown, other = graph(31), graph(32)
    docx = docx_with_pictures([png_bytes(other), png_bytes(shown)])
    native_pdf(native, [png_bytes(shown.resize((300, 200), Image.LANCZOS))])
    tag_figures(native, ["PSRID:1"])  # points at `other`; a correct source exists but the stamp is not trusted
    report = restore_source_images(docx, native, out)
    assert (report.unmatched, report.restored) == (1, 0)
    assert pdf_images(out)[0][:2] == (300, 200)


def test_stamps_are_removed_from_the_output(paths):
    native, out = paths
    src = graph(1)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    tag_figures(native, ["PSRID:1"])
    restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert figure_alts(out) == []


def test_unstamped_pdf_still_matches_by_pixels(paths):
    native, out = paths
    src = graph(1)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    report = restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert report.restored == 1 and report.entries[0].evidence == "pixels"


def test_export_copy_stamps_each_picture_and_leaves_the_original(tmp_path):
    import zipfile

    from src.postprocessing.converters import make_export_copy

    src, dst = tmp_path / "a.docx", tmp_path / "b.docx"
    src.write_bytes(docx_with_pictures([png_bytes(graph(1)), png_bytes(graph(2))]))
    before = src.read_bytes()
    assert make_export_copy(src, dst) == (0, 2)
    assert src.read_bytes() == before
    with zipfile.ZipFile(dst) as zf:
        xml = zf.read("word/document.xml").decode()
    assert 'descr="PSRID:1"' in xml and 'descr="PSRID:2"' in xml
    # the stamps the copy carries mean the same pictures restoration harvests from the original
    ids = ir._harvest(before).ids
    assert sorted(ids) == [1, 2] and all(len(v.sources) == 1 for v in ids.values())


def test_shared_pdf_image_with_several_stamps_is_matched_among_all_of_them():
    # Word stores identical pictures once, so one image can carry the stamps of several DOCX pictures
    def src(label):
        return ir._Source(label, b"", (10, 10), True, None, Image.new("L", (64, 64)))

    a, b, c = src("a"), src("b"), src("c")
    ids = {1: ir._PictureId((a,), ""), 2: ir._PictureId((b,), ""), 3: ir._PictureId((c,), "")}
    assert ir._id_candidates({1, 2}, ids) == [a, b]
    assert ir._id_candidates({1, 9}, ids) is None  # a stamp the DOCX does not explain: do not narrow
    assert ir._id_candidates(None, ids) is None


def test_images_inside_a_form_are_found_through_the_form(tmp_path):
    # Word draws metafile pictures (FLIR previews) as a form XObject that holds the images
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(10, 10, 110, 110), stream=png_bytes(graph(3, (100, 100))))
    image = page.get_images(full=True)[0][0]
    form = doc.get_new_xref()
    doc.update_object(form, f"<</Type/XObject/Subtype/Form/BBox[0 0 10 10]/Resources<</XObject<</Im0 {image} 0 R>>>>>>")
    doc.update_stream(form, b"q /Im0 Do Q")
    assert ir._images_drawn_by(doc, form, set()) == {image}
    assert ir._images_drawn_by(doc, image, set()) == {image}


def test_export_copy_stamps_a_vml_picture_with_alt(tmp_path):
    import zipfile

    from src.postprocessing.converters import make_export_copy

    src, dst = tmp_path / "a.docx", tmp_path / "b.docx"
    src.write_bytes(docx_with_vml_crop(png_bytes(graph(1)), cropleft="1000f"))
    assert make_export_copy(src, dst) == (0, 1)
    with zipfile.ZipFile(dst) as zf:
        assert 'alt="PSRID:1"' in zf.read("word/document.xml").decode()
    ids = ir._harvest(src.read_bytes()).ids
    assert list(ids) == [1] and len(ids[1].sources) == 1


def test_stamped_picture_stretched_by_word_is_still_restored(paths):
    # #214: PRPD screenshots are squashed on the page, so Word's copy has a different aspect than the source
    native, out = paths
    src = graph(5, size=(600, 424))
    native_pdf(native, [png_bytes(src.resize((300, 125), Image.LANCZOS))])
    docx = docx_with_pictures([png_bytes(src)])
    unstamped = restore_source_images(docx, native, out)
    assert (unstamped.unmatched, unstamped.restored) == (1, 0)  # aspect check still guards unstamped images
    tag_figures(native, ["PSRID:1"])
    report = restore_source_images(docx, native, out)
    assert (report.restored, report.entries[0].evidence) == (1, "id")
    assert pdf_images(out)[0][:2] == (600, 424)


def test_stamped_but_different_picture_is_not_restored_despite_stretch(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(6, size=(600, 424)).resize((300, 125), Image.LANCZOS))])
    tag_figures(native, ["PSRID:1"])
    report = restore_source_images(docx_with_pictures([png_bytes(graph(7, size=(600, 424)))]), native, out)
    assert (report.unmatched, report.restored) == (1, 0)


def native_pdf_sharing_one_image(path: Path, data: bytes, pages: int) -> Path:
    """Word stores a picture once and draws it on every page that uses it."""
    doc = fitz.open()
    xref = 0
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        xref = page.insert_image(fitz.Rect(50, 100, 350, 300), stream=data) if not xref else xref
        if page.number:
            page.insert_image(fitz.Rect(50, 100, 350, 300), xref=xref)
    doc.save(path)
    doc.close()
    return path


def test_two_stamps_that_name_look_alike_pictures_stay_ambiguous(paths):
    native, out = paths
    a = graph(21)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([10, 10, 39, 29], fill="black")  # ~0.7 % of content apart
    native_pdf_sharing_one_image(native, png_bytes(b.resize((300, 200), Image.LANCZOS)), pages=2)
    tag_figures(native, ["PSRID:1", "PSRID:2"])  # the one stored image is drawn as picture 1 and as picture 2
    report = restore_source_images(docx_with_pictures([png_bytes(a), png_bytes(b)]), native, out)
    assert (report.ambiguous, report.restored) == (1, 0)
    assert pdf_images(out)[0][:2] == (300, 200)


def test_image_also_drawn_without_a_stamp_is_not_narrowed_by_the_stamp(paths):
    native, out = paths
    src = graph(8)
    native_pdf_sharing_one_image(native, png_bytes(src.resize((300, 200), Image.LANCZOS)), pages=2)
    tag_figures(native, ["PSRID:1"])  # page 2 draws the same image untagged
    report = restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert report.entries[0].evidence == "pixels"


def test_stamp_is_removed_even_when_the_figure_link_is_not_simple(paths):
    native, out = paths
    src = graph(1)
    native_pdf(native, [png_bytes(src.resize((300, 200), Image.LANCZOS))])
    tag_figures(native, ["PSRID:1"])
    with fitz.open(native) as doc:
        elem = next(x for x in range(1, doc.xref_length()) if doc.xref_get_key(x, "S")[1] == "/Figure")
        doc.xref_set_key(elem, "K", "[0 7]")
        doc.saveIncr()
    restore_source_images(docx_with_pictures([png_bytes(src)]), native, out)
    assert figure_alts(out) == []


def test_original_description_survives_when_a_drawing_has_no_picture():
    from docx import Document as Doc

    doc = Doc()
    run = parse_xml(
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        '<w:drawing><wp:inline><wp:extent cx="1" cy="1"/><wp:docPr id="9" name="x" descr="keep me"/></wp:inline>'
        "</w:drawing></w:r>"
    )
    doc.add_paragraph()._p.append(run)
    out = io.BytesIO()
    doc.save(out)
    ids = ir._harvest(out.getvalue()).ids
    assert ids[1].original == "keep me" and ids[1].sources == ()


# ---------------------------------------------------------------- stamps never reach a delivered PDF (#215)


def all_alts(path: Path) -> list[str]:
    with fitz.open(path) as doc:
        return [
            doc.xref_get_key(x, "Alt")[1]
            for x in range(1, doc.xref_length())
            if doc.xref_get_key(x, "Alt")[0] == "string"
        ]


def docx_with_description(descr: str) -> bytes:
    data = docx_with_pictures([png_bytes(graph(1))])
    import zipfile

    src, out = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            blob = src.read(info.filename)
            if info.filename == "word/document.xml":
                blob = blob.replace(b"<wp:docPr ", f'<wp:docPr descr="{descr}" '.encode(), 1)
            dst.writestr(info, blob)
    return out.getvalue()


def test_strip_picture_stamps_restores_the_original_description(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(1))])
    tag_figures(native, ["PSRID:1"])
    removed = ir.strip_picture_stamps(native, out, docx_with_description("Thermogram of busbar"))
    assert removed == 1 and all_alts(out) == ["Thermogram of busbar"]


def test_strip_picture_stamps_clears_when_the_docx_is_unreadable(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(1))])
    tag_figures(native, ["PSRID:1"])
    assert ir.strip_picture_stamps(native, out, b"not a docx") == 1
    assert all_alts(out) == []


def test_strip_picture_stamps_finds_a_stamp_on_any_element_type(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(1))])
    tag_figures(native, ["PSRID:1"])
    with fitz.open(native) as doc:
        elem = next(x for x in range(1, doc.xref_length()) if doc.xref_get_key(x, "S")[1] == "/Figure")
        doc.xref_set_key(elem, "S", "/Span")
        doc.saveIncr()
    ir.strip_picture_stamps(native, out, None)
    assert all_alts(out) == []


def test_strip_picture_stamps_keeps_a_title_Word_combined_with_the_stamp(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(1))])
    tag_figures(native, ["Photo title. PSRID:1"])
    ir.strip_picture_stamps(native, out, docx_with_description("the original"))
    assert all_alts(out) == ["Photo title. the original"]


def test_strip_picture_stamps_writes_nothing_without_a_stamp(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(1))])
    assert ir.strip_picture_stamps(native, out, None) == 0
    assert not out.exists()


# ---------------------------------------------------------------- groups and canvases (#216)

_GROUP_NS = (
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
    'xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"'
)


def docx_with_group(pictures: list[bytes], container: str = "wpg:wgp") -> bytes:
    """One drawing (one ``wp:docPr``) whose group or canvas holds every picture."""
    doc = Document()
    pics = ""
    for k, data in enumerate(pictures):
        rid, _ = doc.part.get_or_add_image(io.BytesIO(data))
        pics += (
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{k}" name="p{k}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm></pic:spPr></pic:pic>'
        )
    run = parse_xml(
        f'<w:r {NS} {_GROUP_NS}><w:drawing><wp:inline><wp:extent cx="1" cy="1"/><wp:docPr id="1" name="Group"/>'
        f'<a:graphic><a:graphicData><{container}>{pics}</{container}></a:graphicData></a:graphic></wp:inline>'
        f"</w:drawing></w:r>"
    )
    doc.add_paragraph()._p.append(run)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


@pytest.mark.parametrize("container", ["wpg:wgp", "wpc:wpc"])
def test_group_or_canvas_stamp_names_every_picture_inside(container):
    a, b = graph(41), graph(42)
    docx = docx_with_group([png_bytes(a), png_bytes(b)], container)
    ids = ir._harvest(docx).ids
    assert list(ids) == [1] and len(ids[1].sources) == 2


@pytest.mark.parametrize("container", ["wpg:wgp", "wpc:wpc"])
def test_pictures_in_a_group_or_canvas_each_restore_to_their_own_source(paths, container):
    native, out = paths
    a, b = graph(41), graph(42)
    docx = docx_with_group([png_bytes(a), png_bytes(b)], container)
    native_pdf(
        native,
        [png_bytes(a.resize((300, 200), Image.LANCZOS)), png_bytes(b.resize((300, 200), Image.LANCZOS))],
    )
    tag_figures(native, ["PSRID:1", "PSRID:1"])  # Word tags the group as one figure: every picture carries its stamp
    report = restore_source_images(docx, native, out)
    assert (report.restored, report.unmatched) == (2, 0)
    assert all(e.evidence == "id" for e in report.entries)
    assert mean_abs_diff(pdf_pixels(out, 0), a) == 0
    assert mean_abs_diff(pdf_pixels(out, 1), b) == 0


def test_group_with_an_untraceable_picture_does_not_narrow():
    import zipfile

    src = io.BytesIO(docx_with_group([png_bytes(graph(41)), png_bytes(graph(42))]))
    docx = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(docx, "w") as zout:
        media = sorted(n for n in zin.namelist() if n.startswith("word/media/"))
        for n in zin.namelist():
            zout.writestr(n, b"not an image" if n == media[1] else zin.read(n))
    docx = docx.getvalue()
    assert ir._harvest(docx).ids[1].sources == ()


# ---------------------------------------------------------------- exact page-content reading (#217)


def test_image_drawn_after_nested_marked_content_is_traced_to_its_stamp(paths):
    native, out = paths
    a = graph(21)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([10, 10, 39, 29], fill="black")  # look-alike pair: only the stamp can choose
    docx = docx_with_pictures([png_bytes(a), png_bytes(b)])
    native_pdf(native, [png_bytes(b.resize((300, 200), Image.LANCZOS))])
    tag_figures(native, ["PSRID:2"], before_image=b"/Span <</ActualText (x)>> BDC EMC /Artifact BMC /Artifact BMC EMC EMC ")
    report = restore_source_images(docx, native, out)
    assert (report.ambiguous, report.restored) == (0, 1)
    assert report.entries[0].evidence == "id"


def test_text_that_looks_like_marked_content_operators_is_not_read_as_them(paths):
    native, out = paths
    a = graph(21)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([10, 10, 39, 29], fill="black")
    docx = docx_with_pictures([png_bytes(a), png_bytes(b)])
    native_pdf(native, [png_bytes(b.resize((300, 200), Image.LANCZOS))])
    tag_figures(native, ["PSRID:2"], before_image=b"(EMC) Tj ")
    report = restore_source_images(docx, native, out)
    assert (report.restored, report.entries[0].evidence) == (1, "id")


def test_form_is_credited_only_with_the_images_it_draws():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(10, 10, 60, 60), stream=png_bytes(graph(3, (100, 100))))
    page.insert_image(fitz.Rect(70, 10, 120, 60), stream=png_bytes(graph(4, (100, 100))))
    drawn, idle = [i[0] for i in page.get_images(full=True)]
    form = doc.get_new_xref()
    doc.update_object(
        form,
        f"<</Type/XObject/Subtype/Form/BBox[0 0 10 10]/Resources<</XObject<</Im0 {drawn} 0 R/Im1 {idle} 0 R>>>>>>",
    )
    doc.update_stream(form, b"q /Im0 Do Q")
    assert ir._images_drawn_by(doc, form, set()) == {drawn}


def test_form_nested_in_a_form_is_followed_only_where_drawn():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(10, 10, 60, 60), stream=png_bytes(graph(3, (100, 100))))
    image = page.get_images(full=True)[0][0]
    inner = doc.get_new_xref()
    doc.update_object(inner, f"<</Type/XObject/Subtype/Form/BBox[0 0 10 10]/Resources<</XObject<</Im0 {image} 0 R>>>>>>")
    doc.update_stream(inner, b"q /Im0 Do Q")
    outer = doc.get_new_xref()
    doc.update_object(outer, f"<</Type/XObject/Subtype/Form/BBox[0 0 10 10]/Resources<</XObject<</F0 {inner} 0 R>>>>>>")
    doc.update_stream(outer, b"q /F0 Do Q")
    unused = doc.get_new_xref()
    doc.update_object(unused, f"<</Type/XObject/Subtype/Form/BBox[0 0 10 10]/Resources<</XObject<</F0 {inner} 0 R>>>>>>")
    doc.update_stream(unused, b"q Q")
    assert ir._images_drawn_by(doc, outer, set()) == {image}
    assert ir._images_drawn_by(doc, unused, set()) == set()


def test_marked_content_operators_inside_names_and_escaped_strings_are_ignored(paths):
    native, out = paths
    a = graph(21)
    b = a.copy()
    ImageDraw.Draw(b).rectangle([10, 10, 39, 29], fill="black")
    docx = docx_with_pictures([png_bytes(a), png_bytes(b)])
    native_pdf(native, [png_bytes(b.resize((300, 200), Image.LANCZOS))])
    tag_figures(native, ["PSRID:2"], before_image=b"/EMC gs (a\) EMC) Tj /P <</MCID 7>> BDC EMC ")
    report = restore_source_images(docx, native, out)
    assert (report.restored, report.entries[0].evidence) == (1, "id")


# ---------------------------------------------------------------- inferring a missing stamp (#218, ADR 0012)


def tagged_pages(path: Path, pages: list[list[tuple[bytes, str | None]]]) -> Path:
    """One PDF page per list, drawing its pictures in order; a picture with a stamp is tagged as that figure."""
    import re

    doc = fitz.open()
    for items in pages:
        page = doc.new_page(width=595, height=842)
        for k, (data, _) in enumerate(items):
            page.insert_image(fitz.Rect(20, 20 + 120 * k, 200, 120 + 120 * k), stream=data)
    root = doc.get_new_xref()
    doc.update_object(root, "<<>>")
    elems = []
    for page, items in zip(doc, pages):
        page.clean_contents()
        xref = page.get_contents()[0]
        parts = re.split(rb"(/\S+ Do)", doc.xref_stream(xref))
        out, k = [], -1
        for chunk in parts:
            if chunk.endswith(b" Do") and chunk.startswith(b"/"):
                k += 1
                stamp = items[k][1]
                if stamp is not None:
                    chunk = b"/P <</MCID %d>> BDC " % k + chunk + b" EMC"
                    elem = doc.get_new_xref()
                    doc.update_object(
                        elem, f"<</Type/StructElem/S/Figure/Alt({stamp})/K {k}/Pg {page.xref} 0 R/P {root} 0 R>>"
                    )
                    elems.append(elem)
            out.append(chunk)
        doc.update_stream(xref, b"".join(out))
    doc.update_object(root, "<</Type/StructTreeRoot/K[" + " ".join(f"{e} 0 R" for e in elems) + "]>>")
    doc.xref_set_key(doc.pdf_catalog(), "StructTreeRoot", f"{root} 0 R")
    doc.save(path)
    doc.close()
    return path


def _look_alike(img: Image.Image) -> Image.Image:
    twin = img.copy()
    ImageDraw.Draw(twin).rectangle([10, 10, 39, 29], fill="black")  # ~0.7 % of content apart: pixels call the pair ambiguous
    return twin


def _small(img: Image.Image) -> bytes:
    return png_bytes(img.resize((300, 200), Image.LANCZOS))


def test_single_gap_infers_the_missing_stamp(paths):
    native, out = paths
    a, b, c = graph(51), graph(52), graph(53)
    docx = docx_with_pictures([png_bytes(a), png_bytes(b), png_bytes(c), png_bytes(_look_alike(b))])
    tagged_pages(native, [[(_small(a), "PSRID:1"), (_small(b), None), (_small(c), "PSRID:3")]])
    report = restore_source_images(docx, native, out)
    assert [e.action for e in report.entries] == ["restored"] * 3
    assert report.entries[1].evidence == "id"
    assert mean_abs_diff(pdf_pixels(out, 1), b) == 0  # not the twin that pixels alone cannot tell from it


def test_two_images_in_the_gap_are_not_inferred(paths):
    native, out = paths
    a, b, c, x = graph(51), graph(52), graph(53), graph(54)
    docx = docx_with_pictures([png_bytes(a), png_bytes(b), png_bytes(c), png_bytes(_look_alike(b)), png_bytes(x)])
    tagged_pages(
        native, [[(_small(a), "PSRID:1"), (_small(b), None), (_small(x), None), (_small(c), "PSRID:3")]]
    )
    report = restore_source_images(docx, native, out)
    assert report.entries[1].action == "ambiguous" and report.entries[1].evidence == "pixels"


def test_two_drawings_in_the_gap_are_not_inferred(paths):
    native, out = paths
    a, b, c, e = graph(51), graph(52), graph(53), graph(55)
    docx = docx_with_pictures([png_bytes(a), png_bytes(b), png_bytes(e), png_bytes(c), png_bytes(_look_alike(b))])
    tagged_pages(native, [[(_small(a), "PSRID:1"), (_small(b), None), (_small(c), "PSRID:4")]])
    report = restore_source_images(docx, native, out)
    assert report.entries[1].action == "ambiguous" and report.entries[1].evidence == "pixels"


def test_neighbours_on_different_pages_are_not_inferred(paths):
    native, out = paths
    a, b, c = graph(51), graph(52), graph(53)
    docx = docx_with_pictures([png_bytes(a), png_bytes(b), png_bytes(c), png_bytes(_look_alike(b))])
    tagged_pages(native, [[(_small(a), "PSRID:1"), (_small(b), None)], [(_small(c), "PSRID:3")]])
    report = restore_source_images(docx, native, out)
    assert report.entries[1].action == "ambiguous" and report.entries[1].evidence == "pixels"


@pytest.mark.parametrize("where", ["before", "after"])
def test_a_missing_neighbour_is_not_inferred(paths, where):
    native, out = paths
    a, b, c = graph(51), graph(52), graph(53)
    docx = docx_with_pictures([png_bytes(a), png_bytes(b), png_bytes(c), png_bytes(_look_alike(b))])
    items = [(_small(a), "PSRID:1"), (_small(b), None)] if where == "after" else [(_small(b), None), (_small(c), "PSRID:3")]
    tagged_pages(native, [items])
    report = restore_source_images(docx, native, out)
    unstamped = next(e for e in report.entries if e.action == "ambiguous")
    assert unstamped.evidence == "pixels"


def test_an_inferred_source_that_disagrees_with_the_pixels_keeps_words_copy(paths):
    native, out = paths
    a, b, c, z = graph(51), graph(52), graph(53), graph(56)
    docx = docx_with_pictures([png_bytes(a), png_bytes(b), png_bytes(c), png_bytes(z)])
    tagged_pages(native, [[(_small(a), "PSRID:1"), (_small(z), None), (_small(c), "PSRID:3")]])
    report = restore_source_images(docx, native, out)
    assert report.entries[1].action == "unmatched"  # inferred drawing 2 is not what Word drew; no other try


def test_inference_stays_inside_the_main_document_and_off_drawings_already_stamped():
    events = [({1}, 1), ({2}, None), ({3}, 3)]
    assert ir._infer_missing_stamps(events, {1, 3}, body_drawings=3) == {1: 2}
    assert ir._infer_missing_stamps(events, {1, 3}, body_drawings=3) == {1: 2}
    assert ir._infer_missing_stamps(events, {1, 3}, body_drawings=1) == {}  # drawing 2 is a header or footer
    assert ir._infer_missing_stamps([({1}, 1), ({2, 9}, None), ({3}, 3)], {1, 3}, body_drawings=3) == {}  # a form of two images
    assert ir._infer_missing_stamps(events, {1, 2, 3}, body_drawings=3) == {}  # drawing 2 is stamped elsewhere


def test_strip_drops_the_grouped_object_text_Word_adds_after_an_empty_stamp(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(1))])
    tag_figures(native, ["PSRID:1 (Grouped Object)"])
    ir.strip_picture_stamps(native, out, None)
    assert all_alts(out) == []  # an unstamped export has no description on the group


def test_strip_keeps_the_grouped_object_text_after_a_real_description(paths):
    native, out = paths
    native_pdf(native, [png_bytes(graph(1))])
    tag_figures(native, ["PSRID:1 (Grouped Object)"])
    ir.strip_picture_stamps(native, out, docx_with_description("Busbar group"))
    assert all_alts(out) == ["Busbar group (Grouped Object)"]
