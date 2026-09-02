"""Native Python PRPD graph generator and survey directory resolution module (Option B).

Implements binary FlatBuffers and JSON decoding for UltraTEV survey data, 4-tier
density scatter binning, deterministic asset discovery, and DocxTemplate InlineImage binding.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
from pathlib import Path
import re
import struct
from typing import Any

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


def safe_path(p: Path | str) -> str:
    """Ensure Windows extended-length path compatibility (\\\\?\\)."""
    s = str(Path(p).resolve())
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def decode_tev_event_data(filepath: Path | str) -> list[dict[str, Any]]:
    """Decode gzipped base64 FlatBuffers eventData.js (identifier 'UE01').

    Returns a list of event dictionaries:
    [{'peak': float, 'integral': int, 'phase': int, 'cycle': int, 'risetime': int, 'width': int, 'amplitude': float}]
    """
    with open(safe_path(filepath), "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    m = re.search(r'var\s+eventData\s*=\s*"([^"]+)"', text)
    if not m:
        raise ValueError(f"Could not extract eventData string from {filepath}")

    b64_str = m.group(1)
    raw_bytes = gzip.decompress(base64.b64decode(b64_str))

    root_offset = struct.unpack_from("<I", raw_bytes, 0)[0]
    soffset = struct.unpack_from("<i", raw_bytes, root_offset)[0]
    vtable_offset = root_offset - soffset

    field0_offset_in_table = struct.unpack_from("<H", raw_bytes, vtable_offset + 4)[0]
    if field0_offset_in_table == 0:
        return []

    vector_loc = root_offset + field0_offset_in_table
    vector_offset_rel = struct.unpack_from("<I", raw_bytes, vector_loc)[0]
    vector_pos = vector_loc + vector_offset_rel
    vector_len = struct.unpack_from("<I", raw_bytes, vector_pos)[0]

    events: list[dict[str, Any]] = []
    for i in range(vector_len):
        elem_pos = vector_pos + 4 + i * 24
        peak, integral, phase, cycle, risetime, width, tf_t, tf_f = struct.unpack_from(
            "<fiHHHHff", raw_bytes, elem_pos
        )
        events.append(
            {
                "peak": float(peak),
                "integral": int(integral),
                "phase": int(phase),
                "cycle": int(cycle),
                "risetime": int(risetime),
                "width": int(width),
                "tf_t": float(tf_t),
                "tf_f": float(tf_f),
                "amplitude": float(peak),
            }
        )

    return events


def decode_ultrasonic_phase_plot(filepath: Path | str) -> list[dict[str, Any]]:
    """Decode ultrasonic_phase_plot.js containing var ultra_events = {"data": [[peak, phase, cycle], ...]}.

    Returns a list of event dictionaries:
    [{'peak': float, 'phase': int, 'cycle': int, 'amplitude': float}]
    """
    with open(safe_path(filepath), "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    m = re.search(r"var\s+ultra_events\s*=\s*(\{.*?\});", text, re.DOTALL)
    if not m:
        m = re.search(r"var\s+ultra_events\s*=\s*(\{.*\})", text, re.DOTALL)
    if not m:
        raise ValueError(f"Could not extract ultra_events from {filepath}")

    raw_json = m.group(1)
    data_dict = json.loads(raw_json)
    raw_events = data_dict.get("data", [])

    events: list[dict[str, Any]] = []
    for elem in raw_events:
        peak = float(elem[0])
        phase = int(elem[1])
        cycle = int(elem[2])
        # Ultrasonic amplitude rounding to nearest 1/3 of a dB (UltraTEV spec)
        rounded_amp = round(peak * 3.0) / 3.0
        events.append(
            {
                "peak": peak,
                "phase": phase,
                "cycle": cycle,
                "amplitude": rounded_amp,
            }
        )

    return events


def generate_prpd_figure(
    events: list[dict[str, Any]],
    tech_type: str = "TEV",
    output_path: Path | str | None = None,
    title: str | None = None,
    show_sine: bool = False,
    dpi: int = 200,
    figsize: tuple[float, float] = (10, 4.2),
) -> Path | None:
    """Render a high-resolution PRPD graph matching UltraTEV's visual appearance and 4-tier color bins."""
    is_tev = tech_type.upper() == "TEV"
    if is_tev:
        ymin, ymax = 0.0, 60.0
        ylabel = "dB"
    else:
        ymin, ymax = -10.0, 71.0
        ylabel = "dBuV"

    point_counts: dict[tuple[int, float], int] = {}
    for e in events:
        phase = int(e["phase"]) % 360
        amp = float(e["amplitude"])
        key = (phase, amp)
        point_counts[key] = point_counts.get(key, 0) + 1

    max_count = max(point_counts.values()) if point_counts else 1

    count_thresh_frac = [0.1, 0.45, 0.8]
    thresh = [
        max_count * count_thresh_frac[0],
        max_count * count_thresh_frac[1],
        max_count * count_thresh_frac[2],
    ]

    t0 = max(1, round(thresh[0])) if round(thresh[0]) > 0 else 1
    t1 = max(t0, round(thresh[1]))
    t2 = max(t1, round(thresh[2]))
    t_max = max(t2, round(max_count))

    bin1_x, bin1_y = [], []
    bin2_x, bin2_y = [], []
    bin3_x, bin3_y = [], []
    bin4_x, bin4_y = [], []

    for (phase, amp), count in point_counts.items():
        if count <= thresh[0]:
            bin1_x.append(phase)
            bin1_y.append(amp)
        elif count <= thresh[1]:
            bin2_x.append(phase)
            bin2_y.append(amp)
        elif count <= thresh[2]:
            bin3_x.append(phase)
            bin3_y.append(amp)
        else:
            bin4_x.append(phase)
            bin4_y.append(amp)

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.grid(True, which="both", color="#E2E2E2", linestyle="-", linewidth=0.8, zorder=1)

    if show_sine:
        deg = np.linspace(0, 360, 361)
        sine_val = np.abs(np.sin(np.radians(deg)))
        sine_y = ymin + (ymax - ymin) * sine_val
        ax.plot(deg, sine_y, color="#555555", linewidth=1.1, linestyle="-", zorder=2, label="_nolegend_")

    dot_size = 12.0
    if bin1_x:
        ax.scatter(bin1_x, bin1_y, c="#00FF00", s=dot_size, marker="o", edgecolors="none", zorder=3)
    if bin2_x:
        ax.scatter(bin2_x, bin2_y, c="#0000FF", s=dot_size, marker="o", edgecolors="none", zorder=4)
    if bin3_x:
        ax.scatter(bin3_x, bin3_y, c="#FF0000", s=dot_size, marker="o", edgecolors="none", zorder=5)
    if bin4_x:
        ax.scatter(bin4_x, bin4_y, c="#640000", s=dot_size, marker="o", edgecolors="none", zorder=6)

    ax.set_xlim(0, 360)
    ax.set_xticks([0, 90, 180, 270, 360])
    ax.set_ylim(ymin, ymax)

    if is_tev:
        ax.set_yticks(np.arange(0, 61, 10))
    else:
        ax.set_yticks(np.arange(-10, 72, 10))

    ax.set_xlabel("Degrees", fontsize=10, fontweight="normal", color="#000000")
    ax.set_ylabel(ylabel, fontsize=10, fontweight="normal", color="#000000")

    for spine in ax.spines.values():
        spine.set_color("#000000")
        spine.set_linewidth(1.0)

    ax.tick_params(axis="both", colors="#000000", labelsize=9, length=4, width=0.8)

    patch_green = mpatches.Patch(color="#00FF00", label=f"< {t0}")
    patch_blue = mpatches.Patch(color="#0000FF", label=f"{t0} < {t1}")
    patch_red = mpatches.Patch(color="#FF0000", label=f"{t1} < {t2}")
    patch_darkred = mpatches.Patch(color="#640000", label=f"{t2} < {t_max}")

    ax.legend(
        handles=[patch_green, patch_blue, patch_red, patch_darkred],
        loc="upper left",
        frameon=True,
        framealpha=0.95,
        facecolor="white",
        edgecolor="#D0D0D0",
        fontsize=8.5,
        borderaxespad=0.6,
        handlelength=1.0,
        handleheight=1.0,
    )

    if title:
        ax.set_title(title, fontsize=11, fontweight="bold", color="#333333", pad=10)

    plt.tight_layout()

    out_file = None
    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(safe_path(out_file), dpi=dpi, facecolor="white", edgecolor="none")
    plt.close(fig)
    return out_file


