"""Standalone US audio generation & retroactive PDF sound embedding workflow engine.

Coordinates both standalone 16-bit WAV audio file export into <SUBSTATION>/RAW DATA/US+TEV/sounds/
and retroactive PDF sound embedding across Full Report and Quick Report deliverables.
Enforces UsTevAudioResiliencePolicy, AtomicPdfSavePolicy, and SubstationIsolatedBatchResiliencePolicy.
Policy Category: Best-Effort Batch Orchestration with Strict Per-Candidate Component Isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable, Literal, Sequence

import fitz

from src.postprocessing.sound_embedder import (
    convert_24bit_wav_to_16bit_pcm,
    embed_sound_annotation,
    export_16bit_wav,
    extract_page_equipment_context,
    find_sound_clip_anchor,
    resolve_measurement_audio_for_page,
    validate_and_return_8k_wav,
)
from src.quick_report.prpd import (
    DiscoveredMeasurement,
    discover_survey_measurements,
)
from src.testsheet.models import SubstationTestsheetPackage

logger = logging.getLogger(__name__)

UsAudioMode = Literal["export_wav", "embed_pdf", "both"]


@dataclass
class UsAudioCandidate:
    """Discovered candidate substation for ultrasound audio export and embedding."""

    package: SubstationTestsheetPackage | None = None
    raw_data_dir: Path | None = None
    survey_dir: Path | None = None
    sounds_output_dir: Path | None = None
    full_report_pdf: Path | None = None
    quick_report_pdf: Path | None = None

    @property
    def display_name(self) -> str:
        """User-facing substation display label."""
        if self.package and getattr(self.package, "substation_name", None):
            return str(self.package.substation_name)
        if self.raw_data_dir:
            return Path(self.raw_data_dir).name
        if self.survey_dir:
            return Path(self.survey_dir).name
        return "Unknown Substation"

    def resolve_sounds_output_dir(self) -> Path:
        """Resolve canonical destination directory for exported 16-bit WAV files.

        Anchors to <SUBSTATION>/RAW DATA/US+TEV/sounds/.
        """
        if self.sounds_output_dir is not None:
            return Path(self.sounds_output_dir)

        if self.survey_dir is not None:
            survey_path = Path(self.survey_dir)
            if survey_path.name.upper() == "US+TEV":
                return survey_path / "sounds"
            return survey_path / "sounds"

        if self.raw_data_dir is not None:
            raw_path = Path(self.raw_data_dir)
            if (raw_path / "US+TEV").is_dir():
                return raw_path / "US+TEV" / "sounds"
            if (raw_path / "RAW DATA" / "US+TEV").is_dir():
                return raw_path / "RAW DATA" / "US+TEV" / "sounds"
            return raw_path / "US+TEV" / "sounds"

        raise ValueError(
            "Cannot resolve sounds output directory: candidate has no sounds_output_dir, "
            "survey_dir, or raw_data_dir specified."
        )


@dataclass
class UsAudioWorkflowSummary:
    """Execution telemetry and results across an ultrasound audio batch."""

    total_substations: int = 0
    total_wavs_exported: int = 0
    total_sounds_embedded: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_time: float = 0.0


def export_substation_16bit_wavs(
    survey_root: Path | str,
    output_dir: Path | str,
) -> list[Path]:
    """Export standard 16-bit WAV files for all US measurements in an UltraTEV survey.

    Discovers all US measurements via discover_survey_measurements(survey_root).
    Iterates measurements and locates 8k.wav.
    Asserts 8k.wav exists and is non-empty; if missing, raises FileNotFoundError (fail-loud invariant).
    Directly consumes canonical deduplicated label meas.label (SurveyMeasurementNaming)
    to ensure 100% naming parity and duplicate counter safety with PRPD graphs.
    Exports standard 16-bit WAV to <output_dir>/{meas.label}.wav with idempotent overwrite.

    Args:
        survey_root: Path to the UltraTEV survey folder.
        output_dir: Destination directory for exported .wav files.

    Returns:
        list[Path]: List of exported 16-bit .wav file paths.

    Raises:
        FileNotFoundError: If survey_root directory does not exist or authoritative 8k.wav
            is missing or empty in any US measurement.
    """
    root = Path(survey_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"UltraTEV survey directory not found: {root}")

    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    measurements = discover_survey_measurements(root)
    us_measurements = [
        m for m in measurements if str(getattr(m, "tech", "")).upper() == "US"
    ]

    exported_paths: list[Path] = []
    for meas in us_measurements:
        wav_8k = validate_and_return_8k_wav(meas)
        dest_wav = out_dir / f"{meas.label}.wav"
        export_16bit_wav(wav_8k, dest_wav)
        exported_paths.append(dest_wav)

    return exported_paths


def embed_survey_ultrasound_into_pdf(
    pdf_path: Path | str,
    survey_root: Path | str | None,
    package: SubstationTestsheetPackage | None = None,
) -> int:
    """Retroactively embed ultrasound sound annotations into an existing deliverable PDF.

    Validates pdf_path.is_file(). If survey root is missing, logs INFO and returns 0 (UsTevAudioResiliencePolicy).
    Pre-flight unlinks any stale .tmp_sound_{pdf.name} in pdf_path.parent.
    Uses context-managed PyMuPDF session (with fitz.open(pdf_path) as doc:) to guarantee handle closure:
      - Caches discovered US measurements for survey_root.
      - Iterates pages:
        - Finds "Sound clip" anchor using find_sound_clip_anchor(page) (centered in Column 2).
        - If found, extracts context using extract_page_equipment_context(page, package=package).
        - Resolves matching 8k.wav via resolve_measurement_audio_for_page().
        - Downscales 24-bit to 16-bit PCM in memory via convert_24bit_wav_to_16bit_pcm().
        - Injects sound annotation idempotently via embed_sound_annotation().
      - Writes modified PDF bytes to .tmp_sound_{pdf.name} in the same directory.
    Enforces AtomicPdfSavePolicy: outside document context (handles closed), replaces pdf_path
    atomically via os.replace(tmp_path, pdf_path), guarded with try...finally to ensure
    temp file cleanup on error.

    Args:
        pdf_path: Path to the deliverable PDF file.
        survey_root: Path to the UltraTEV survey directory, or None.
        package: Optional SubstationTestsheetPackage for equipment context catalog.

    Returns:
        int: Total count of inserted or updated sound annotations.

    Raises:
        FileNotFoundError: If target pdf_path does not exist on disk.
    """
    target_pdf = Path(pdf_path).resolve()
    if not target_pdf.is_file():
        raise FileNotFoundError(f"Deliverable PDF file not found: {target_pdf}")

    if survey_root is None:
        logger.info(
            "US+TEV raw survey folder not present for %s; skipping sound embedding",
            target_pdf,
        )
        return 0

    survey_path = Path(survey_root).resolve()
    if not survey_path.is_dir():
        logger.info(
            "US+TEV raw survey folder not present for %s; skipping sound embedding",
            target_pdf,
        )
        return 0

    # Discover and cache US measurements upfront
    measurements = discover_survey_measurements(survey_path)
    us_measurements = [
        m for m in measurements if str(getattr(m, "tech", "")).upper() == "US"
    ]
    if not us_measurements:
        logger.info(
            "No US measurements discovered in survey %s; skipping sound embedding",
            survey_path,
        )
        return 0

    tmp_path = target_pdf.parent / f".tmp_sound_{target_pdf.name}"

    # Pre-flight: unlink any stale temp file
    if tmp_path.exists():
        try:
            tmp_path.unlink()
        except OSError as exc:
            logger.warning("Failed pre-flight unlink of stale temp file %s: %s", tmp_path, exc)

    annot_count = 0
    try:
        with fitz.open(target_pdf) as doc:
            for page in doc:
                anchor = find_sound_clip_anchor(page)
                if anchor is None:
                    continue

                page_ctx = extract_page_equipment_context(page, package=package)
                wav_file = resolve_measurement_audio_for_page(
                    survey_path, us_measurements, page_ctx
                )
                if wav_file is None or not Path(wav_file).is_file():
                    continue

                pcm_bytes, framerate, channels = convert_24bit_wav_to_16bit_pcm(wav_file)
                embed_sound_annotation(
                    doc,
                    page,
                    anchor,
                    pcm_bytes,
                    framerate=framerate,
                    channels=channels,
                )
                annot_count += 1

            if annot_count > 0:
                doc.save(str(tmp_path), garbage=3, deflate=True)

        if annot_count > 0 and tmp_path.exists():
            os.replace(tmp_path, target_pdf)

        return annot_count
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


class UsAudioWorkflow:
    """Core workflow engine coordinating standalone WAV export and retroactive PDF sound embedding.

    Adheres to SubstationIsolatedBatchResiliencePolicy (best-effort batch orchestration).
    """

    def __init__(self, mode: UsAudioMode = "both") -> None:
        norm_mode = mode.lower().strip()
        if norm_mode not in ("export_wav", "embed_pdf", "both"):
            raise ValueError(
                f"Unsupported UsAudioWorkflow mode: '{mode}'. Must be 'export_wav', 'embed_pdf', or 'both'."
            )
        self.mode: UsAudioMode = norm_mode  # type: ignore[assignment]

    def run_substation(self, candidate: UsAudioCandidate) -> tuple[int, int]:
        """Execute ultrasound audio export and/or embedding for a single substation candidate.

        Args:
            candidate: UsAudioCandidate specifying survey paths, output directory, and PDFs.

        Returns:
            tuple[int, int]: (wavs_exported_count, sounds_embedded_count)
        """
        wavs_exported = 0
        sounds_embedded = 0

        # 1. Standalone 16-bit WAV Export
        if self.mode in ("export_wav", "both"):
            if candidate.survey_dir and Path(candidate.survey_dir).is_dir():
                out_dir = candidate.resolve_sounds_output_dir()
                wav_paths = export_substation_16bit_wavs(candidate.survey_dir, out_dir)
                wavs_exported += len(wav_paths)
            else:
                logger.info(
                    "US+TEV raw survey folder not present for candidate %s; skipping WAV export",
                    candidate.display_name,
                )

        # 2. Retroactive PDF Sound Embedding
        if self.mode in ("embed_pdf", "both"):
            for pdf_target in (candidate.full_report_pdf, candidate.quick_report_pdf):
                if pdf_target and Path(pdf_target).is_file():
                    embedded = embed_survey_ultrasound_into_pdf(
                        pdf_path=pdf_target,
                        survey_root=candidate.survey_dir,
                        package=candidate.package,
                    )
                    sounds_embedded += embedded

        return wavs_exported, sounds_embedded

    def run_batch(
        self,
        candidates: Sequence[UsAudioCandidate],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> UsAudioWorkflowSummary:
        """Execute ultrasound audio processing across a batch of substation candidates.

        Enforces SubstationIsolatedBatchResiliencePolicy: single-substation errors are trapped,
        recorded in summary.errors, and do not halt subsequent candidates in the batch.

        Args:
            candidates: Sequence of UsAudioCandidate objects.
            progress_callback: Optional callback(current, total, name) for progress reporting.

        Returns:
            UsAudioWorkflowSummary: Telemetry summarizing batch results, counts, and errors.
        """
        summary = UsAudioWorkflowSummary(total_substations=len(candidates))
        start_time = time.perf_counter()

        for idx, cand in enumerate(candidates, start=1):
            name = cand.display_name

            if progress_callback:
                progress_callback(idx, len(candidates), name)

            try:
                wavs, sounds = self.run_substation(cand)
                summary.total_wavs_exported += wavs
                summary.total_sounds_embedded += sounds
            except Exception as exc:
                err_msg = f"{name}: {exc}"
                logger.error(
                    "[ERROR] Failed processing US audio for %s: %s",
                    name,
                    exc,
                    exc_info=True,
                )
                summary.errors.append(err_msg)

        summary.elapsed_time = time.perf_counter() - start_time
        return summary
