from __future__ import annotations

import io
from pathlib import Path
import struct
import wave
import fitz
import pytest

from src.postprocessing.sound_embedder import (
    convert_24bit_wav_to_16bit_pcm,
    export_16bit_wav,
    embed_sound_annotation,
)


def _create_synthetic_wav(
    path: Path,
    sampwidth: int,
    framerate: int,
    channels: int,
    raw_data: bytes,
) -> Path:
    """Helper to write raw PCM frames to a standard RIFF WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.setcomptype("NONE", "not compressed")
        wf.writeframes(raw_data)
    return path


def test_convert_24bit_wav_downscales_to_16bit_exact_samples(tmp_path: Path):
    """Assert 24-bit PCM downscales to 16-bit PCM by shifting right 8 bits (discarding LSB b0)."""
    wav_file = tmp_path / "test_24bit.wav"
    
    # Define known 24-bit signed samples:
    # 1. 0 -> 0x000000
    # 2. +32767 << 8 -> 0x7FFF00 (b0=0x00, b1=0xFF, b2=0x7F) -> 16-bit: +32767 (0x7FFF)
    # 3. -32768 << 8 -> 0x800000 (b0=0x00, b1=0x00, b2=0x80) -> 16-bit: -32768 (0x8000)
    # 4. -1 << 8 -> 0xFFFF00 (b0=0x00, b1=0xFF, b2=0xFF) -> 16-bit: -1 (0xFFFF)
    # 5. Arbitrary sample with non-zero LSB:
    #    0x123456 -> b0=0x56, b1=0x34, b2=0x12 -> 16-bit: 0x1234
    samples_24 = [
        bytes([0x00, 0x00, 0x00]),
        bytes([0x00, 0xFF, 0x7F]),
        bytes([0x00, 0x00, 0x80]),
        bytes([0x00, 0xFF, 0xFF]),
        bytes([0x56, 0x34, 0x12]),
    ]
    raw_24 = b"".join(samples_24)
    _create_synthetic_wav(wav_file, sampwidth=3, framerate=8000, channels=1, raw_data=raw_24)

    pcm_bytes, framerate, channels = convert_24bit_wav_to_16bit_pcm(wav_file)

    assert framerate == 8000
    assert channels == 1
    assert len(pcm_bytes) == len(samples_24) * 2

    # Unpack 16-bit signed little-endian integers
    unpacked_16 = struct.unpack(f"<{len(samples_24)}h", pcm_bytes)
    assert unpacked_16[0] == 0
    assert unpacked_16[1] == 32767
    assert unpacked_16[2] == -32768
    assert unpacked_16[3] == -1
    assert unpacked_16[4] == 0x1234


def test_convert_16bit_wav_passthrough(tmp_path: Path):
    """Assert 16-bit WAV frames pass through directly without modification."""
    wav_file = tmp_path / "test_16bit.wav"
    raw_16 = struct.pack("<4h", 100, -200, 300, -400)
    _create_synthetic_wav(wav_file, sampwidth=2, framerate=16000, channels=1, raw_data=raw_16)

    pcm_bytes, framerate, channels = convert_24bit_wav_to_16bit_pcm(wav_file)

    assert framerate == 16000
    assert channels == 1
    assert pcm_bytes == raw_16


def test_convert_8bit_wav_to_16bit(tmp_path: Path):
    """Assert 8-bit unsigned PCM converts to 16-bit signed PCM."""
    wav_file = tmp_path / "test_8bit.wav"
    # In 8-bit WAV: 128 is zero, 255 is ~+32512, 0 is -32768
    raw_8 = bytes([128, 0, 255])
    _create_synthetic_wav(wav_file, sampwidth=1, framerate=8000, channels=1, raw_data=raw_8)

    pcm_bytes, framerate, channels = convert_24bit_wav_to_16bit_pcm(wav_file)

    assert framerate == 8000
    assert channels == 1
    unpacked_16 = struct.unpack("<3h", pcm_bytes)
    assert unpacked_16[0] == 0
    assert unpacked_16[1] == -32768
    assert unpacked_16[2] == 32512


def test_convert_wav_missing_file_raises_filenotfound(tmp_path: Path):
    missing_file = tmp_path / "non_existent.wav"
    with pytest.raises(FileNotFoundError):
        convert_24bit_wav_to_16bit_pcm(missing_file)


def test_convert_wav_empty_file_raises_filenotfound(tmp_path: Path):
    empty_file = tmp_path / "empty.wav"
    empty_file.write_bytes(b"")
    with pytest.raises(FileNotFoundError):
        convert_24bit_wav_to_16bit_pcm(empty_file)


def test_convert_wav_unsupported_sample_width_raises_value_error(tmp_path: Path):
    wav_file = tmp_path / "test_32bit.wav"
    _create_synthetic_wav(wav_file, sampwidth=4, framerate=8000, channels=1, raw_data=b"\x00" * 16)
    with pytest.raises(ValueError, match="Unsupported sample width: 4"):
        convert_24bit_wav_to_16bit_pcm(wav_file)


def test_export_16bit_wav_writes_valid_file(tmp_path: Path):
    """Assert export_16bit_wav downscales 24-bit input and writes valid 16-bit RIFF WAV."""
    src_wav = tmp_path / "src_24.wav"
    dest_wav = tmp_path / "nested" / "output_16.wav"

    samples_24 = [bytes([0x00, 0xFF, 0x7F]), bytes([0x00, 0x00, 0x80])]
    _create_synthetic_wav(src_wav, sampwidth=3, framerate=8000, channels=1, raw_data=b"".join(samples_24))

    result_path = export_16bit_wav(src_wav, dest_wav)

    assert result_path == dest_wav
    assert dest_wav.is_file()

    with wave.open(str(dest_wav), "rb") as wf:
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 8000
        assert wf.getnchannels() == 1
        assert wf.getcomptype() == "NONE"
        frames = wf.readframes(wf.getnframes())

    unpacked = struct.unpack("<2h", frames)
    assert unpacked[0] == 32767
    assert unpacked[1] == -32768


def test_embed_sound_annotation_on_blank_page():
    """Assert embed_sound_annotation injects valid ISO 32000-1 Sound annotation and stream."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(236.0, 600.0, 254.0, 618.0)
    pcm_bytes = b"\x12\x34\x56\x78" * 100

    annot_xref = embed_sound_annotation(
        doc=doc,
        page=page,
        rect=rect,
        pcm_bytes=pcm_bytes,
        framerate=8000,
        channels=1,
    )
    assert annot_xref > 0

    # Save and reload document to verify strict PDF spec conformance via PyMuPDF parser
    pdf_bytes = doc.tobytes()
    doc.close()

    reloaded_doc = fitz.open("pdf", pdf_bytes)
    reloaded_page = reloaded_doc[0]
    annots = list(reloaded_page.annots())

    assert len(annots) == 1
    annot = annots[0]
    assert annot.type == (18, "Sound")
    assert annot.xref == annot_xref

    # Verify Sound dictionary attributes
    sound_key = reloaded_doc.xref_get_key(annot.xref, "Sound")
    assert sound_key[0] == "xref"
    sound_xref = int(sound_key[1].split()[0])

    assert reloaded_doc.xref_get_key(sound_xref, "Type") == ("name", "/Sound")
    assert reloaded_doc.xref_get_key(sound_xref, "R") == ("int", "8000")
    assert reloaded_doc.xref_get_key(sound_xref, "C") == ("int", "1")
    assert reloaded_doc.xref_get_key(sound_xref, "B") == ("int", "16")
    assert reloaded_doc.xref_get_key(sound_xref, "E") == ("name", "/Signed")

    # Verify stream content
    stream_bytes = reloaded_doc.xref_stream(sound_xref)
    assert stream_bytes == pcm_bytes
    reloaded_doc.close()