def discover_ultratev_survey_dir(raw_data_dir: Path | str | None) -> Path | None:
    """Discover the root UltraTEV survey directory inside a substation's RAW DATA folder."""
    if not raw_data_dir:
        return None
    raw_path = Path(raw_data_dir)
    if not raw_path.exists():
        return None

    # Check for direct US+TEV subfolder
    candidate_roots = [
        raw_path / "RAW DATA" / "US+TEV",
        raw_path / "US+TEV",
        raw_path,
    ]

    for candidate in candidate_roots:
        if candidate.exists() and candidate.is_dir():
            # If candidate itself has SWG or TX
            if (candidate / "SWG").exists() or (candidate / "TX").exists() or (candidate / "TX1").exists():
                return candidate
            # Or child survey stems (e.g. 20260810T104017_043-STESEN-BAS-DAN-TEKSI)
            for child in sorted(candidate.iterdir(), reverse=True):
                if child.is_dir() and ((child / "SWG").exists() or (child / "TX").exists() or (child / "TX1").exists()):
                    return child

    # Deep search fallback for any folder containing SWG and (TX or TX1 or resources)
    try:
        for child in sorted(raw_path.rglob("SWG"), reverse=True):
            parent = child.parent
            if parent.is_dir() and ((parent / "TX").exists() or (parent / "TX1").exists() or (parent / "resources").exists()):
                return parent
    except Exception:
        pass

    return None


