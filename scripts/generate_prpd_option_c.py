"""
Option C: Composite Measurement Info Table + Native PRPD Graph Generation
Author: Antigravity Assistant
Purpose: Decode raw TEV (FlatBuffers / gzip base64) and Ultrasonic (JSON array) event data
         and metadata from survey files, and render publication-grade composite figures
         featuring a styled Measurement Information Table on the left and a 4-tier
         repetition density PRPD Scatter Plot on the right.
"""

import base64
import gzip
import json
import os
from pathlib import Path
import re
import struct
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
import numpy as np

# Ensure Windows UTF-8 stdout encoding
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def safe_path(p: Path | str) -> str:
    """Ensure Windows long path compatibility."""
    s = str(Path(p).resolve())
    if os.name == 'nt' and not s.startswith('\\\\?\\'):
        return '\\\\?\\' + s
    return s


def decode_tev_event_data(filepath: Path | str) -> list[dict]:
    """
    Decodes gzipped base64 FlatBuffers eventData.js (file identifier 'UE01').
    Returns a list of event dictionaries:
    [{'peak': float, 'integral': int, 'phase': int, 'cycle': int, 'risetime': int, 'width': int, 'amplitude': float}]
    """
    with open(safe_path(filepath), 'r', encoding='utf-8') as f:
        text = f.read()

    m = re.search(r'var\s+eventData\s*=\s*"([^"]+)"', text)
    if not m:
        raise ValueError(f"Could not extract eventData string from {filepath}")

    b64_str = m.group(1)
    raw_bytes = gzip.decompress(base64.b64decode(b64_str))

    # Parse FlatBuffers EventVec
    root_offset = struct.unpack_from("<I", raw_bytes, 0)[0]
    soffset = struct.unpack_from("<i", raw_bytes, root_offset)[0]
    vtable_offset = root_offset - soffset

    # field 0 (events vector) offset in table is at vtable_offset + 4
    field0_offset_in_table = struct.unpack_from("<H", raw_bytes, vtable_offset + 4)[0]
    if field0_offset_in_table == 0:
        return []

    vector_loc = root_offset + field0_offset_in_table
    vector_offset_rel = struct.unpack_from("<I", raw_bytes, vector_loc)[0]
    vector_pos = vector_loc + vector_offset_rel
    vector_len = struct.unpack_from("<I", raw_bytes, vector_pos)[0]

    events = []
    # Each SingleEvent struct is 24 bytes:
    # float32 peak (0..4), int32 integral (4..8), uint16 phase (8..10), uint16 cycle (10..12),
    # uint16 rise (12..14), uint16 width (14..16), float32 tf_t (16..20), float32 tf_f (20..24)
    for i in range(vector_len):
        elem_pos = vector_pos + 4 + i * 24
        peak, integral, phase, cycle, risetime, width, tf_t, tf_f = struct.unpack_from(
            "<fiHHHHff", raw_bytes, elem_pos
        )
        events.append({
            'peak': float(peak),
            'integral': int(integral),
            'phase': int(phase),
            'cycle': int(cycle),
            'risetime': int(risetime),
            'width': int(width),
            'tf_t': float(tf_t),
            'tf_f': float(tf_f),
            'amplitude': float(peak)  # TEV uses raw peak amplitude (dB)
        })

    return events


