<!-- status: closed -->
Part of Wayfinder Map: [map.md](../map.md)
GitHub Issue: [#84](https://github.com/adamlarGit/pahang-cli/issues/84)
Specification: [spec.md](../spec.md)

# 084: feat(sound): in-memory 24-to-16-bit audio converter & PyMuPDF sound annotator

**What to build:** Core audio processing and PDF sound annotation engine. Delivers pure-Python in-memory 24-bit to 16-bit PCM downscaling (`sample >> 8`) for UltraTEV `8k.wav` recordings without external dependencies (`ffmpeg`/`sox`), standalone 16-bit WAV file export, and low-level ISO 32000-1 `/Subtype /Sound` annotation injection via PyMuPDF `xref` stream manipulation.

**Blocked by:** None (can start immediately).

**Status:** closed

- [x] Create `src/postprocessing/sound_embedder.py` module.
- [x] Implement `convert_24bit_wav_to_16bit_pcm(wav_path: Path | str) -> tuple[bytes, int, int]`:
  - Reads WAV frames using Python standard library `wave`.
  - Handles `sampwidth == 2` (passes through 16-bit PCM directly).
  - Handles `sampwidth == 3` (downscales 24-bit to 16-bit by discarding least significant byte `b0` via slice assignment `out[0::2] = raw[1::3]` and `out[1::2] = raw[2::3]`).
  - Handles `sampwidth == 1` (converts 8-bit unsigned to 16-bit signed).
  - Returns `(pcm_bytes, framerate, nchannels)` in memory with zero intermediate disk I/O.
- [x] Implement `export_16bit_wav(src_wav_path: Path | str, dest_wav_path: Path | str) -> Path`:
  - Uses `convert_24bit_wav_to_16bit_pcm` to get 16-bit PCM bytes.
  - Writes valid 16-bit RIFF WAV file with standard parameters (`sampwidth=2`, `comptype='NONE'`).
- [x] Implement `embed_sound_annotation(doc: fitz.Document, page: fitz.Page, rect: fitz.Rect, pcm_bytes: bytes, framerate: int = 8000, channels: int = 1) -> int`:
  - Enforces `IdempotentSoundEmbeddingPolicy`: inspects existing page annotations (`page.annots()`). If a `/Subtype /Sound` annotation already intersects `rect`, updates the existing sound object stream directly via `doc.update_stream(existing_sound_xref, pcm_bytes)` and returns existing annot xref without creating duplicate stacked icons or leaking unreferenced streams.
  - If no existing sound annotation intersects `rect`:
    - Allocates new xref for Sound Object stream (`/Type /Sound`, `/R framerate`, `/C channels`, `/B 16`, `/E /Signed`).
    - Injects raw 16-bit PCM stream via `doc.update_stream(sound_xref, pcm_bytes)`.
    - Converts PyMuPDF coordinates (top-left origin) to PDF points (bottom-left origin): `pdf_y0 = page_h - rect.y1`, `pdf_y1 = page_h - rect.y0`.
    - Allocates new xref for Sound Annotation (`/Type /Annot`, `/Subtype /Sound`, `/Rect [x0 pdf_y0 x1 pdf_y1]`, `/Sound sound_xref 0 R`, `/Name /Speaker`, `/F 4`, `/P page.xref 0 R`).
    - Robustly registers annotation xref to page `/Annots`: checks `doc.xref_get_key(page.xref, "Annots")`. If indirect (`('xref', '<annots_xref> 0 R')`), modifies the underlying indirect array object directly; if direct array (`('array', '...')`), appends before `]`; if null (`('null', 'null')`), assigns `[{annot_xref} 0 R]`.
  - Returns annotation xref integer.
- [x] Implement unit test suite in `tests/test_sound_embedder.py`:
  - Synthetic 24-bit WAV generation and downscaling verification (asserting exact mathematical sample values).
  - Standalone WAV export verification (asserting `sampwidth == 2` and playable audio).
  - Sound annotation injection test on blank PDF page, re-opening with PyMuPDF to assert `annot.type == (18, 'Sound')`, correct sample rate, bit depth, and byte length.
  - Idempotency test: injecting twice at the same coordinates updates the stream without increasing `len(list(page.annots()))` or creating duplicate stacked icons.
  - Indirect `/Annots` test: injecting on a PDF with an indirect `/Annots` object succeeds cleanly without corrupting the document.