def find_swg_feeder_survey_dir(
    survey_root: Path,
    panel_no: int,
    feeder_no: str = "",
    panel_name: str = "",
) -> Path | None:
    """Find the target SWG feeder survey directory using 3-tier precedence."""
    swg_dir = survey_root / "SWG"
    if not swg_dir.exists():
        return None

    candidate_subdirs = [d for d in swg_dir.iterdir() if d.is_dir()]

    # Tier 1: Match panel_no (Column A index, 1-based)
    if panel_no > 0:
        p_num_str = str(panel_no)
        for d in candidate_subdirs:
            d_name = d.name.upper()
            if d_name in (f"FEEDER_{p_num_str}", f"FEEDER {p_num_str}", f"PANEL_{p_num_str}", f"PANEL {p_num_str}"):
                return d

    # Tier 2: Match exact folder name against panel_name / feeder_no
    clean_pname = panel_name.strip().upper().replace(" ", "_")
    clean_feeder = feeder_no.strip().upper().replace(" ", "_")
    for d in candidate_subdirs:
        d_upper = d.name.upper()
        if d_upper in (panel_name.strip().upper(), clean_pname, feeder_no.strip().upper(), clean_feeder):
            return d

    # Tier 3: Match digits in feeder_no (handling leading zeroes like F02 -> 2)
    digits = re.findall(r"\d+", feeder_no) or re.findall(r"\d+", panel_name)
    if digits:
        raw_digit = digits[0]
        try:
            int_digit = str(int(raw_digit))
        except ValueError:
            int_digit = raw_digit
        target_variants = {
            f"FEEDER_{int_digit}",
            f"FEEDER {int_digit}",
            f"FEEDER_{raw_digit}",
            f"FEEDER {raw_digit}",
            f"PANEL_{int_digit}",
            f"PANEL {int_digit}",
            f"PANEL_{raw_digit}",
            f"PANEL {raw_digit}",
        }
        for d in candidate_subdirs:
            if d.name.upper() in target_variants:
                return d

    return None


def find_tx_survey_dir(survey_root: Path, tx_idx: int = 1) -> Path | None:
    """Find the target Transformer survey directory (supporting 1-TX and multi-TX layouts)."""
    # 1. Multi-TX folder pattern (e.g. TX1/Transformer/, TX2/Transformer/)
    tx_folder = survey_root / f"TX{tx_idx}"
    if tx_folder.exists():
        tf_sub = tx_folder / "Transformer"
        return tf_sub if tf_sub.exists() else tx_folder

    # 2. Single-TX folder pattern (TX/Transformer/)
    if tx_idx == 1:
        tx_folder = survey_root / "TX"
        if tx_folder.exists():
            tf_sub = tx_folder / "Transformer"
            return tf_sub if tf_sub.exists() else tx_folder

    # 3. Fallback to any folder containing Transformer_<N>
    for child in survey_root.iterdir():
        if child.is_dir() and f"TX{tx_idx}" in child.name.upper():
            return child

    return None


def find_latest_measurement_dir(feeder_or_tx_dir: Path, tech_type: str) -> Path | None:
    """Find the latest timestamped measurement directory containing valid payload."""
    if not feeder_or_tx_dir or not feeder_or_tx_dir.exists():
        return None

    is_tev = tech_type.upper() == "TEV"
    target_pattern = "_TEV" if is_tev else "_Ultrasonic"
    target_payload = "eventData.js" if is_tev else "ultrasonic_phase_plot.js"

    candidate_dirs = [
        d
        for d in feeder_or_tx_dir.iterdir()
        if d.is_dir() and target_pattern.upper() in d.name.upper()
    ]
    # Sort descending by timestamp / name
    candidate_dirs.sort(key=lambda x: x.name, reverse=True)

    for d in candidate_dirs:
        payload_file = d / target_payload
        if payload_file.exists() and payload_file.stat().st_size > 0:
            return d

    return None


