"""Standalone CLI utility for Option B PRPD Graph Generation.

Author: Antigravity Assistant
Purpose: Decode raw TEV and Ultrasonic event data from survey files and render
         publication-grade PRPD graphs matching UltraTEV's visual appearance.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.quick_report.prpd import (
    decode_tev_event_data,
    decode_ultrasonic_phase_plot,
    generate_prpd_figure,
    safe_path,
)


def auto_discover_measurements(survey_dir: Path | str) -> list[tuple[str, Path, str]]:
    """Dynamically discover all Switchgear and Transformer TEV and Ultrasonic measurement data files.

    Returns list of tuples: (label, data_filepath, tech_type)
    """
    base_path = Path(safe_path(survey_dir))
    items: list[tuple[str, Path, str]] = []

    # 1. Scan SWG directory (FEEDER_1, FEEDER_2, ..., FEEDER_N)
    swg_dir = base_path / "SWG"
    if swg_dir.exists() and swg_dir.is_dir():
        for feeder_folder in sorted(swg_dir.iterdir(), key=lambda p: p.name):
            if not feeder_folder.is_dir():
                continue
            feeder_name = feeder_folder.name.upper()

            # Find TEV measurement subfolder
            for meas in feeder_folder.iterdir():
                if meas.is_dir() and meas.name.endswith("_TEV"):
                    data_file = meas / "eventData.js"
                    if os.path.exists(safe_path(data_file)):
                        label = f"SWG_{feeder_name}_TEV"
                        items.append((label, data_file, "TEV"))

            # Find Ultrasonic measurement subfolder
            for meas in feeder_folder.iterdir():
                if meas.is_dir() and meas.name.endswith("_Ultrasonic"):
                    data_file = meas / "ultrasonic_phase_plot.js"
                    if os.path.exists(safe_path(data_file)):
                        label = f"SWG_{feeder_name}_US"
                        items.append((label, data_file, "US"))

    # 2. Scan TX directory (Transformer, TX1, TX2, etc.)
    tx_dir = base_path / "TX"
    if tx_dir.exists() and tx_dir.is_dir():
        for tx_folder in sorted(tx_dir.iterdir(), key=lambda p: p.name):
            if not tx_folder.is_dir():
                continue
            tx_name = tx_folder.name.upper()

            # Find Ultrasonic measurement subfolder
            for meas in tx_folder.iterdir():
                if meas.is_dir() and meas.name.endswith("_Ultrasonic"):
                    data_file = meas / "ultrasonic_phase_plot.js"
                    if os.path.exists(safe_path(data_file)):
                        label = f"TX_{tx_name}_US"
                        items.append((label, data_file, "US"))

            # Find TEV measurement subfolder if any on TX
            for meas in tx_folder.iterdir():
                if meas.is_dir() and meas.name.endswith("_TEV"):
                    data_file = meas / "eventData.js"
                    if os.path.exists(safe_path(data_file)):
                        label = f"TX_{tx_name}_TEV"
                        items.append((label, data_file, "TEV"))

    return items


def generate_all_survey_prpd(survey_dir: Path | str, output_dir: Path | str) -> list[dict]:
    """Find and process all TEV and Ultrasonic measurements from a survey folder and write PNGs."""
    survey_path = Path(survey_dir).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    items = auto_discover_measurements(survey_path)
    if not items:
        print(f"[ERROR] No measurements found in survey directory: {survey_path}")
        return []

    results = []

    print("=" * 80)
    print("OPTION B: MEASUREMENT DATA DECODING & NATIVE PRPD GENERATION")
    print(f"Source Survey: {survey_path}")
    print(f"Output Directory: {out_dir}")
    print(f"Discovered Items: {len(items)}")
    print("=" * 80)

    for label, data_file, tech_type in items:
        out_png = out_dir / f"{label}.png"

        # Decode data
        if tech_type == "TEV":
            events = decode_tev_event_data(data_file)
        else:
            events = decode_ultrasonic_phase_plot(data_file)

        # Generate plot
        generate_prpd_figure(
            events=events,
            tech_type=tech_type,
            output_path=out_png,
            show_sine=False,
        )

        out_size = os.path.getsize(safe_path(out_png)) if os.path.exists(safe_path(out_png)) else 0
        print(f"[{tech_type:3s}] {label:20s} -> {len(events):5d} events -> Saved ({out_size:,} bytes) to {out_png.name}")

        results.append({
            "label": label,
            "tech": tech_type,
            "events_count": len(events),
            "output_file": str(out_png),
            "file_size": out_size,
            "status": "SUCCESS" if out_size > 0 else "FAILED",
        })

    print("=" * 80)
    print(f"All {len(results)} PRPD graphs generated successfully.")
    print("=" * 80)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Option B PRPD native scatter graphs.")
    parser.add_argument(
        "--survey-dir",
        "-s",
        default=r"C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\RAW MATERIAL\KUANTAN\01. AUGUST\25-08-2026\149. TAMAN BUKIT BEIRUT PERMAI (IR+VI)\RAW DATA\US+TEV\20260825T103351_149-TAMAN-BUKIT-BEIRUT-PERMAI",
        help="Path to raw UltraTEV survey directory.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="docs/prpd_preview/option_b",
        help="Destination directory for output PNG files.",
    )
    args = parser.parse_args()
    generate_all_survey_prpd(args.survey_dir, args.output_dir)