def decode_ultrasonic_phase_plot(filepath: Path | str) -> list[dict]:
    """
    Decodes ultrasonic_phase_plot.js containing var ultra_events = {"data": [[peak, phase, cycle], ...]}.
    Returns a list of event dictionaries:
    [{'peak': float, 'phase': int, 'cycle': int, 'amplitude': float}]
    """
    with open(safe_path(filepath), 'r', encoding='utf-8') as f:
        text = f.read()

    m = re.search(r'var\s+ultra_events\s*=\s*(\{.*?\});', text, re.DOTALL)
    if not m:
        m = re.search(r'var\s+ultra_events\s*=\s*(\{.*\})', text, re.DOTALL)
    if not m:
        raise ValueError(f"Could not extract ultra_events from {filepath}")

    raw_json = m.group(1)
    data_dict = json.loads(raw_json)
    raw_events = data_dict.get('data', [])

    events = []
    for elem in raw_events:
        peak = float(elem[0])
        phase = int(elem[1])
        cycle = int(elem[2])
        # Ultrasonic amplitude rounding to nearest 1/3 of a dB (matches UltraTEV UTP2Events)
        rounded_amp = round(peak * 3.0) / 3.0
        events.append({
            'peak': peak,
            'phase': phase,
            'cycle': cycle,
            'amplitude': rounded_amp
        })

    return events


def parse_measurement_metadata(meta_path: Path | str, tech_type: str = "TEV") -> list[tuple[str, str]]:
    """
    Parses measurement_metadata.js and returns an ordered list of (Label, Value) tuples for the table.
    """
    with open(safe_path(meta_path), 'r', encoding='utf-8') as f:
        text = f.read().strip()

    idx = text.find('{')
    last_idx = text.rfind('}')
    if idx == -1 or last_idx == -1:
        raise ValueError(f"Invalid measurement_metadata.js content in {meta_path}")

    json_str = text[idx:last_idx + 1]
    data = json.loads(json_str)

    fields_dict = {}
    for g in data.get('measurement_fields', []):
        for f in g.get('fields', []):
            fields_dict[f.get('fieldname')] = f.get('data')

    trend = data.get('Trend', [{}])[0] if data.get('Trend') else {}

    TRANSLATIONS = {
        "$TRUE": "True",
        "$FALSE": "False",
        "$ULTRA_INT": "Internal Microphone",
        "$ULTRA_CONT": "Contact Probe",
        "$ULTRA_CONTACT": "Contact Probe",
        "$ULTRA_DISH": "UltraDish",
        "$ULTRA_FLEX": "Flexible Microphone",
        "$ULTRA_BOLT": "UltraBolt",
        "$ULTRA_NOISE": "Noise",
        "$ULTRA_PD": "PD",
        "$TEV_NOISE": "Noise",
        "$TEV_PD": "PD",
        "$TEVINT_NO_CONCERN": "No Concern",
        "$TEVINT_NO_CONCERN_LOW_PPC": "No Concern - low pulses per cycle",
        "$TEVINT_LOWLEVEL_PD": "Possible low level internal partial discharge - no immediate concern",
        "$TEVINT_POSS_MED_INT_PD": "Possible medium level internal partial discharge",
        "$TEVINT_LIKE_MED_INT_PD": "Likely medium level internal partial discharge",
        "$TEVINT_POSS_HIGH_INT_PD": "Possible high level internal partial discharge",
        "$TEVINT_LIKE_HIGH_INT_PD": "Likely high level internal partial discharge",
        "$TEVINT_SURF_DISCHARGE": "Possible surface discharge - check ultrasonics",
        "$TEVINT_FLOAT_METAL": "Likely floating metalwork or poor connections",
        "$TEVINT_HIGHPPC_NOISE": "High pulses per cycle - noise likely",
        "$TEVINT_BACKGROUND_NOISE": "High noise level: measurement invalid",
        "$PHASE_REF_MANUAL": "Manual",
        "$PHASE_REF_EFIELD": "E-Field",
        "$PHASE_REF_HFIELD": "H-Field",
        "$PHASE_REF_PHOTO": "Photo",
        "$PHASE_REF_SMARTIO": "SmartIO",
        "$PHASE_REF_WIRELESS": "Wireless Phase Reference",
    }

    def trans(val):
        if val is None:
            return ""
        val_str = str(val)
        return TRANSLATIONS.get(val_str, val_str)

    table_rows: list[tuple[str, str]] = []

    if tech_type.upper() == "TEV":
        # 1. Measurement (dB)
        db_val = fields_dict.get("$MEASURE_DB", trend.get("$MEASURE_DB", 0))
        table_rows.append(("Measurement (dB)", f"{float(db_val):.0f}"))

        # 2. Measurement (PPC)
        ppc_val = trend.get("$MEASURE_PPC", fields_dict.get("$MEASURE_PPC", 0))
        table_rows.append(("Measurement (PPC)", f"{float(ppc_val):.2f}"))

        # 3. Noise Level (dB)
        noise_val = fields_dict.get("$NOISE_LEVEL", 0)
        table_rows.append(("Noise Level (dB)", f"{float(noise_val):.0f}"))

        # 4. TEV Interpretation
        interp = fields_dict.get("$TEV_INTERPRET", "")
        table_rows.append(("TEV Interpretation", trans(interp)))

        # 5. TEV Classification
        cls_val = fields_dict.get("$TEV_CLASS", "")
        table_rows.append(("TEV Classification", trans(cls_val)))

        # 6. TEV Classification PD (%)
        cls_pd = fields_dict.get("$TEV_CLASS_PD_PERCENT", 0)
        table_rows.append(("TEV Classification PD (%)", f"{cls_pd}"))

        # 7. Phase Reference Locked
        lock = fields_dict.get("$PHASE_REF_LOCK", "")
        table_rows.append(("Phase Reference Locked", trans(lock)))

        # 8. Phase Reference Source
        src = fields_dict.get("$PHASE_REF_TYPE", "")
        table_rows.append(("Phase Reference Source", trans(src)))

        # 9. Phase Reference Strength (%)
        strength = fields_dict.get("$PHASE_REF_STRENGTH", 0)
        table_rows.append(("Phase Reference Strength (%)", f"{strength}"))

    else:
        # Ultrasonic
        # 1. Measurement (dBμV)
        dbuv_val = fields_dict.get("$MEASURE_DBUV", trend.get("$MEASURE_DBUV", 0))
        table_rows.append(("Measurement (dB\u03bcV)", f"{float(dbuv_val):.0f}"))

        # 2. Ultrasonic Accessory
        acc = fields_dict.get("$ULTRA_ACC", "")
        table_rows.append(("Ultrasonic Accessory", trans(acc)))

        # 3. Ultrasonic Classification
        cls_val = fields_dict.get("$ULTRA_CLASS", trend.get("$ULTRA_CLASS", ""))
        table_rows.append(("Ultrasonic Classification", trans(cls_val)))

        # 4. Classification Certainty (%)
        cert = fields_dict.get("$ULTRA_CLASS_PERCENT", 0)
        table_rows.append(("Classification Certainty (%)", f"{cert}"))

        # 5. Phase Reference Locked
        lock = fields_dict.get("$PHASE_REF_LOCK", "")
        table_rows.append(("Phase Reference Locked", trans(lock)))

        # 6. Phase Reference Source
        src = fields_dict.get("$PHASE_REF_TYPE", "")
        table_rows.append(("Phase Reference Source", trans(src)))

        # 7. Phase Reference Strength (%)
        strength = fields_dict.get("$PHASE_REF_STRENGTH", 0)
        table_rows.append(("Phase Reference Strength (%)", f"{strength}"))

    return table_rows