def generate_prpd_graphs_for_swg_panel(
    survey_root: Path | None,
    panel_no: int,
    output_dir: Path,
    feeder_no: str = "",
    panel_name: str = "",
) -> tuple[Path | None, Path | None]:
    """Generate US and TEV PRPD PNG graph images for a switchgear panel.

    Returns (us_png_path, tev_png_path).
    """
    if not survey_root:
        return None, None

    feeder_dir = find_swg_feeder_survey_dir(
        survey_root=survey_root,
        panel_no=panel_no,
        feeder_no=feeder_no,
        panel_name=panel_name,
    )
    if not feeder_dir:
        return None, None

    us_png: Path | None = None
    tev_png: Path | None = None

    # 1. Ultrasonic Graph
    us_dir = find_latest_measurement_dir(feeder_dir, "US")
    if us_dir:
        us_file = us_dir / "ultrasonic_phase_plot.js"
        if us_file.exists():
            try:
                events = decode_ultrasonic_phase_plot(us_file)
                us_out = output_dir / f"prpd_swg_panel{panel_no}_us.png"
                us_png = generate_prpd_figure(events, tech_type="US", output_path=us_out)
            except Exception:
                us_png = None

    # 2. TEV Graph
    tev_dir = find_latest_measurement_dir(feeder_dir, "TEV")
    if tev_dir:
        tev_file = tev_dir / "eventData.js"
        if tev_file.exists():
            try:
                events = decode_tev_event_data(tev_file)
                tev_out = output_dir / f"prpd_swg_panel{panel_no}_tev.png"
                tev_png = generate_prpd_figure(events, tech_type="TEV", output_path=tev_out)
            except Exception:
                tev_png = None

    return us_png, tev_png


def generate_prpd_graphs_for_transformer(
    survey_root: Path | None,
    tx_idx: int,
    output_dir: Path,
) -> tuple[Path | None, Path | None]:
    """Generate US and TEV PRPD PNG graph images for a transformer.

    Returns (us_png_path, tev_png_path).
    """
    if not survey_root:
        return None, None

    tx_dir = find_tx_survey_dir(survey_root=survey_root, tx_idx=tx_idx)
    if not tx_dir:
        return None, None

    us_png: Path | None = None
    tev_png: Path | None = None

    # 1. Ultrasonic Graph
    us_dir = find_latest_measurement_dir(tx_dir, "US")
    if us_dir:
        us_file = us_dir / "ultrasonic_phase_plot.js"
        if us_file.exists():
            try:
                events = decode_ultrasonic_phase_plot(us_file)
                us_out = output_dir / f"prpd_tx{tx_idx}_us.png"
                us_png = generate_prpd_figure(events, tech_type="US", output_path=us_out)
            except Exception:
                us_png = None

    # 2. TEV Graph (if any recorded on TX)
    tev_dir = find_latest_measurement_dir(tx_dir, "TEV")
    if tev_dir:
        tev_file = tev_dir / "eventData.js"
        if tev_file.exists():
            try:
                events = decode_tev_event_data(tev_file)
                tev_out = output_dir / f"prpd_tx{tx_idx}_tev.png"
                tev_png = generate_prpd_figure(events, tech_type="TEV", output_path=tev_out)
            except Exception:
                tev_png = None

    return us_png, tev_png


