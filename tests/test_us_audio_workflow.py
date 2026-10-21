"""Unit and workflow tests for standalone US audio generation and retroactive PDF sound embedding.

Tests cover:
- UsAudioCandidate and UsAudioWorkflowSummary domain models.
- export_substation_16bit_wavs: canonical naming ({meas.label}.wav), 16-bit PCM output,
  skipping TEV, and fail-loud FileNotFoundError when 8k.wav is missing/empty.
- embed_survey_ultrasound_into_pdf: retroactive embedding, IdempotentSoundEmbeddingPolicy,
  UsTevAudioResiliencePolicy (missing survey returns 0), AtomicPdfSavePolicy (handle release,
  pre-flight unlink, guarded cleanup).
- UsAudioWorkflow: execution modes ('export_wav', 'embed_pdf', 'both'), run_substation,
  run_batch, and SubstationIsolatedBatchResiliencePolicy isolating single-substation errors.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import wave
try:
    import pymupdf as fitz
except ImportError:
    import fitz
import pytest

from src.postprocessing.sound_embedder import convert_24bit_wav_to_16bit_pcm
from src.quick_report.prpd import DiscoveredMeasurement
from src.workflows.us_audio import (
    UsAudioCandidate,
    UsAudioWorkflow,
    UsAudioWorkflowSummary,
    embed_survey_ultrasound_into_pdf,
    export_substation_16bit_wavs,
)


def _create_synthetic_wav(
    path: Path,
    sampwidth: int = 3,
    framerate: int = 8000,
    channels: int = 1,
    num_samples: int = 100,
) -> Path:
    """Helper to generate a valid WAV file with synthetic PCM frames."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.setcomptype("NONE", "not compressed")
        if sampwidth == 3:
            raw = bytes([0x56, 0x34, 0x12]) * num_samples
        elif sampwidth == 2:
            raw = bytes([0x34, 0x12]) * num_samples
        else:
            raw = bytes([0x12]) * num_samples
        wf.writeframes(raw)
    return path


def _create_synthetic_survey(survey_root: Path, create_wav: bool = True) -> Path:
    """Creates a synthetic UltraTEV survey folder with US and TEV measurements."""
    survey_root.mkdir(parents=True, exist_ok=True)

    vcb_cb_dir = survey_root / "VCB" / "PANEL_1" / "meas_cb"
    vcb_cb_dir.mkdir(parents=True, exist_ok=True)
    if create_wav:
        _create_synthetic_wav(vcb_cb_dir / "8k.wav", sampwidth=3)
    (vcb_cb_dir / "Ultrasonic.html").write_text("<html></html>", encoding="utf-8")
    (vcb_cb_dir / "ultrasonic_phase_plot.js").write_text(
        'var ultra_events = {"data": [[15.5, 60, 100]]};\n', encoding="utf-8"
    )

    vcb_bb_dir = survey_root / "VCB" / "PANEL_1" / "meas_bb"
    vcb_bb_dir.mkdir(parents=True, exist_ok=True)
    if create_wav:
        _create_synthetic_wav(vcb_bb_dir / "8k.wav", sampwidth=3)
    (vcb_bb_dir / "Ultrasonic.html").write_text("<html></html>", encoding="utf-8")
    (vcb_bb_dir / "ultrasonic_phase_plot.js").write_text(
        'var ultra_events = {"data": [[12.0, 60, 100]]};\n', encoding="utf-8"
    )

    tev_dir = survey_root / "VCB" / "PANEL_1" / "meas_tev"
    tev_dir.mkdir(parents=True, exist_ok=True)
    (tev_dir / "TEV.html").write_text("<html></html>", encoding="utf-8")

    manifest = {
        "assets": [
            {
                "$ASSET_NAME": "VCB",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "PANEL 1",
                        "$MEASURES": [
                            {
                                "$MEASURE_TYPE": "$ULTRA",
                                "Data": "VCB/PANEL_1/meas_cb",
                                "$COMPONENT": "$CIRCUIT_BREAKER",
                            },
                            {
                                "$MEASURE_TYPE": "$ULTRA",
                                "Data": "VCB/PANEL_1/meas_bb",
                                "$COMPONENT": "$UPPER_BUSBARS",
                            },
                            {
                                "$MEASURE_TYPE": "$TEV",
                                "Data": "VCB/PANEL_1/meas_tev",
                                "$COMPONENT": "$CIRCUIT_BREAKER",
                            },
                        ],
                    }
                ],
            }
        ]
    }
    (survey_root / "survey_summary.js").write_text(
        f"var survey_summary = {json.dumps(manifest)};\n", encoding="utf-8"
    )
    return survey_root


