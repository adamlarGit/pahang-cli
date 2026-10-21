"""Ultrasound audio processing and ISO 32000-1 PDF sound annotation engine.

Delivers pure-Python in-memory 24-bit to 16-bit PCM downscaling, standalone 16-bit WAV file
export, and low-level PyMuPDF xref sound object & annotation injection.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
import wave

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from src.quick_report.prpd import (
    DiscoveredMeasurement,
    decode_ultrasonic_phase_plot,
    find_swg_feeder_survey_dir,
    find_tx_survey_dir,
)

# Canonical 1-to-1 chamber to component keyword mapping for switchgear cubicles
CHAMBER_COMPONENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "BREAKER": ("CIRCUIT_BREAKER", "BREAKER"),
    "CABLE": ("CABLE_BOX", "CABLES", "CABLE"),
    "BUSBAR": ("BUSBAR", "UPPER_BUSBARS", "LOWER_BUSBARS"),
    "PT": ("VT_CHAMBER", "VOLTAGE_TRANSFORMER", "VT", "PT"),
    "VT": ("VT_CHAMBER", "VOLTAGE_TRANSFORMER", "VT", "PT"),
    "FUSE": ("FUSE", "CABLE_BOX", "CABLES", "CABLE"),
}

# Transformer active HV scanning page keywords
TRANSFORMER_HV_SIDE_KEYWORDS: tuple[str, ...] = (
    "HV CABLE",
    "HV BUSHING",
    "HV CABLE SPLIT",
    "TRANSFORMER",
)


def find_sound_clip_anchor(page: fitz.Page) -> fitz.Rect | None:
    """Locate the 'Sound clip' marker on a PDF page and return target speaker rect in Column 2.

    Searches the page for the 'Sound clip' label. If present, detects the exact coordinates of
    the visible speaker icon image in Column 2 (x in [180, 250] pt vertically aligned within +/-15 pt
    of the label) and centers an 18x18 pt hit target directly superimposed over the visible icon.
    If no embedded image is present (e.g., text-only synthetic test sheets), falls back to the canonical
    Column 2 icon center coordinates (cx = 210.30 pt, cy = (inst.y0 + inst.y1) / 2.0).
    If the 'Sound clip' marker is absent, returns None.

    Args:
        page: PyMuPDF Page object.

    Returns:
        fitz.Rect | None: Target speaker annotation rectangle, or None if marker is absent.
    """
    rects = page.search_for("Sound clip")
    if not rects:
        return None
    inst = rects[0]

    # Discover exact visible speaker icon image in Column 2
    icon_rect: fitz.Rect | None = None
    try:
        for img in page.get_images():
            for r in page.get_image_rects(img[0]):
                if inst.y0 - 15.0 <= r.y0 <= inst.y1 + 15.0 and 180.0 <= r.x0 <= 250.0:
                    icon_rect = r
                    break
            if icon_rect is not None:
                break
    except Exception:
        pass

    if icon_rect is not None:
        cx = (icon_rect.x0 + icon_rect.x1) / 2.0
        cy = (icon_rect.y0 + icon_rect.y1) / 2.0
    else:
        cx = 210.30
        cy = (inst.y0 + inst.y1) / 2.0

    return fitz.Rect(cx - 9.0, cy - 9.0, cx + 9.0, cy + 9.0)


def extract_page_equipment_context(
    page: fitz.Page,
    package: Any = None,
) -> dict[str, Any]:
    r"""Extract physical equipment identifiers from a PDF deliverable page text.

    Extracts text and regex matches:
      - Switchgear panel index / feeder tag: r"Panel No\.\s*[:\n\r]*\s*([^\n\r]+)"
      - Feeder name: r"Panel Name\s*[:\n\r]*\s*([^\n\r]+)" (from Row 4)
      - Compartment area: r"Area\s*[:\n\r]*\s*([A-Za-z0-9_\s]+?)(?:\s+(?:Panel|IR|Time|Model|Tx)|$)"
      - Transformer unit index: r"Tx No\.\s*[:\n\r]*(?:TX|Tx|TRANSFORMER)?\s*(\d+)" and r"(?:Tx No\.|TX)\s*[:\n\r]*\s*(?:TX)?\s*(\d+)"

    Enforces TwoTierPanelMatchingPolicy:
      - Tier 1: Parses explicit digits from Panel No. if present (e.g. 1, Panel 1, 1 (CRB70001) -> 1).
      - Tier 2: If unnumbered utility code (e.g. CRB00764), uses extracted Panel Name to resolve
        via find_swg_feeder_survey_dir directly, falling back to package.equipment.switchgears[0].panels
        if package is provided.

    Args:
        page: PyMuPDF Page object.
        package: Optional SubstationTestsheetPackage containing equipment catalogs.

    Returns:
        dict[str, Any]: Dictionary containing extracted equipment context.
    """
    text = page.get_text("text")

    # 1. Switchgear panel index / feeder tag (captures "1", "Panel 1", "1 (CRB70001)", "CRB00764")
    m_panel = re.search(r"Panel No\.\s*[:\n\r]*\s*([^\n\r]+)", text)
    raw_panel_no = m_panel.group(1).strip() if m_panel else ""

    # 2. Feeder name (Row 4)
    m_name = re.search(r"Panel Name\s*[:\n\r]*\s*([^\n\r]+)", text)
    panel_name = m_name.group(1).strip() if m_name else ""

    # 3. Compartment area
    m_area = re.search(
        r"Area\s*[:\n\r]*\s*([A-Za-z0-9_\s]+?)(?:\s+(?:Panel|IR|Time|Model|Tx)|$)",
        text,
        re.MULTILINE,
    )
    area = m_area.group(1).strip() if m_area else ""

    # 4. Transformer unit index (strict delimiter requirement to prevent matching feeder names like "TX 1 INCOMER")
    tx_idx: int | None = None
    raw_tx_no = ""
    m_tx = (
        re.search(r"Tx No\.\s*[:\n\r]*\s*(?:TX|Tx|TRANSFORMER)?\s*(\d+)", text, re.IGNORECASE)
        or re.search(r"\b(?:Tx No\.|TX)\s*[:\n\r]+\s*(?:TX)?\s*(\d+)", text, re.IGNORECASE)
    )
    if m_tx:
        tx_idx = int(m_tx.group(1))
        raw_tx_no = m_tx.group(0).strip()

    # 5. Switchgear type, model, manufacturer
    m_eq = re.search(r"Equipment\s*[:\n\r]*\s*([^\n\r]+)", text)
    switchgear_type = m_eq.group(1).strip() if m_eq else ""
    if switchgear_type:
        switchgear_type = re.split(
            r"\s+(?:Manufacturer|Model|Rating|Time|Area|Panel|Tx)\b",
            switchgear_type,
            flags=re.IGNORECASE,
        )[0].strip()

    m_model = re.search(r"Model\s*[:\n\r]*\s*([^\n\r]+)", text)
    model = m_model.group(1).strip() if m_model else ""
    if model:
        model = re.split(
            r"\s+(?:Manufacturer|Equipment|Rating|Time|Area|Panel|Tx|Serial)\b",
            model,
            flags=re.IGNORECASE,
        )[0].strip()

    m_mfg = re.search(r"Manufacturer\s*[:\n\r]*\s*([^\n\r]+)", text)
    manufacturer = m_mfg.group(1).strip() if m_mfg else ""
    if manufacturer:
        manufacturer = re.split(
            r"\s+(?:Equipment|Model|Rating|Time|Area|Panel|Tx|Serial)\b",
            manufacturer,
            flags=re.IGNORECASE,
        )[0].strip()

    # Enforce TwoTierPanelMatchingPolicy
    panel_no: int | None = None
    if raw_panel_no:
        # Tier 1: Check for explicit digits (e.g. "1", "Panel 1", "1 (CRB70001)")
        m_tier1 = (
            re.search(r"^Panel\s*(\d+)", raw_panel_no, re.IGNORECASE)
            or re.search(r"^(\d+)", raw_panel_no)
        )
        if m_tier1:
            panel_no = int(m_tier1.group(1))

    if package is not None:
        eq = getattr(package, "equipment", None)
        if eq is None and hasattr(package, "data") and getattr(package, "data", None) is not None:
            eq = getattr(package.data, "equipment", None)
        elif eq is None and hasattr(package, "switchgears"):
            eq = package

        swgs = getattr(eq, "switchgears", ()) if eq is not None else ()
        clean_raw_panel = raw_panel_no.strip().upper()
        clean_panel_name = panel_name.strip().upper()

        if panel_no is None:
            # Tier 2: Check package switchgear panel catalog fallback
            for swg in swgs:
                for p in getattr(swg, "panels", ()):
                    feeder_tag = (getattr(p, "panel_feeder_no", "") or "").strip().upper()
                    p_name = (getattr(p, "name", "") or "").strip().upper()
                    matched = False
                    if feeder_tag and clean_raw_panel and feeder_tag == clean_raw_panel:
                        matched = True
                    elif feeder_tag and clean_panel_name and feeder_tag == clean_panel_name:
                        matched = True
                    elif p_name and clean_panel_name and p_name == clean_panel_name:
                        matched = True
                    elif p_name and clean_raw_panel and p_name == clean_raw_panel:
                        matched = True

                    if matched:
                        panel_no = getattr(p, "panel_no", None)
                        break
                if panel_no is not None:
                    break

        # Fall back switchgear_type, model, manufacturer to package if missing
        if (not switchgear_type or not model or not manufacturer) and swgs:
            swg_target = None
            if panel_no is not None:
                for swg in swgs:
                    for p in getattr(swg, "panels", ()):
                        if getattr(p, "panel_no", None) == panel_no:
                            swg_target = swg
                            break
                    if swg_target is not None:
                        break
            if swg_target is None and swgs:
                swg_target = swgs[0]

            if swg_target is not None:
                if not switchgear_type:
                    switchgear_type = getattr(swg_target, "switchgear_type", "") or ""
                if not model:
                    model = getattr(swg_target, "model", "") or ""
                if not manufacturer:
                    manufacturer = getattr(swg_target, "manufacturer", "") or ""

    return {
        "panel_no": panel_no,
        "panel_name": panel_name,
        "raw_panel_no": raw_panel_no,
        "area": area,
        "tx_idx": tx_idx,
        "raw_tx_no": raw_tx_no,
        "switchgear_type": switchgear_type,
        "model": model,
        "manufacturer": manufacturer,
    }


def get_measurement_db(meas: DiscoveredMeasurement) -> float:
    """Extract ultrasound dB reading from measurement directory for tie-breaking.

    Inspects ultrasonic_phase_plot.js and measurement_metadata.js (via ADR-0006 JSON raw_decode).
    If readings cannot be decoded, returns -999.0 as a baseline sentinel.
    """
    # 1. Try ultrasonic_phase_plot.js
    phase_plot_path = meas.meas_dir / "ultrasonic_phase_plot.js"
    if phase_plot_path.is_file():
        try:
            events = decode_ultrasonic_phase_plot(phase_plot_path)
            if events:
                return max(float(e.get("amplitude", e.get("peak", -999.0))) for e in events)
        except Exception:
            pass

    # 2. Try measurement_metadata.js via ADR-0006 JSON raw_decode
    meta_path = meas.meas_dir / "measurement_metadata.js"
    if meta_path.is_file():
        try:
            raw_text = meta_path.read_text(encoding="utf-8", errors="ignore")
            start_idx = raw_text.find("{")
            if start_idx != -1:
                meta_dict, _ = json.JSONDecoder().raw_decode(raw_text[start_idx:])
                trend = meta_dict.get("Trend", [])
                if trend and isinstance(trend, list) and isinstance(trend[0], dict):
                    db_val = trend[0].get("$MEASURE_DBUV")
                    if db_val is not None:
                        return float(db_val)

                for group in meta_dict.get("measurement_fields", []):
                    for field in group.get("fields", []):
                        if field.get("fieldname") == "$MEASURE_DBUV":
                            return float(field.get("data", -999.0))
        except Exception:
            pass

    return -999.0


def validate_and_return_8k_wav(meas: DiscoveredMeasurement) -> Path:
    """Validate mandatory presence of non-empty 8k.wav and return its Path.

    Raises:
        FileNotFoundError: If 8k.wav does not exist or has 0 bytes.
    """
    wav_path = meas.meas_dir / "8k.wav"
    if not wav_path.is_file():
        raise FileNotFoundError(
            f"Missing mandatory 8k.wav for measurement: {meas.label} in {meas.meas_dir}"
        )
    if wav_path.stat().st_size == 0:
        raise FileNotFoundError(
            f"Mandatory 8k.wav is empty (0 bytes) for measurement: {meas.label} in {meas.meas_dir}"
        )
    return wav_path


_validate_and_return_8k_wav = validate_and_return_8k_wav


def resolve_measurement_audio_for_page(
    survey_root: Path,
    measurements: list[DiscoveredMeasurement],
    page_context: dict[str, Any],
) -> Path | None:
    """Canonical mapping resolver linking a deliverable PDF page to its UltraTEV 8k.wav audio recording.

    Filters measurements to tech == "US".
    Enforces VcbAudioAttributionPolicy, TransformerAudioAttributionPolicy, and RmuAudioAttributionPolicy.
    Enforces mandatory presence of non-empty 8k.wav (raising FileNotFoundError if missing).

    Args:
        survey_root: Substation survey root directory.
        measurements: List of all auto-discovered survey measurements.
        page_context: Extracted page equipment context from extract_page_equipment_context.

    Returns:
        Path | None: Resolved path to the target 8k.wav file, or None if unmeasured or non-acoustic.
    """
    us_meas = [m for m in measurements if m.tech == "US"]
    if not us_meas:
        return None

    area = str(page_context.get("area", "")).strip().upper()
    tx_idx = page_context.get("tx_idx")

    # Guard: Non-acoustic SECONDARY COMPARTMENT or empty area
    if not area or "SECONDARY" in area:
        return None

    # 1. Transformer Audio Attribution Policy
    # Only applies to active HV side scanning pages
    is_hv_side_page = any(kw in area for kw in TRANSFORMER_HV_SIDE_KEYWORDS)
    if is_hv_side_page:
        eff_tx_idx = tx_idx if tx_idx is not None else 1
        tx_dir = find_tx_survey_dir(survey_root, eff_tx_idx) if survey_root and survey_root.exists() else None

        candidates: list[DiscoveredMeasurement] = []
        for m in us_meas:
            matched = False
            if tx_dir and (m.meas_dir == tx_dir or tx_dir in m.meas_dir.parents):
                matched = True
            elif f"TX{eff_tx_idx}" in m.label.upper() or f"TX{eff_tx_idx}" in m.asset.upper():
                matched = True
            elif eff_tx_idx == 1 and (
                "_TX_" in m.label.upper()
                or m.asset.upper() in ("TX", "TRANSFORMER")
                or "TRANSFORMER" in m.subasset.upper()
            ):
                matched = True

            if matched:
                candidates.append(m)

        if not candidates:
            return None

        selected = max(candidates, key=get_measurement_db)
        return _validate_and_return_8k_wav(selected)

    # 2. Switchgear Cubicle (VCB / RMU)
    panel_no = page_context.get("panel_no") or 0
    raw_panel_no = str(page_context.get("raw_panel_no", "")).strip()
    panel_name = str(page_context.get("panel_name", "")).strip()

    feeder_dir = (
        find_swg_feeder_survey_dir(survey_root, panel_no=panel_no, feeder_no=raw_panel_no, panel_name=panel_name)
        if survey_root and survey_root.exists()
        else None
    )

    # Collect measurements belonging to this panel
    panel_measurements: list[DiscoveredMeasurement] = []
    if feeder_dir:
        panel_measurements = [
            m for m in us_meas
            if m.meas_dir == feeder_dir or feeder_dir in m.meas_dir.parents
        ]

    if not panel_measurements:
        targets: list[str] = []
        if panel_no > 0:
            targets.extend([
                f"PANEL_{panel_no}",
                f"PANEL {panel_no}",
                f"FEEDER_{panel_no}",
                f"FEEDER {panel_no}",
                f"PANEL_{str(panel_no).zfill(2)}",
                f"FEEDER_{str(panel_no).zfill(2)}",
            ])
        if panel_name:
            targets.append(panel_name.strip().upper())
            targets.append(panel_name.strip().upper().replace(" ", "_"))
        if raw_panel_no:
            targets.append(raw_panel_no.strip().upper())
            targets.append(raw_panel_no.strip().upper().replace(" ", "_"))

        if targets:
            panel_measurements = [
                m for m in us_meas
                if m.asset.upper() not in ("TX", "TRANSFORMER")
                and any(t in m.subasset.upper() or t in m.label.upper() for t in targets)
            ]

    # Equipment type detection: distinguish RMU from modular VCB cubicles
    model = str(page_context.get("model", "")).strip().upper()
    switchgear_type = str(page_context.get("switchgear_type", "")).strip().upper()

    is_rmu = (
        any(m.asset.upper() == "RMU" or m.label.upper().startswith("RMU_") for m in us_meas)
        or "RMU" in switchgear_type
        or "INS24" in model
        or (feeder_dir and "RMU" in feeder_dir.as_posix().upper())
    )

    # Check for RMU board-level fallback (strictly restricted to RMU feeder pages: CABLE or FUSE)
    is_rmu_feeder_page = "CABLE" in area or "FUSE" in area
    if not panel_measurements:
        if is_rmu and is_rmu_feeder_page:
            has_feeder_subfolders = False
            if survey_root and survey_root.exists():
                try:
                    for d in survey_root.iterdir():
                        if d.is_dir() and d.name.upper().startswith(("SWG", "VCB", "RMU")):
                            for sub in d.iterdir():
                                if sub.is_dir() and any(k in sub.name.upper() for k in ("FEEDER", "PANEL")):
                                    has_feeder_subfolders = True
                                    break
                except OSError:
                    pass

            if not has_feeder_subfolders:
                board_level = [
                    m for m in us_meas
                    if m.label.upper() in ("RMU_US", "SWG_US")
                    or (m.asset.upper() in ("RMU", "SWG") and (not m.component or m.component.upper() in ("$NONE", "NONE", "")))
                ]
                if board_level:
                    selected = max(board_level, key=get_measurement_db)
                    return _validate_and_return_8k_wav(selected)

        # Zero cross-chamber leakage for VCB or unmeasured panels
        return None

    # RmuAudioAttributionPolicy: single untagged US recordings match active cable / fuse scanning page
    if is_rmu and is_rmu_feeder_page and len(panel_measurements) == 1:
        single_m = panel_measurements[0]
        if not single_m.component or single_m.component.upper() in ("$NONE", "NONE", ""):
            return _validate_and_return_8k_wav(single_m)

    # VcbAudioAttributionPolicy: Strict 1-to-1 chamber mapping
    chamber_matched: list[DiscoveredMeasurement] = []
    for chamber_key, component_keys in CHAMBER_COMPONENT_KEYWORDS.items():
        if chamber_key in area:
            candidates = [
                m for m in panel_measurements
                if m.component and any(ck in m.component.upper() for ck in component_keys)
            ]
            if chamber_key == "BUSBAR":
                # Multi-measurement tie-breaking: prioritize $UPPER_BUSBARS over $LOWER_BUSBARS
                upper = [
                    m for m in candidates
                    if "UPPER" in m.component.upper() or "UPPER" in m.label.upper()
                ]
                chamber_matched = upper if upper else candidates
            elif chamber_key == "FUSE":
                # Multi-measurement tie-breaking: prioritize $FUSE over fallback $CABLE_BOX if present
                fuse_candidates = [
                    m for m in candidates
                    if "FUSE" in m.component.upper() or "FUSE" in m.label.upper()
                ]
                chamber_matched = fuse_candidates if fuse_candidates else candidates
            else:
                chamber_matched = candidates
            break

    if not chamber_matched:
        # Zero cross-chamber leaking: single recordings apply strictly to their own chamber and are never cloned.
        return None

    # Tie-breaking: select recording with highest ultrasound dB reading
    selected = max(chamber_matched, key=get_measurement_db)
    return _validate_and_return_8k_wav(selected)





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


def _is_matching_sound_rect(candidate_rect: fitz.Rect, target_rect: fitz.Rect) -> bool:
    """Check if candidate sound annotation matches target hit rect.

    Matches if rectangles intersect, or if candidate is within +/-20 pt vertically in Column 2
    (x in [170, 270] pt), ensuring existing annotations (e.g. from prior legacy offset coordinates)
    are recognized and migrated in place.
    """
    if candidate_rect.intersects(target_rect):
        return True
    return (
        abs(candidate_rect.y0 - target_rect.y0) <= 20.0
        and 170.0 <= candidate_rect.x0 <= 270.0
    )


def _find_existing_sound_annot(
    doc: fitz.Document,
    page: fitz.Page,
    rect: fitz.Rect,
) -> tuple[int, int] | None:
    r"""Find an existing /Subtype /Sound annotation matching target rect or row.

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

            if is_sound and _is_matching_sound_rect(annot.rect, rect):
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
                    if _is_matching_sound_rect(mupdf_rect, rect):
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
    exists for this slot, updates the existing sound object stream and annotation properties
    (/Rect, /CA 0.0, /Border [0 0 0], and empty /AP Form XObject) directly and returns
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
    page_h = page.rect.height
    pdf_y0 = page_h - rect.y1
    pdf_y1 = page_h - rect.y0

    existing = _find_existing_sound_annot(doc, page, rect)
    if existing is not None:
        annot_xref, sound_xref = existing
        # 1. Update audio stream and sampling metadata
        doc.update_stream(sound_xref, pcm_bytes)
        doc.xref_set_key(sound_xref, "R", str(framerate))
        doc.xref_set_key(sound_xref, "C", str(channels))

        # 2. Update hit rect, transparency, and empty appearance Form XObject
        doc.xref_set_key(
            annot_xref,
            "Rect",
            f"[{rect.x0:.2f} {pdf_y0:.2f} {rect.x1:.2f} {pdf_y1:.2f}]",
        )
        doc.xref_set_key(annot_xref, "CA", "0.0")
        doc.xref_set_key(annot_xref, "Border", "[0 0 0]")

        app_info = doc.xref_get_key(annot_xref, "AP")
        if app_info[0] == "null" or not app_info[1]:
            app_xref = doc.get_new_xref()
            doc.update_object(
                app_xref,
                f"<< /Type /XObject /Subtype /Form /BBox [0 0 {rect.width:.2f} {rect.height:.2f}] /Resources << >> >>",
            )
            doc.update_stream(app_xref, b"")
            doc.xref_set_key(annot_xref, "AP", f"<< /N {app_xref} 0 R >>")
        return annot_xref

    # 1. Allocate and populate Sound Object stream
    sound_xref = doc.get_new_xref()
    doc.update_object(
        sound_xref,
        f"<< /Type /Sound /R {framerate} /C {channels} /B 16 /E /Signed >>",
    )
    doc.update_stream(sound_xref, pcm_bytes)

    # 2. Transparent Empty Appearance Form XObject
    app_xref = doc.get_new_xref()
    doc.update_object(
        app_xref,
        f"<< /Type /XObject /Subtype /Form /BBox [0 0 {rect.width:.2f} {rect.height:.2f}] /Resources << >> >>",
    )
    doc.update_stream(app_xref, b"")

    # 3. Sound Annotation Dictionary with /CA 0.0, /Border [0 0 0], empty /AP
    annot_xref = doc.get_new_xref()
    annot_dict = (
        f"<< /Type /Annot /Subtype /Sound "
        f"/Rect [{rect.x0:.2f} {pdf_y0:.2f} {rect.x1:.2f} {pdf_y1:.2f}] "
        f"/Sound {sound_xref} 0 R "
        f"/Name /Speaker "
        f"/CA 0.0 "
        f"/Border [0 0 0] "
        f"/F 4 "
        f"/AP << /N {app_xref} 0 R >> "
        f"/P {page.xref} 0 R >>"
    )
    doc.update_object(annot_xref, annot_dict)

    # 4. Register annotation xref into page /Annots
    _register_annot_xref_to_page(doc, page, annot_xref)

    return annot_xref