def generate_all_substation_prpd_graphs(
    survey_root: Path | str | None,
    output_dir: Path | str,
) -> dict[str, Any]:
    """Discover all SWG feeders and TX units and generate all PRPD PNG graphs in one pass.

    Returns structured catalog:
    {
        "swg": {
            1: {"us": Path(...), "tev": Path(...)},
            2: {"us": Path(...), "tev": Path(...)},
            ...
        },
        "tx": {
            1: {"us": Path(...), "tev": Path(...) or None},
            ...
        }
    }
    """
    catalog: dict[str, dict[int, dict[str, Path | None]]] = {
        "swg": {},
        "tx": {},
    }
    if not survey_root:
        return catalog

    survey_path = Path(survey_root)
    if not survey_path.exists():
        return catalog

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. SWG Feeders
    swg_dir = survey_path / "SWG"
    if swg_dir.exists() and swg_dir.is_dir():
        candidate_feeders = [d for d in swg_dir.iterdir() if d.is_dir()]
        for feeder_dir in sorted(candidate_feeders, key=lambda d: d.name):
            digits = re.findall(r"\d+", feeder_dir.name)
            if digits:
                try:
                    panel_idx = int(digits[0])
                except ValueError:
                    panel_idx = len(catalog["swg"]) + 1
            else:
                panel_idx = len(catalog["swg"]) + 1

            us_png: Path | None = None
            tev_png: Path | None = None

            us_meas = find_latest_measurement_dir(feeder_dir, "US")
            if us_meas:
                us_file = us_meas / "ultrasonic_phase_plot.js"
                if us_file.exists():
                    try:
                        events = decode_ultrasonic_phase_plot(us_file)
                        us_out = out_path / f"prpd_swg_panel{panel_idx}_us.png"
                        us_png = generate_prpd_figure(events, tech_type="US", output_path=us_out)
                    except Exception:
                        us_png = None

            tev_meas = find_latest_measurement_dir(feeder_dir, "TEV")
            if tev_meas:
                tev_file = tev_meas / "eventData.js"
                if tev_file.exists():
                    try:
                        events = decode_tev_event_data(tev_file)
                        tev_out = out_path / f"prpd_swg_panel{panel_idx}_tev.png"
                        tev_png = generate_prpd_figure(events, tech_type="TEV", output_path=tev_out)
                    except Exception:
                        tev_png = None

            catalog["swg"][panel_idx] = {
                "us": us_png,
                "tev": tev_png,
            }

    # 2. Transformer (TX) units
    candidate_tx_indices: set[int] = set()
    for child in survey_path.iterdir():
        if child.is_dir():
            d_upper = child.name.upper()
            if d_upper.startswith("TX") or "TRANSFORMER" in d_upper:
                digits = re.findall(r"\d+", d_upper)
                if digits:
                    candidate_tx_indices.add(int(digits[0]))
                else:
                    candidate_tx_indices.add(1)
    if not candidate_tx_indices:
        if (survey_path / "TX").exists():
            candidate_tx_indices.add(1)

    for tx_idx in sorted(candidate_tx_indices):
        tx_dir = find_tx_survey_dir(survey_path, tx_idx=tx_idx)
        if not tx_dir or not tx_dir.exists():
            continue

        us_png = None
        tev_png = None

        us_meas = find_latest_measurement_dir(tx_dir, "US")
        if us_meas:
            us_file = us_meas / "ultrasonic_phase_plot.js"
            if us_file.exists():
                try:
                    events = decode_ultrasonic_phase_plot(us_file)
                    us_out = out_path / f"prpd_tx{tx_idx}_us.png"
                    us_png = generate_prpd_figure(events, tech_type="US", output_path=us_out)
                except Exception:
                    us_png = None

        tev_meas = find_latest_measurement_dir(tx_dir, "TEV")
        if tev_meas:
            tev_file = tev_meas / "eventData.js"
            if tev_file.exists():
                try:
                    events = decode_tev_event_data(tev_file)
                    tev_out = out_path / f"prpd_tx{tx_idx}_tev.png"
                    tev_png = generate_prpd_figure(events, tech_type="TEV", output_path=tev_out)
                except Exception:
                    tev_png = None

        catalog["tx"][tx_idx] = {
            "us": us_png,
            "tev": tev_png,
        }

    return catalog


def build_prpd_inline_images(
    doc_tpl: DocxTemplate,
    us_png: Path | None,
    tev_png: Path | None,
    width_mm: float = 82.0,
) -> tuple[InlineImage | str, InlineImage | str]:
    """Build DocxTemplate InlineImage instances for us.prpd and tev.prpd, or return clean ''."""
    us_inline: InlineImage | str = ""
    tev_inline: InlineImage | str = ""

    if us_png and Path(us_png).exists():
        us_inline = InlineImage(doc_tpl, str(us_png), width=Mm(width_mm))

    if tev_png and Path(tev_png).exists():
        tev_inline = InlineImage(doc_tpl, str(tev_png), width=Mm(width_mm))

    return us_inline, tev_inline


__all__ = [
    "build_prpd_inline_images",
    "decode_tev_event_data",
    "decode_ultrasonic_phase_plot",
    "discover_ultratev_survey_dir",
    "find_latest_measurement_dir",
    "find_swg_feeder_survey_dir",
    "find_tx_survey_dir",
    "generate_all_substation_prpd_graphs",
    "generate_prpd_figure",
    "generate_prpd_graphs_for_swg_panel",
    "generate_prpd_graphs_for_transformer",
    "safe_path",
]