def render_measurement_table(
    ax: plt.Axes,
    table_rows: list[tuple[str, str]],
    header_title: str = "Measurement"
) -> None:
    """
    Renders a styled card-like Measurement table onto a Matplotlib Axes.
    """
    ax.axis('off')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    num_rows = len(table_rows)
    x_left = 0.02
    x_right = 0.98
    width = x_right - x_left
    split_x = x_left + width * 0.58

    # Layout geometry
    h_header = 0.095
    h_row = min(0.09, (0.92 - h_header) / max(num_rows, 8))
    total_table_height = h_header + num_rows * h_row
    y_start = 0.04 + (0.92 - total_table_height) / 2.0

    # Color palette
    header_bg = '#F2F4F7'
    header_text_color = '#1E293B'
    row_alt_bg = '#F8FAFC'
    row_white_bg = '#FFFFFF'
    border_color = '#D1D5DB'
    label_color = '#374151'
    val_color = '#111827'

    # Draw Header Box
    y_header_bottom = y_start + num_rows * h_row
    rect_header = Rectangle(
        (x_left, y_header_bottom),
        width,
        h_header,
        facecolor=header_bg,
        edgecolor=border_color,
        linewidth=0.9,
        zorder=2
    )
    ax.add_patch(rect_header)
    ax.text(
        x_left + 0.035 * width,
        y_header_bottom + h_header / 2.0,
        header_title,
        ha='left',
        va='center',
        fontsize=9.2,
        fontweight='bold',
        color=header_text_color,
        zorder=3
    )

    # Draw Data Rows (from top to bottom)
    for idx, (label, val) in enumerate(table_rows):
        y_row_bottom = y_header_bottom - (idx + 1) * h_row
        bg_color = row_alt_bg if idx % 2 == 1 else row_white_bg

        # Row box
        rect_row = Rectangle(
            (x_left, y_row_bottom),
            width,
            h_row,
            facecolor=bg_color,
            edgecolor=border_color,
            linewidth=0.8,
            zorder=2
        )
        ax.add_patch(rect_row)

        # Vertical divider
        ax.plot(
            [split_x, split_x],
            [y_row_bottom, y_row_bottom + h_row],
            color=border_color,
            linewidth=0.8,
            zorder=3
        )

        # Label Text (Left Aligned)
        ax.text(
            x_left + 0.035 * width,
            y_row_bottom + h_row / 2.0,
            label,
            ha='left',
            va='center',
            fontsize=8.3,
            fontweight='normal',
            color=label_color,
            zorder=4
        )

        # Value Text (Right Aligned)
        is_first = (idx == 0)
        ax.text(
            x_right - 0.035 * width,
            y_row_bottom + h_row / 2.0,
            str(val),
            ha='right',
            va='center',
            fontsize=8.5 if is_first else 8.3,
            fontweight='bold' if is_first else 'normal',
            color=val_color,
            zorder=4
        )


