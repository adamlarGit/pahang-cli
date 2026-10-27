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

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from src.cli_selectors import (
    SelectOption,
    prompt_target_inspection_dates_with_ranges,
    select_multiple,
    select_one,
    select_pahang_inspection_dates_interactive,
)
from src.core.normalizers import format_month_folder
from src.postprocessing.sound_embedder import (
    TRANSFORMER_HV_SIDE_KEYWORDS,
    convert_24bit_wav_to_16bit_pcm,
    embed_sound_annotation,
    export_16bit_wav,
    extract_page_equipment_context,
    find_sound_clip_anchor,
    resolve_measurement_audio_for_page,
    validate_and_return_8k_wav,
)
from src.project.storage import extract_numerical_prefix
from src.quick_report.extractor import QuickReportExtractor
from src.quick_report.prpd import (
    DiscoveredMeasurement,
    discover_survey_measurements,
    discover_ultratev_survey_dir,
    resolve_survey_container_dir,
)
from src.testsheet.models import SubstationPackage, SubstationTestsheetPackage

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

        Anchors to <SUBSTATION>/RAW DATA/<CONTAINER>/sounds/ using a 2-level bounded container check.
        Raises ValueError if neither 'US' nor 'US+TEV' container is detected.
        """
        if self.sounds_output_dir is not None:
            return Path(self.sounds_output_dir)

        if self.survey_dir is not None:
            return resolve_survey_container_dir(self.survey_dir) / "sounds"

        if self.raw_data_dir is not None:
            raw_path = Path(self.raw_data_dir)
            discovered = discover_ultratev_survey_dir(raw_path)
            if discovered is not None:
                try:
                    return resolve_survey_container_dir(discovered) / "sounds"
                except ValueError:
                    pass

            for container in ("US+TEV", "US"):
                if (raw_path / container).is_dir():
                    return raw_path / container / "sounds"
                if (raw_path / "RAW DATA" / container).is_dir():
                    return raw_path / "RAW DATA" / container / "sounds"

            raise ValueError(
                f"Neither 'US' nor 'US+TEV' container detected in raw_data_dir: {self.raw_data_dir}"
            )

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


def _auto_discover_testsheet_data(pdf_path: Path) -> Any | None:
    """Auto-discover and parse testsheet workbook adjacent or via WorkspaceStorage."""
    from src.project.storage import LocalWorkspaceStorage
    from src.testsheet.extractor import TestsheetExtractor

    pe_num = None
    try:
        pe_num = extract_numerical_prefix(pdf_path.stem)
    except ValueError:
        pass

    ts_file: Path | None = None
    parts = list(pdf_path.parts)
    for i, p in enumerate(parts):
        if p.upper() in ("FULL REPORT", "QUICK REPORT") and i >= 1 and i + 3 < len(parts):
            root = Path(*parts[:i])
            station = parts[i + 1]
            month = parts[i + 2]
            date_str = parts[i + 3]
            storage = LocalWorkspaceStorage(root)
            if pe_num is not None:
                ts_file = storage.get_substation_testsheet_path(
                    station, month, date_str, pe_num, stem=pdf_path.stem
                )
            break

    # Sibling directory fallback if not in structured workspace
    if ts_file is None:
        for f in sorted(pdf_path.parent.glob("*.xlsx")):
            if f.name.startswith(("~$", ".")):
                continue
            if (pe_num is not None and str(pe_num) in f.stem) or (pdf_path.stem.upper() in f.stem.upper()):
                ts_file = f
                break

    if ts_file and ts_file.is_file():
        try:
            return TestsheetExtractor().extract_testsheet_data(ts_file)
        except Exception as exc:
            logger.debug("Failed parsing auto-discovered testsheet %s: %s", ts_file, exc)
    return None


def embed_survey_ultrasound_into_pdf(
    pdf_path: Path | str,
    survey_root: Path | str | None,
    package: SubstationTestsheetPackage | SubstationPackage | Any = None,
) -> int:
    """Retroactively embed ultrasound sound annotations into an existing deliverable PDF.

    Validates pdf_path.is_file(). If survey root is missing, logs INFO and returns 0 (UsTevAudioResiliencePolicy).
    Pre-flight unlinks any stale .tmp_sound_{pdf.name} in pdf_path.parent.
    Uses context-managed PyMuPDF session (with fitz.open(pdf_path) as doc:) to guarantee handle closure:
      - Caches discovered US measurements for survey_root.
      - Auto-discovers testsheet data if package is None.
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
            "US/US+TEV raw survey folder not present for %s; skipping sound embedding",
            target_pdf,
        )
        return 0

    survey_path = Path(survey_root).resolve()
    if not survey_path.is_dir():
        logger.info(
            "US/US+TEV raw survey folder not present for %s; skipping sound embedding",
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

    if package is None:
        package = _auto_discover_testsheet_data(target_pdf)

    tmp_path = target_pdf.parent / f".tmp_sound_{target_pdf.name}"

    # Pre-flight: unlink any stale temp file
    if tmp_path.exists():
        try:
            tmp_path.unlink()
        except OSError as exc:
            logger.warning("Failed pre-flight unlink of stale temp file %s: %s", tmp_path, exc)

    annot_count = 0
    state: dict[str, Any] = {}
    try:
        with fitz.open(target_pdf) as doc:
            for page in doc:
                page_ctx = extract_page_equipment_context(
                    page, package=package, state=state
                )

                anchor = find_sound_clip_anchor(page)
                if anchor is None:
                    continue

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
                    "US/US+TEV raw survey folder not present for candidate %s; skipping WAV export",
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


def _find_deliverable_pdf(
    base_dir: Path | None,
    pkg: SubstationTestsheetPackage,
) -> Path | None:
    """Locate deliverable PDF (<STEM>.pdf) on disk for a given substation package in canonical hierarchy."""
    if base_dir is None:
        return None

    base_path = Path(base_dir).resolve()
    if not base_path.is_dir():
        return None

    station = getattr(pkg, "station", "") or (pkg.data.station_name if getattr(pkg, "data", None) else "") or ""
    month = format_month_folder(getattr(pkg, "month", "")) or getattr(pkg, "month", "") or ""
    date_str = getattr(pkg, "date_str", "") or ""
    sub_num = getattr(pkg, "substation_number", None)
    sub_name = getattr(pkg, "substation_name", "")

    # Canonical directory structure: <REPORT_DIR>/<STATION>/<MONTH>/<DATE>/
    target_dir = base_path / station / month / date_str
    if not target_dir.is_dir():
        # Fallback to date folder directly under base_path if structure is flat
        if (base_path / date_str).is_dir():
            target_dir = base_path / date_str
        else:
            return None

    for pdf_file in sorted(target_dir.glob("*.pdf")):
        if pdf_file.name.startswith((".", "~$")):
            continue

        if sub_num is not None:
            try:
                pfx = extract_numerical_prefix(pdf_file.name)
                if pfx == sub_num:
                    return pdf_file.resolve()
            except ValueError:
                pass

            if pdf_file.name.startswith((f"{sub_num:03d}.", f"{sub_num}.")):
                return pdf_file.resolve()

        if sub_name and sub_name.lower() in pdf_file.stem.lower():
            return pdf_file.resolve()

    return None


def discover_us_audio_candidate_substations(
    environment: Any,
    target_dates: Sequence[Path | str],
) -> list[UsAudioCandidate]:
    """Discover candidate substations containing valid US+TEV survey folders and resolve deliverable PDFs.

    Extracts substation packages across dates using QuickReportExtractor.
    Resolves raw material directory and checks for UltraTEV survey presence via discover_ultratev_survey_dir().
    Resolves deliverable PDF targets: FULL REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.pdf and QUICK REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.pdf.
    Filters list strictly to substations possessing a valid US+TEV survey folder.

    Args:
        environment: ProjectEnvironment or utility environment instance.
        target_dates: Inspection date folders or strings to discover.

    Returns:
        list[UsAudioCandidate]: Filtered list of candidate substations with survey and PDF paths resolved.
    """
    extractor = QuickReportExtractor()
    folder_dates = [d.name if isinstance(d, Path) else str(d) for d in target_dates]
    packages = extractor.extract(environment, folders=folder_dates)

    full_report_dir = (
        environment.get_full_report_dir()
        if hasattr(environment, "get_full_report_dir")
        else getattr(environment, "base_path", Path(".")) / "FULL REPORT"
    )
    quick_report_dir = (
        environment.get_quick_report_dir()
        if hasattr(environment, "get_quick_report_dir")
        else getattr(environment, "base_path", Path(".")) / "QUICK REPORT"
    )

    candidates: list[UsAudioCandidate] = []
    for pkg in packages:
        raw_dir = environment.storage.get_substation_raw_data_dir(
            pkg.station,
            pkg.month,
            pkg.date_str,
            pkg.substation_number,
        )
        if not raw_dir:
            continue

        raw_dir_path = Path(raw_dir).resolve()
        survey_dir = discover_ultratev_survey_dir(raw_dir_path)
        if survey_dir is None or not survey_dir.exists():
            continue

        full_pdf = _find_deliverable_pdf(full_report_dir, pkg)
        quick_pdf = _find_deliverable_pdf(quick_report_dir, pkg)

        candidate = UsAudioCandidate(
            package=pkg,
            raw_data_dir=raw_dir_path,
            survey_dir=survey_dir,
            full_report_pdf=full_pdf,
            quick_report_pdf=quick_pdf,
        )
        candidate.sounds_output_dir = candidate.resolve_sounds_output_dir()
        candidates.append(candidate)

    return candidates


def select_us_audio_substations_interactive(
    candidates: list[UsAudioCandidate],
) -> list[UsAudioCandidate]:
    """Interactive single merged checklist selector for candidate substations across all dates.

    Formats checklist labels with date prefix and PDF availability tag:
      f"[{cand.package.date_str}] {cand.package.substation_name} [PDF READY]" if cand.full_report_pdf or cand.quick_report_pdf else f"[{cand.package.date_str}] {cand.package.substation_name} [NO PDF]"
    Reuses select_multiple to present a single merged checklist.
    Default state is all pre-checked with 'a' key shortcut to toggle.
    Zero-selection loops back safely without halting.

    Args:
        candidates: Discovered UsAudioCandidate objects.

    Returns:
        list[UsAudioCandidate]: Selected candidate substations.
    """
    if not candidates:
        return []

    options: list[SelectOption[UsAudioCandidate]] = []
    for cand in candidates:
        pkg = cand.package
        date_str = getattr(pkg, "date_str", "") if pkg else ""
        sub_name = getattr(pkg, "substation_name", None) or cand.display_name

        has_pdf = bool(
            (cand.full_report_pdf and Path(cand.full_report_pdf).is_file())
            or (cand.quick_report_pdf and Path(cand.quick_report_pdf).is_file())
        )
        pdf_tag = "[PDF READY]" if has_pdf else "[NO PDF]"
        title = f"[{date_str}] {sub_name} {pdf_tag}"
        options.append(SelectOption(title=title, value=cand, checked=True))

    while True:
        selected = select_multiple(
            "Select substations for ultrasound audio processing ('a' toggles all):",
            options,
        )
        if selected is None:
            return []
        if len(selected) == 0:
            print("No substations selected. Please select at least one substation or cancel.")
            continue
        return list(selected)


def run_generate_us_audio_action(environment: Any) -> UsAudioWorkflowSummary | None:
    """CLI utility action to generate 16-bit audio WAVs and/or embed sound annotations into report PDFs."""
    print("\n[UTILITY] Standalone Ultrasound Audio Generation & PDF Sound Embedding...")

    mode_options = [
        SelectOption(
            "Embed ultrasound sounds into existing report PDFs (Full & Quick Report)",
            "embed_pdf",
        ),
        SelectOption(
            "Export converted 16-bit WAV files to RAW DATA/US+TEV/sounds/",
            "export_wav",
        ),
        SelectOption(
            "Both (Export WAV files and embed into PDFs)",
            "both",
        ),
        SelectOption("Cancel", "__cancel__", shortcut_key="c"),
    ]

    selected_mode = select_one(
        "Generate US 16-bit Audio & Embed Sounds - Select Mode",
        mode_options,
    )
    if selected_mode in ("__cancel__", None):
        print("Operation cancelled.")
        return None

    date_mode_options = [
        SelectOption("Browse Date Folders (Interactive Checklist)", "browse_dates"),
        SelectOption("Enter Target Date(s) (Text Input / Range)", "enter_dates"),
        SelectOption("Cancel", "__cancel__", shortcut_key="c"),
    ]

    while True:
        date_mode = select_one(
            "Generate US 16-bit Audio & Embed Sounds - Select Date Mode",
            date_mode_options,
        )
        if date_mode in ("__cancel__", None):
            print("Operation cancelled.")
            return None

        if date_mode == "browse_dates":
            selected_dates = select_pahang_inspection_dates_interactive(environment)
        else:
            selected_dates = prompt_target_inspection_dates_with_ranges(environment)

        if not selected_dates:
            continue
        break

    folder_dates = [d.name if isinstance(d, Path) else str(d) for d in selected_dates]
    candidates = discover_us_audio_candidate_substations(environment, folder_dates)
    if not candidates:
        print("\n[WARN] No substations with valid US+TEV survey data found in selected date(s).")
        return None

    effective_mode: UsAudioMode = selected_mode  # type: ignore[assignment]
    if effective_mode == "embed_pdf":
        has_any_pdf = any(
            bool(
                (c.full_report_pdf and Path(c.full_report_pdf).is_file())
                or (c.quick_report_pdf and Path(c.quick_report_pdf).is_file())
            )
            for c in candidates
        )
        if not has_any_pdf:
            print(
                "\n[WARN] Deliverable PDFs were not found on disk for any of the discovered substations.\n"
                "Report PDFs (Full Report / Quick Report) must be compiled before sound annotations can be embedded."
            )
            fallback_options = [
                SelectOption(
                    "Switch to Mode 2: Export converted 16-bit WAV files to RAW DATA/US+TEV/sounds/",
                    "export_wav",
                ),
                SelectOption("Return to menu (Cancel)", "__cancel__", shortcut_key="c"),
            ]
            fallback_choice = select_one("Select Action", fallback_options)
            if fallback_choice != "export_wav":
                print("Operation cancelled. Please compile reports first.")
                return None
            effective_mode = "export_wav"

    selected_candidates = select_us_audio_substations_interactive(candidates)
    if not selected_candidates:
        print("No substations selected. Operation cancelled.")
        return None

    workflow = UsAudioWorkflow(mode=effective_mode)
    print(
        f"\n[INFO] Starting ultrasound audio workflow for {len(selected_candidates)} "
        f"substation(s) in {effective_mode.upper()} mode..."
    )

    def _on_progress(idx: int, total: int, pe_name: str) -> None:
        print(f"[{idx}/{total}] Processing US audio for {pe_name}...")

    summary = workflow.run_batch(selected_candidates, progress_callback=_on_progress)

    print("\n" + "=" * 80)
    print("ULTRASOUND AUDIO GENERATION & PDF EMBEDDING SUMMARY")
    print("=" * 80)
    print(f"Total Substations Processed: {summary.total_substations}")
    print(f"Total 16-bit WAVs Exported:  {summary.total_wavs_exported}")
    print(f"Total Sounds Embedded:       {summary.total_sounds_embedded}")
    print(f"Elapsed Time:                {summary.elapsed_time:.2f} seconds")
    if summary.errors:
        print(f"\nErrors ({len(summary.errors)}):")
        for err in summary.errors:
            print(f"  - {err}")
    print("=" * 80)
    return summary