def _create_synthetic_report_pdf(pdf_path: Path) -> Path:
    """Generates a synthetic deliverable PDF with 'Sound clip' anchors and equipment contexts."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()

    # Page 1: VCB Panel 1 Breaker Compartment
    page1 = doc.new_page(width=595.0, height=842.0)
    page1.insert_text(fitz.Point(60.0, 100.0), "Panel No. : 1", fontsize=10)
    page1.insert_text(fitz.Point(60.0, 120.0), "Panel Name : INCOMER 1", fontsize=10)
    page1.insert_text(fitz.Point(60.0, 140.0), "Area : BREAKER COMPARTMENT", fontsize=10)
    page1.insert_text(fitz.Point(80.0, 650.0), "Sound clip", fontsize=10)

    # Page 2: VCB Panel 1 Busbar Compartment
    page2 = doc.new_page(width=595.0, height=842.0)
    page2.insert_text(fitz.Point(60.0, 100.0), "Panel No. : 1", fontsize=10)
    page2.insert_text(fitz.Point(60.0, 120.0), "Panel Name : INCOMER 1", fontsize=10)
    page2.insert_text(fitz.Point(60.0, 140.0), "Area : BUSBAR COMPARTMENT", fontsize=10)
    page2.insert_text(fitz.Point(80.0, 650.0), "Sound clip", fontsize=10)

    # Page 3: Overview page without 'Sound clip'
    page3 = doc.new_page(width=595.0, height=842.0)
    page3.insert_text(fitz.Point(60.0, 100.0), "Substation Overview", fontsize=14)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


# ==============================================================================
# Seam 1: Domain Models & Standalone WAV Export Tests
# ==============================================================================


def test_export_substation_16bit_wavs_canonical_names_and_parity(tmp_path: Path):
    """Assert WAV export writes canonical {label}.wav files downscaled to 16-bit PCM and skips TEV."""
    survey_dir = tmp_path / "US+TEV"
    _create_synthetic_survey(survey_dir, create_wav=True)

    output_dir = tmp_path / "sounds"
    wav_paths = export_substation_16bit_wavs(survey_dir, output_dir)

    assert len(wav_paths) == 2
    filenames = {p.name for p in wav_paths}
    assert filenames == {
        "VCB_PANEL_1_CIRCUIT_BREAKER_US.wav",
        "VCB_PANEL_1_UPPER_BUSBARS_US.wav",
    }

    # Verify each exported file is a valid 16-bit PCM WAV
    for wav_p in wav_paths:
        assert wav_p.is_file()
        with wave.open(str(wav_p), "rb") as wf:
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 8000
            assert wf.getnchannels() == 1


def test_export_substation_16bit_wavs_fails_loud_on_missing_8k_wav(tmp_path: Path):
    """Assert WAV export fails loudly with FileNotFoundError when 8k.wav is missing or empty."""
    survey_dir = tmp_path / "US+TEV"
    _create_synthetic_survey(survey_dir, create_wav=False)

    output_dir = tmp_path / "sounds"
    with pytest.raises(FileNotFoundError, match="8k.wav"):
        export_substation_16bit_wavs(survey_dir, output_dir)


def test_export_substation_16bit_wavs_missing_survey_root_raises(tmp_path: Path):
    """Assert WAV export raises FileNotFoundError upfront if survey_root does not exist."""
    missing_dir = tmp_path / "NON_EXISTENT_SURVEY"
    output_dir = tmp_path / "sounds"
    with pytest.raises(FileNotFoundError, match="survey directory not found"):
        export_substation_16bit_wavs(missing_dir, output_dir)


def test_export_substation_16bit_wavs_idempotent_overwrite(tmp_path: Path):
    """Assert subsequent export runs overwrite existing files cleanly without error."""
    survey_dir = tmp_path / "US+TEV"
    _create_synthetic_survey(survey_dir, create_wav=True)

    output_dir = tmp_path / "sounds"
    first_run = export_substation_16bit_wavs(survey_dir, output_dir)
    assert len(first_run) == 2

    # Run again into the same output directory
    second_run = export_substation_16bit_wavs(survey_dir, output_dir)
    assert len(second_run) == 2
    assert {p.name for p in second_run} == {p.name for p in first_run}


# ==============================================================================
# Seam 2: Retroactive PDF Sound Embedding & Resilience Tests
# ==============================================================================


def test_embed_survey_ultrasound_into_pdf_idempotent(tmp_path: Path):
    """Assert sound embedding modifies deliverable PDF and is strictly idempotent."""
    survey_dir = tmp_path / "US+TEV"
    _create_synthetic_survey(survey_dir, create_wav=True)

    pdf_path = tmp_path / "DELIVERABLE.pdf"
    _create_synthetic_report_pdf(pdf_path)

    # First injection
    count1 = embed_survey_ultrasound_into_pdf(pdf_path, survey_dir)
    assert count1 == 2

    # Verify annotations in PDF
    with fitz.open(pdf_path) as doc:
        page0 = doc[0]
        annots_p0 = list(page0.annots())
        assert len(annots_p0) == 1
        assert annots_p0[0].type == (18, "Sound")

        page1 = doc[1]
        annots_p1 = list(page1.annots())
        assert len(annots_p1) == 1
        assert annots_p1[0].type == (18, "Sound")

        # Overview page has no sound annotations
        page2 = doc[2]
        annots_p2 = list(page2.annots())
        assert len(annots_p2) == 0

    # Second injection: IdempotentSoundEmbeddingPolicy must update stream and not duplicate annotations
    count2 = embed_survey_ultrasound_into_pdf(pdf_path, survey_dir)
    assert count2 == 2

    with fitz.open(pdf_path) as doc:
        p0 = doc[0]
        p1 = doc[1]
        assert len(list(p0.annots())) == 1
        assert len(list(p1.annots())) == 1


def test_embed_survey_ultrasound_missing_survey_returns_zero(tmp_path: Path):
    """UsTevAudioResiliencePolicy: missing survey root returns 0 without raising exception."""
    pdf_path = tmp_path / "DELIVERABLE.pdf"
    _create_synthetic_report_pdf(pdf_path)

    # Missing survey dir
    missing_dir = tmp_path / "NON_EXISTENT_SURVEY"
    count = embed_survey_ultrasound_into_pdf(pdf_path, missing_dir)
    assert count == 0

    # None survey dir
    count_none = embed_survey_ultrasound_into_pdf(pdf_path, None)
    assert count_none == 0


def test_atomic_pdf_save_policy_unlinks_stale_temp_and_handles_cleanup(tmp_path: Path):
    """AtomicPdfSavePolicy unlinks stale temp file pre-flight and cleans up on error."""
    survey_dir = tmp_path / "US+TEV"
    _create_synthetic_survey(survey_dir, create_wav=True)

    pdf_path = tmp_path / "DELIVERABLE.pdf"
    _create_synthetic_report_pdf(pdf_path)

    # Pre-create stale temp file
    stale_tmp = pdf_path.parent / f".tmp_sound_{pdf_path.name}"
    stale_tmp.write_bytes(b"STALE DATA")
    assert stale_tmp.exists()

    count = embed_survey_ultrasound_into_pdf(pdf_path, survey_dir)
    assert count == 2
    assert not stale_tmp.exists()  # Cleaned up and replaced atomically

    # File can be opened immediately on Windows without permission error
    with fitz.open(pdf_path) as doc:
        assert doc.page_count == 3


def test_atomic_pdf_save_policy_cleans_up_temp_on_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """AtomicPdfSavePolicy cleans up .tmp_sound_{pdf.name} if an exception is raised mid-save."""
    survey_dir = tmp_path / "US+TEV"
    _create_synthetic_survey(survey_dir, create_wav=True)

    pdf_path = tmp_path / "DELIVERABLE.pdf"
    _create_synthetic_report_pdf(pdf_path)

    # Monkeypatch os.replace to simulate an unexpected error after writing temp file
    def mock_replace(src: Path | str, dst: Path | str):
        # Verify temp file was created before raising
        assert Path(src).exists()
        raise OSError("Simulated Windows disk I/O lock error")

    monkeypatch.setattr(os, "replace", mock_replace)

    tmp_file = pdf_path.parent / f".tmp_sound_{pdf_path.name}"

    with pytest.raises(OSError, match="Simulated Windows disk I/O lock error"):
        embed_survey_ultrasound_into_pdf(pdf_path, survey_dir)

    # Finally block must have cleaned up the temporary file
    assert not tmp_file.exists()


# ==============================================================================
# Seam 3: UsAudioWorkflow & Batch Resilience Tests
# ==============================================================================


def test_us_audio_workflow_modes(tmp_path: Path):
    """Test UsAudioWorkflow respects export_wav, embed_pdf, and both execution modes."""
    survey_dir = tmp_path / "US+TEV"
    _create_synthetic_survey(survey_dir, create_wav=True)

    pdf_path = tmp_path / "DELIVERABLE.pdf"
    _create_synthetic_report_pdf(pdf_path)
    sounds_dir = tmp_path / "sounds"

    cand = UsAudioCandidate(
        package=None,
        raw_data_dir=tmp_path,
        survey_dir=survey_dir,
        sounds_output_dir=sounds_dir,
        full_report_pdf=pdf_path,
        quick_report_pdf=None,
    )

    # 1. Mode: export_wav
    wf_export = UsAudioWorkflow(mode="export_wav")
    wavs, sounds = wf_export.run_substation(cand)
    assert wavs == 2
    assert sounds == 0

    # 2. Mode: embed_pdf
    wf_embed = UsAudioWorkflow(mode="embed_pdf")
    wavs, sounds = wf_embed.run_substation(cand)
    assert wavs == 0
    assert sounds == 2

    # 3. Mode: both
    wf_both = UsAudioWorkflow(mode="both")
    wavs, sounds = wf_both.run_substation(cand)
    assert wavs == 2
    assert sounds == 2


def test_us_audio_workflow_batch_resilience_isolates_corrupted_candidate(tmp_path: Path):
    """SubstationIsolatedBatchResiliencePolicy: isolates single error, records it, continues batch."""
    # Candidate 1: valid
    s1 = tmp_path / "sub1"
    survey1 = _create_synthetic_survey(s1 / "US+TEV", create_wav=True)
    pdf1 = _create_synthetic_report_pdf(s1 / "REPORT.pdf")
    c1 = UsAudioCandidate(
        survey_dir=survey1,
        sounds_output_dir=s1 / "sounds",
        full_report_pdf=pdf1,
    )

    # Candidate 2: corrupted (missing 8k.wav causes FileNotFoundError in export_wav)
    s2 = tmp_path / "sub2"
    survey2 = _create_synthetic_survey(s2 / "US+TEV", create_wav=False)
    pdf2 = _create_synthetic_report_pdf(s2 / "REPORT.pdf")
    c2 = UsAudioCandidate(
        survey_dir=survey2,
        sounds_output_dir=s2 / "sounds",
        full_report_pdf=pdf2,
    )

    # Candidate 3: valid
    s3 = tmp_path / "sub3"
    survey3 = _create_synthetic_survey(s3 / "US+TEV", create_wav=True)
    pdf3 = _create_synthetic_report_pdf(s3 / "REPORT.pdf")
    c3 = UsAudioCandidate(
        survey_dir=survey3,
        sounds_output_dir=s3 / "sounds",
        full_report_pdf=pdf3,
    )

    wf = UsAudioWorkflow(mode="both")
    progress_calls: list[tuple[int, int, str]] = []

    def callback(cur: int, total: int, name: str) -> None:
        progress_calls.append((cur, total, name))

    summary = wf.run_batch([c1, c2, c3], progress_callback=callback)

    assert summary.total_substations == 3
    assert summary.total_wavs_exported == 4  # 2 from c1, 2 from c3
    assert summary.total_sounds_embedded == 4  # 2 from c1, 2 from c3
    assert len(summary.errors) == 1
    assert "8k.wav" in summary.errors[0]
    assert len(progress_calls) == 3


def test_embed_survey_ultrasound_multi_transition_disambiguation(tmp_path: Path):
    """Verify embed_survey_ultrasound_into_pdf sequentially disambiguates unnumbered transition panels:
    Pages 43-45 embed PANEL_6 audio, Pages 71-73 embed PANEL_12 audio, Pages 98-100 embed PANEL_18 audio.
    """
    survey_root = tmp_path / "US+TEV"
    survey_root.mkdir(parents=True, exist_ok=True)

    manifest_measures = []
    # Create survey directories for PANEL_6 (100 samples), PANEL_12 (200 samples), PANEL_18 (300 samples)
    for p_no, samples in [(6, 100), (12, 200), (18, 300)]:
        p_dir = survey_root / "VCB" / f"PANEL_{p_no}"
        p_dir.mkdir(parents=True, exist_ok=True)
        for comp, tag, db in [
            ("$CIRCUIT_BREAKER", "front", 15.0),
            ("$CABLE_BOX", "rear", 14.0),
            ("$UPPER_BUSBARS", "busbar", 16.0),
        ]:
            m_dir = p_dir / f"meas_{tag}"
            m_dir.mkdir(parents=True, exist_ok=True)
            _create_synthetic_wav(m_dir / "8k.wav", sampwidth=3, num_samples=samples)
            (m_dir / "Ultrasonic.html").write_text("<html></html>", encoding="utf-8")
            (m_dir / "ultrasonic_phase_plot.js").write_text(
                f'var ultra_events = {{"data": [[{db}, 60, 100]]}};\n', encoding="utf-8"
            )
            manifest_measures.append({
                "$MEASURE_TYPE": "$ULTRA",
                "Data": f"VCB/PANEL_{p_no}/meas_{tag}",
                "$COMPONENT": comp,
            })

    manifest = {
        "assets": [
            {
                "$ASSET_NAME": "VCB",
                "$SUB_ASSETS": [
                    {
                        "$SUB_ASSET_NAME": "SWITCHGEAR",
                        "$MEASURES": manifest_measures,
                    }
                ],
            }
        ]
    }
    (survey_root / "survey_summary.js").write_text(
        f"var survey_summary = {json.dumps(manifest)};\n", encoding="utf-8"
    )

    # Build 18-panel switchgear catalog matching Bandar Indera Mahkota VI
    class PanelSpec:
        def __init__(self, panel_no: int, name: str, panel_feeder_no: str = ""):
            self.panel_no = panel_no
            self.name = name
            self.panel_feeder_no = panel_feeder_no

    class SwgSpec:
        def __init__(self, panels: list[PanelSpec]):
            self.panels = panels

    class EqSpec:
        def __init__(self, switchgears: list[SwgSpec]):
            self.switchgears = switchgears

    class PkgSpec:
        def __init__(self, equipment: EqSpec):
            self.equipment = equipment

    panels = []
    for i in range(1, 19):
        if i in (6, 12, 18):
            panels.append(PanelSpec(panel_no=i, name="TRANSITION PANEL", panel_feeder_no=""))
        else:
            panels.append(PanelSpec(panel_no=i, name=f"FEEDER {i}", panel_feeder_no=f"CKN000{i:02d}"))
    pkg = PkgSpec(equipment=EqSpec(switchgears=[SwgSpec(panels=panels)]))

    # Create synthetic deliverable PDF with pages corresponding to Bandar Indera Mahkota VI
    pdf_path = tmp_path / "DELIVERABLE_MULTI_TRANS.pdf"
    doc = fitz.open()

    page_specs = [
        ("5", "FEEDER 5", "CABLE COMPARTMENT"),
        # Transition 1 (Panel 6)
        ("-", "TRANSITION PANEL", "FRONT COMPARTMENT"),
        ("-", "TRANSITION PANEL", "REAR COMPARTMENT"),
        ("-", "TRANSITION PANEL", "BUSBAR COMPARTMENT"),
        ("7", "FEEDER 7", "CABLE COMPARTMENT"),
        ("11", "FEEDER 11", "CABLE COMPARTMENT"),
        # Transition 2 (Panel 12)
        ("-", "TRANSITION PANEL", "FRONT COMPARTMENT"),
        ("-", "TRANSITION PANEL", "REAR COMPARTMENT"),
        ("-", "TRANSITION PANEL", "BUSBAR COMPARTMENT"),
        ("13", "FEEDER 13", "CABLE COMPARTMENT"),
        ("17", "FEEDER 17", "CABLE COMPARTMENT"),
        # Transition 3 (Panel 18)
        ("-", "TRANSITION PANEL", "FRONT COMPARTMENT"),
        ("-", "TRANSITION PANEL", "REAR COMPARTMENT"),
        ("-", "TRANSITION PANEL", "BUSBAR COMPARTMENT"),
    ]

    for p_no_str, p_name_str, area_str in page_specs:
        p = doc.new_page(width=595.0, height=842.0)
        p.insert_text(fitz.Point(60.0, 100.0), f"Panel No. : {p_no_str}", fontsize=10)
        p.insert_text(fitz.Point(60.0, 120.0), f"Panel Name : {p_name_str}", fontsize=10)
        p.insert_text(fitz.Point(60.0, 140.0), f"Area : {area_str}", fontsize=10)
        p.insert_text(fitz.Point(80.0, 650.0), "Sound clip", fontsize=10)

    doc.save(str(pdf_path))
    doc.close()

    count = embed_survey_ultrasound_into_pdf(pdf_path, survey_root, package=pkg)
    assert count == 9

    with fitz.open(pdf_path) as verify_doc:
        # Pages 1, 2, 3 -> Transition 1 (Panel 6, 100 samples -> 200 bytes)
        for page_idx in (1, 2, 3):
            annots = list(verify_doc[page_idx].annots())
            assert len(annots) == 1
            sound_ref = int(verify_doc.xref_get_key(annots[0].xref, "Sound")[1].split()[0])
            stream_len = len(verify_doc.xref_stream(sound_ref))
            assert stream_len == 200, f"Page {page_idx} expected 200 bytes (Panel 6), got {stream_len}"

        # Pages 6, 7, 8 -> Transition 2 (Panel 12, 200 samples -> 400 bytes)
        for page_idx in (6, 7, 8):
            annots = list(verify_doc[page_idx].annots())
            assert len(annots) == 1
            sound_ref = int(verify_doc.xref_get_key(annots[0].xref, "Sound")[1].split()[0])
            stream_len = len(verify_doc.xref_stream(sound_ref))
            assert stream_len == 400, f"Page {page_idx} expected 400 bytes (Panel 12), got {stream_len}"

        # Pages 11, 12, 13 -> Transition 3 (Panel 18, 300 samples -> 600 bytes)
        for page_idx in (11, 12, 13):
            annots = list(verify_doc[page_idx].annots())
            assert len(annots) == 1
            sound_ref = int(verify_doc.xref_get_key(annots[0].xref, "Sound")[1].split()[0])
            stream_len = len(verify_doc.xref_stream(sound_ref))
            assert stream_len == 600, f"Page {page_idx} expected 600 bytes (Panel 18), got {stream_len}"

