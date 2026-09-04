"""Standalone CLI utility for Option B PRPD Graph Generation.

Author: Antigravity Assistant
Purpose: Decode raw TEV and Ultrasonic event data from survey files and render
         publication-grade PRPD graphs matching UltraTEV's visual appearance.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
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


def _sanitize_name(name: str) -> str:
    """Sanitize asset or sub-asset names into filesystem-safe uppercase tokens."""
    return re.sub(r"[^\w]+", "_", name.upper()).strip("_")


def auto_discover_measurements(survey_dir: Path | str) -> list[tuple[str, Path, str]]:
    """Dynamically discover all Switchgear and Transformer TEV and Ultrasonic measurement data files.

    Primary approach parses survey_summary.js manifest.
    Fallback approach scans filesystem dynamically (SWG, VCB, RMU, TX, outdoor equipment).
    Returns list of tuples: (label, data_filepath, tech_type)
    """
    base_path = Path(safe_path(survey_dir))
    items: list[tuple[str, Path, str]] = []

    # 1. Primary approach: parse survey_summary.js manifest
    manifest_path = base_path / "survey_summary.js"
    if os.path.exists(safe_path(manifest_path)):
        try:
            with open(safe_path(manifest_path), "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()

            summary_data = None
            m = re.search(r"var\s+survey_summary\s*=\s*(\{[\s\S]*?\});?\s*$", content)
            if m:
                try:
                    summary_data = json.loads(m.group(1))
                except Exception:
                    pass

            if summary_data is None:
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end > start:
                    try:
                        summary_data = json.loads(content[start : end + 1])
                    except Exception:
                        pass

            if summary_data and isinstance(summary_data, dict):
                seen_labels: set[str] = set()
                for asset in summary_data.get("assets", []):
                    if not isinstance(asset, dict):
                        continue
                    asset_name = str(asset.get("$ASSET_NAME", "")).strip()
                    clean_asset = _sanitize_name(asset_name)
                    sub_assets = asset.get("$SUB_ASSETS", [])
                    if not isinstance(sub_assets, list):
                        continue
                    for sub in sub_assets:
                        if not isinstance(sub, dict):
                            continue
                        sub_name = str(sub.get("$SUB_ASSET_NAME", "")).strip()
                        clean_sub = _sanitize_name(sub_name)
                        measures = sub.get("$MEASURES", [])
                        if not isinstance(measures, list):
                            continue
                        for meas in measures:
                            if not isinstance(meas, dict):
                                continue
                            mtype = meas.get("$MEASURE_TYPE", "")
                            data_rel = meas.get("Data", "")
                            if not data_rel:
                                continue
                            rel_subpath = str(data_rel).replace("\\", "/").strip("/")
                            if mtype == "$TEV":
                                data_filename = "eventData.js"
                                tech = "TEV"
                            elif mtype == "$ULTRA":
                                data_filename = "ultrasonic_phase_plot.js"
                                tech = "US"
                            else:
                                continue

                            data_file = base_path / Path(rel_subpath) / data_filename
                            if os.path.exists(safe_path(data_file)):
                                base_label = f"{clean_asset}_{clean_sub}_{tech}" if clean_sub else f"{clean_asset}_{tech}"
                                base_label = base_label.replace(" ", "_")
                                label = base_label
                                if label in seen_labels:
                                    counter = 2
                                    while f"{base_label}_{counter}" in seen_labels:
                                        counter += 1
                                    label = f"{base_label}_{counter}"
                                seen_labels.add(label)
                                items.append((label, data_file, tech))
        except Exception:
            items = []

    if items:
        return items

    # 2. Fallback approach: dynamic directory traversal
    seen_labels = set()
    eq_prefixes = ("SWG", "VCB", "RMU", "TX", "TRANSFORMER", "H_POLE", "H-POLE", "LIGHTNING", "DROPOUT")
    try:
        candidate_eq_dirs = [
            d for d in base_path.iterdir()
            if d.is_dir() and (d.name.upper().startswith(eq_prefixes) or "TRANSFORMER" in d.name.upper())
        ]
    except OSError:
        return items

    for eq_dir in sorted(candidate_eq_dirs, key=lambda p: p.name):
        eq_name = _sanitize_name(eq_dir.name)

        try:
            children = [c for c in eq_dir.iterdir() if c.is_dir()]
        except OSError:
            continue

        for child in sorted(children, key=lambda p: p.name):
            tev_data = child / "eventData.js"
            us_data = child / "ultrasonic_phase_plot.js"
            if os.path.exists(safe_path(tev_data)):
                base_label = f"{eq_name}_TEV"
                label = base_label
                if label in seen_labels:
                    c = 2
                    while f"{base_label}_{c}" in seen_labels:
                        c += 1
                    label = f"{base_label}_{c}"
                seen_labels.add(label)
                items.append((label, tev_data, "TEV"))
                continue
            if os.path.exists(safe_path(us_data)):
                base_label = f"{eq_name}_US"
                label = base_label
                if label in seen_labels:
                    c = 2
                    while f"{base_label}_{c}" in seen_labels:
                        c += 1
                    label = f"{base_label}_{c}"
                seen_labels.add(label)
                items.append((label, us_data, "US"))
                continue

            sub_name = _sanitize_name(child.name)
            try:
                meas_dirs = [m for m in child.iterdir() if m.is_dir()]
            except OSError:
                continue

            for meas in sorted(meas_dirs, key=lambda p: p.name):
                tev_data = meas / "eventData.js"
                us_data = meas / "ultrasonic_phase_plot.js"
                if os.path.exists(safe_path(tev_data)):
                    base_label = f"{eq_name}_{sub_name}_TEV"
                    label = base_label
                    if label in seen_labels:
                        c = 2
                        while f"{base_label}_{c}" in seen_labels:
                            c += 1
                        label = f"{base_label}_{c}"
                    seen_labels.add(label)
                    items.append((label, tev_data, "TEV"))
                elif os.path.exists(safe_path(us_data)):
                    base_label = f"{eq_name}_{sub_name}_US"
                    label = base_label
                    if label in seen_labels:
                        c = 2
                        while f"{base_label}_{c}" in seen_labels:
                            c += 1
                        label = f"{base_label}_{c}"
                    seen_labels.add(label)
                    items.append((label, us_data, "US"))

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
