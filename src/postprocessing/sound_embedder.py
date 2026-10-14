"""Ultrasound audio processing and ISO 32000-1 PDF sound annotation engine.

Delivers pure-Python in-memory 24-bit to 16-bit PCM downscaling, standalone 16-bit WAV file
export, and low-level PyMuPDF xref sound object & annotation injection.
"""

from __future__ import annotations

from pathlib import Path
import re
import wave

import fitz


def convert_24bit_wav_to_16bit_pcm(wav_path: Path | str) -> tuple[bytes, int, int]:
    """Pure-Python in-memory 24-bit to 16-bit PCM downscaler.

    Reads WAV frames using the standard library `wave` module with zero intermediate disk I/O.
    Discards least-significant byte b0 (sample >> 8) via slice assignment:
      out[0::2] = raw[1::3]
      out[1::2] = raw[2::3]

    Args:
        wav_path: Path to the source WAV file.

    Returns:
        tuple[bytes, int, int]: (pcm_bytes, framerate, nchannels)

    Raises:
        FileNotFoundError: If the file does not exist or has 0 bytes.
        ValueError: If sample width is not 1, 2, or 3.
    """
    path = Path(wav_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"WAV file not found or empty: {path}")

    with wave.open(str(path), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        raw_frames = wf.readframes(nframes)

    if sampwidth == 2:
        return raw_frames, framerate, nchannels
    elif sampwidth == 3:
        num_samples = len(raw_frames) // 3
        out = bytearray(num_samples * 2)
        out[0::2] = raw_frames[1::3]
        out[1::2] = raw_frames[2::3]
        return bytes(out), framerate, nchannels
    elif sampwidth == 1:
        num_samples = len(raw_frames)
        out = bytearray(num_samples * 2)
        for i in range(num_samples):
            val = (raw_frames[i] - 128) << 8
            out[2 * i] = val & 0xFF
            out[2 * i + 1] = (val >> 8) & 0xFF
        return bytes(out), framerate, nchannels
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")


def export_16bit_wav(src_wav_path: Path | str, dest_wav_path: Path | str) -> Path:
    """Downscales a source WAV file to 16-bit PCM and saves it to disk.

    Args:
        src_wav_path: Path to the original WAV file (e.g. 24-bit UltraTEV 8k.wav).
        dest_wav_path: Path where the converted 16-bit WAV file will be written.

    Returns:
        Path: The absolute or normalized Path to the saved 16-bit WAV file.
    """
    pcm_bytes, framerate, nchannels = convert_24bit_wav_to_16bit_pcm(src_wav_path)
    dest_path = Path(dest_wav_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(dest_path), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.setcomptype("NONE", "not compressed")
        wf.writeframes(pcm_bytes)

    return dest_path


def _find_existing_sound_annot(
    doc: fitz.Document,
    page: fitz.Page,
    rect: fitz.Rect,
) -> tuple[int, int] | None:
    r"""Find an existing /Subtype /Sound annotation intersecting rect.

    Inspects both high-level page annotations and low-level page /Annots array objects
    to enforce IdempotentSoundEmbeddingPolicy across all document lifecycle states.

    Returns:
        tuple[int, int] | None: (annot_xref, sound_xref) if found, else None.
    """
    # 1. High-level PyMuPDF annotation inspection
    try:
        for annot in page.annots():
            is_sound = (
                annot.type == (18, "Sound")
                or (isinstance(annot.type, tuple) and len(annot.type) > 1 and annot.type[1] == "Sound")
            )
            if not is_sound:
                st = doc.xref_get_key(annot.xref, "Subtype")
                if st[1] == "/Sound":
                    is_sound = True

            if is_sound and annot.rect.intersects(rect):
                sound_val = doc.xref_get_key(annot.xref, "Sound")
                if sound_val[0] == "xref":
                    sound_xref = int(sound_val[1].split()[0])
                    return annot.xref, sound_xref
    except Exception:
        pass

    # 2. Low-level /Annots xref table inspection (handles uncommitted / re-injected annots)
    annots_type, annots_val = doc.xref_get_key(page.xref, "Annots")
    if annots_type == "xref":
        ref_xref = int(annots_val.split()[0])
        annots_str = doc.xref_object(ref_xref)
    elif annots_type == "array":
        annots_str = annots_val
    else:
        return None

    annot_xrefs = [int(m) for m in re.findall(r"(\d+)\s+0\s+R", annots_str)]
    page_h = page.rect.height

    for candidate_xref in annot_xrefs:
        subtype_info = doc.xref_get_key(candidate_xref, "Subtype")
        if subtype_info[1] == "/Sound":
            r_type, r_val = doc.xref_get_key(candidate_xref, "Rect")
            if r_type == "array":
                nums = [float(x) for x in re.findall(r"[-+]?(?:\d*\.\d+|\d+)", r_val)]
                if len(nums) == 4:
                    pdf_x0, pdf_y0, pdf_x1, pdf_y1 = nums
                    mupdf_rect = fitz.Rect(pdf_x0, page_h - pdf_y1, pdf_x1, page_h - pdf_y0)
                    if mupdf_rect.intersects(rect):
                        sound_val = doc.xref_get_key(candidate_xref, "Sound")
                        if sound_val[0] == "xref":
                            sound_xref = int(sound_val[1].split()[0])
                            return candidate_xref, sound_xref

    return None


def _append_xref_to_array_str(arr_str: str, xref: int) -> str:
    """Append an indirect xref reference to a PDF array string."""
    trimmed = arr_str.strip()
    if trimmed.endswith("]"):
        return trimmed[:-1].rstrip() + f" {xref} 0 R]"
    return f"[{xref} 0 R]"


def _register_annot_xref_to_page(
    doc: fitz.Document,
    page: fitz.Page,
    annot_xref: int,
) -> None:
    """Robustly registers an annotation xref into the page's /Annots array.

    Handles indirect xref arrays, direct inline arrays, and empty/null keys.
    """
    annots_type, annots_val = doc.xref_get_key(page.xref, "Annots")
    if annots_type == "xref":
        ref_xref = int(annots_val.split()[0])
        arr_str = doc.xref_object(ref_xref)
        doc.update_object(ref_xref, _append_xref_to_array_str(arr_str, annot_xref))
    elif annots_type == "array":
        doc.xref_set_key(page.xref, "Annots", _append_xref_to_array_str(annots_val, annot_xref))
    else:
        doc.xref_set_key(page.xref, "Annots", f"[{annot_xref} 0 R]")


def embed_sound_annotation(
    doc: fitz.Document,
    page: fitz.Page,
    rect: fitz.Rect,
    pcm_bytes: bytes,
    framerate: int = 8000,
    channels: int = 1,
) -> int:
    """Embeds an ISO 32000-1 compliant Sound annotation into a PDF page.

    Enforces IdempotentSoundEmbeddingPolicy: If a /Subtype /Sound annotation already
    intersects rect, updates the existing sound object stream directly and returns
    the existing annotation xref without creating duplicate stacked icons or leaking
    unreferenced streams.

    Args:
        doc: PyMuPDF Document object.
        page: PyMuPDF Page object.
        rect: Annotation bounding rectangle in PyMuPDF points (top-left origin).
        pcm_bytes: Converted 16-bit signed PCM audio bytes.
        framerate: Audio sample rate in Hz (default 8000).
        channels: Number of audio channels (default 1 for mono).

    Returns:
        int: Cross-reference integer (xref) of the Sound annotation.
    """
    existing = _find_existing_sound_annot(doc, page, rect)
    if existing is not None:
        annot_xref, sound_xref = existing
        doc.update_stream(sound_xref, pcm_bytes)
        return annot_xref

    # 1. Allocate and populate Sound Object stream
    sound_xref = doc.get_new_xref()
    doc.update_object(
        sound_xref,
        f"<< /Type /Sound /R {framerate} /C {channels} /B 16 /E /Signed >>",
    )
    doc.update_stream(sound_xref, pcm_bytes)

    # 2. Convert PyMuPDF coordinates (top-left origin) to PDF points (bottom-left origin)
    page_h = page.rect.height
    pdf_y0 = page_h - rect.y1
    pdf_y1 = page_h - rect.y0

    # 3. Allocate and populate Sound Annotation dictionary
    annot_xref = doc.get_new_xref()
    annot_dict = (
        f"<< /Type /Annot /Subtype /Sound "
        f"/Rect [{rect.x0:.2f} {pdf_y0:.2f} {rect.x1:.2f} {pdf_y1:.2f}] "
        f"/Sound {sound_xref} 0 R "
        f"/Name /Speaker "
        f"/F 4 "
        f"/P {page.xref} 0 R >>"
    )
    doc.update_object(annot_xref, annot_dict)

    # 4. Register annotation xref into page /Annots
    _register_annot_xref_to_page(doc, page, annot_xref)

    return annot_xref