def generate_composite_prpd_figure(
    events: list[dict],
    table_rows: list[tuple[str, str]],
    tech_type: str = "TEV",
    output_path: Path | str | None = None,
    show_sine: bool = False
) -> None:
    """
    Renders Option C: Side-by-side Measurement Info Table and Option B PRPD Scatter Graph.
    
    Parameters:
        events: Decoded event list with 'phase' and 'amplitude'
        table_rows: Ordered (label, value) pairs for the Measurement Table
        tech_type: "TEV" (0 to 60 dB) or "US" (-10 to 71 dBuV)
        output_path: Filepath where PNG image will be saved
        show_sine: Whether to draw the reference line-frequency sine wave
    """
    is_tev = (tech_type.upper() == "TEV")
    if is_tev:
        ymin, ymax = 0.0, 60.0
        ylabel = "dB"
    else:
        ymin, ymax = -10.0, 71.0
        ylabel = "dBuV"

    # Count repetitions per discrete (phase, amplitude) coordinate
    point_counts = {}
    for e in events:
        phase = e['phase'] % 360
        amp = e['amplitude']
        key = (phase, amp)
        point_counts[key] = point_counts.get(key, 0) + 1

    max_count = max(point_counts.values()) if point_counts else 1

    # Bin thresholds matching UltraTEV prpd.js
    COUNT_THRESH_FRAC = [0.1, 0.45, 0.8]
    thresh = [
        max_count * COUNT_THRESH_FRAC[0],
        max_count * COUNT_THRESH_FRAC[1],
        max_count * COUNT_THRESH_FRAC[2]
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

    # Matplotlib Figure Initialization with 2 subplots side-by-side
    fig, (ax_table, ax_prpd) = plt.subplots(
        1, 2,
        figsize=(12, 4.2),
        dpi=200,
        gridspec_kw={'width_ratios': [1.18, 1.82], 'wspace': 0.16}
    )
    fig.patch.set_facecolor('white')

    # ----------------------------------------------------
    # Left Subplot: Styled Measurement Information Table
    # ----------------------------------------------------
    render_measurement_table(ax_table, table_rows, header_title="Measurement")

    # ----------------------------------------------------
    # Right Subplot: PRPD Scatter Plot (Option B style)
    # ----------------------------------------------------
    ax_prpd.set_facecolor('white')
    ax_prpd.grid(True, which='both', color='#E2E2E2', linestyle='-', linewidth=0.8, zorder=1)

    # Reference Unipolar Sine Wave (if enabled)
    if show_sine:
        deg = np.linspace(0, 360, 361)
        sine_val = np.abs(np.sin(np.radians(deg)))
        sine_y = ymin + (ymax - ymin) * sine_val
        ax_prpd.plot(deg, sine_y, color='#555555', linewidth=1.1, linestyle='-', zorder=2, label='_nolegend_')

    # Draw Scatter Series (Order: Green -> Blue -> Red -> Dark Red for correct layering)
    dot_size = 12.0
    if bin1_x:
        ax_prpd.scatter(bin1_x, bin1_y, c='#00FF00', s=dot_size, marker='o', edgecolors='none', zorder=3)
    if bin2_x:
        ax_prpd.scatter(bin2_x, bin2_y, c='#0000FF', s=dot_size, marker='o', edgecolors='none', zorder=4)
    if bin3_x:
        ax_prpd.scatter(bin3_x, bin3_y, c='#FF0000', s=dot_size, marker='o', edgecolors='none', zorder=5)
    if bin4_x:
        ax_prpd.scatter(bin4_x, bin4_y, c='#640000', s=dot_size, marker='o', edgecolors='none', zorder=6)

    # Axis Ranges and Ticks
    ax_prpd.set_xlim(0, 360)
    ax_prpd.set_xticks([0, 90, 180, 270, 360])
    ax_prpd.set_ylim(ymin, ymax)

    if is_tev:
        ax_prpd.set_yticks(np.arange(0, 61, 10))
    else:
        ax_prpd.set_yticks(np.arange(-10, 72, 10))

    # Axis Labels
    ax_prpd.set_xlabel("Degrees", fontsize=9.5, fontweight='normal', color='#000000')
    ax_prpd.set_ylabel(ylabel, fontsize=9.5, fontweight='normal', color='#000000')

    # Spine Borders
    for spine in ax_prpd.spines.values():
        spine.set_color('#000000')
        spine.set_linewidth(1.0)

    # Tick Parameters
    ax_prpd.tick_params(axis='both', colors='#000000', labelsize=8.5, length=4, width=0.8)

    # Custom Legend
    patch_green = mpatches.Patch(color='#00FF00', label=f"< {t0}")
    patch_blue = mpatches.Patch(color='#0000FF', label=f"{t0} < {t1}")
    patch_red = mpatches.Patch(color='#FF0000', label=f"{t1} < {t2}")
    patch_darkred = mpatches.Patch(color='#640000', label=f"{t2} < {t_max}")

    leg = ax_prpd.legend(
        handles=[patch_green, patch_blue, patch_red, patch_darkred],
        loc='upper left',
        frameon=True,
        framealpha=0.95,
        facecolor='white',
        edgecolor='#D0D0D0',
        fontsize=8.0,
        handlelength=1.0,
        handleheight=0.8,
        handletextpad=0.5,
        borderpad=0.5,
        labelspacing=0.3
    )
    leg.get_frame().set_linewidth(0.8)

    plt.subplots_adjust(left=0.03, right=0.97, top=0.94, bottom=0.12)

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(safe_path(out_p), dpi=200, facecolor='white', edgecolor='none')
        plt.close(fig)
    else:
        plt.close(fig)


def generate_all_survey_prpd_option_c(survey_dir: Path | str, output_dir: Path | str) -> list[dict]:
    """
    Finds and processes all 7 TEV and Ultrasonic measurements from survey folder and writes Option C PNGs.
    """
    survey_path = Path(survey_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        ("SWG_FEEDER_1_TEV", "SWG/FEEDER_1", "TEV", "eventData.js"),
        ("SWG_FEEDER_1_US", "SWG/FEEDER_1", "Ultrasonic", "ultrasonic_phase_plot.js"),
        ("SWG_FEEDER_2_TEV", "SWG/FEEDER_2", "TEV", "eventData.js"),
        ("SWG_FEEDER_2_US", "SWG/FEEDER_2", "Ultrasonic", "ultrasonic_phase_plot.js"),
        ("SWG_FEEDER_3_TEV", "SWG/FEEDER_3", "TEV", "eventData.js"),
        ("SWG_FEEDER_3_US", "SWG/FEEDER_3", "Ultrasonic", "ultrasonic_phase_plot.js"),
        ("TX_TRANSFORMER_US", "TX/Transformer", "Ultrasonic", "ultrasonic_phase_plot.js"),
    ]

    results = []

    print("================================================================================")
    print("OPTION C: COMPOSITE MEASUREMENT INFO TABLE + PRPD GRAPH GENERATION")
    print(f"Source Survey: {survey_dir}")
    print(f"Output Directory: {output_dir}")
    print("================================================================================")

    for label, subpath, tech_keyword, filename in targets:
        folder = Path(safe_path(survey_path / subpath))
        if not folder.exists():
            print(f"[ERROR] Directory not found: {folder}")
            continue

        matches = [d for d in folder.iterdir() if d.is_dir() and tech_keyword in d.name]
        if not matches:
            print(f"[ERROR] No measurement directory matching '{tech_keyword}' in {folder}")
            continue

        meas_dir = matches[0]
        data_file = meas_dir / filename
        meta_file = meas_dir / "measurement_metadata.js"
        out_png = out_dir / f"{label}.png"

        if not os.path.exists(safe_path(data_file)):
            print(f"[ERROR] Data file not found: {data_file}")
            continue
        if not os.path.exists(safe_path(meta_file)):
            print(f"[ERROR] Metadata file not found: {meta_file}")
            continue

        # Decode data & metadata
        if tech_keyword == "TEV":
            events = decode_tev_event_data(data_file)
            tech_type = "TEV"
        else:
            events = decode_ultrasonic_phase_plot(data_file)
            tech_type = "US"

        table_rows = parse_measurement_metadata(meta_file, tech_type=tech_type)

        # Generate composite plot
        generate_composite_prpd_figure(
            events=events,
            table_rows=table_rows,
            tech_type=tech_type,
            output_path=out_png,
            show_sine=False
        )

        out_size = os.path.getsize(safe_path(out_png)) if os.path.exists(safe_path(out_png)) else 0
        print(f"[{tech_type:3s}] {label}.png -> {len(events):5d} events, {len(table_rows)} meta rows -> Saved ({out_size:,} bytes)")

        results.append({
            "label": label,
            "tech": tech_type,
            "events_count": len(events),
            "table_rows": len(table_rows),
            "output_file": str(out_png),
            "file_size": out_size,
            "status": "SUCCESS" if out_size > 0 else "FAILED"
        })

    print("================================================================================")
    print(f"All {len(results)} Option C composite PRPD graphs generated successfully!")
    print("================================================================================")
    return results


if __name__ == "__main__":
    survey_dir = r"C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\RAW MATERIAL\RAUB\02. SEPTEMBER\02-09-2026\199\RAW DATA\US+TEV\20260902T103527_199-LEMBAH-KLAU-BARU"
    output_dir = r"C:\Users\ADAM\Desktop\pahang-cli\docs\prpd_preview\option_c\test"

    generate_all_survey_prpd_option_c(survey_dir, output_dir)