def test_embed_sound_annotation_idempotency():
    """Assert subsequent injections at intersecting rect update stream without duplicate annots."""
    # 1. Test in-memory update across successive calls on new document
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(236.0, 600.0, 254.0, 618.0)
    pcm_bytes_1 = b"\x01\x02" * 50
    pcm_bytes_2 = b"\x03\x04" * 100

    xref_1 = embed_sound_annotation(doc, page, rect, pcm_bytes_1, framerate=8000, channels=1)
    xref_2 = embed_sound_annotation(doc, page, rect, pcm_bytes_2, framerate=8000, channels=1)
    assert xref_1 == xref_2

    pdf_bytes = doc.tobytes()
    doc.close()

    # 2. Test re-opening pre-annotated PDF: re-embedding preserves len(list(page.annots())) in memory
    reloaded_doc = fitz.open("pdf", pdf_bytes)
    reloaded_page = reloaded_doc[0]
    assert len(list(reloaded_page.annots())) == 1

    pcm_bytes_3 = b"\x05\x06" * 80
    xref_3 = embed_sound_annotation(reloaded_doc, reloaded_page, rect, pcm_bytes_3, framerate=8000, channels=1)
    assert xref_3 == xref_1
    assert len(list(reloaded_page.annots())) == 1

    sound_key = reloaded_doc.xref_get_key(xref_3, "Sound")
    sound_xref = int(sound_key[1].split()[0])
    assert reloaded_doc.xref_stream(sound_xref) == pcm_bytes_3
    reloaded_doc.close()



def test_embed_sound_annotation_with_indirect_annots_object():
    """Assert sound annotation registers correctly into an indirect /Annots array object."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Pre-populate page with an indirect /Annots object
    indirect_annots_xref = doc.get_new_xref()
    doc.update_object(indirect_annots_xref, "[]")
    doc.xref_set_key(page.xref, "Annots", f"{indirect_annots_xref} 0 R")

    rect = fitz.Rect(100.0, 100.0, 120.0, 120.0)
    pcm_bytes = b"\xaa\xbb" * 20

    annot_xref = embed_sound_annotation(doc, page, rect, pcm_bytes)
    assert annot_xref > 0

    pdf_bytes = doc.tobytes()
    doc.close()

    reloaded_doc = fitz.open("pdf", pdf_bytes)
    reloaded_page = reloaded_doc[0]
    annots_info = reloaded_doc.xref_get_key(reloaded_page.xref, "Annots")
    assert annots_info[0] == "xref"
    annots = list(reloaded_page.annots())
    assert len(annots) == 1
    assert annots[0].type == (18, "Sound")
    assert annots[0].xref == annot_xref
    reloaded_doc.close()

