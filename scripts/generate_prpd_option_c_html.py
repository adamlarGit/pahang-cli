r"""
========================================================================================
 ULTRA-TEV PLUS2 PRPD & MEASUREMENT TABLE COMPOSITE GRAPH GENERATOR (OPTION C)
========================================================================================

Description:
  Automates the headless rendering and screenshot generation of Option C composite
  graphs (Measurement Summary Table on the Left + PRPD Phase Plot on the Right)
  for Ultrasonic (US) and Transient Earth Voltage (TEV) survey data.

----------------------------------------------------------------------------------------
 INSTRUCTIONS FOR JUNIOR TECHNICIANS: HOW TO RUN THIS SCRIPT
----------------------------------------------------------------------------------------

1. Open PowerShell or Command Prompt.
2. Navigate to the project root directory:
     cd C:\Users\ADAM\Desktop\pahang-cli

3. Run the script using Python and provide the path to your raw measurement folder.
   (Always wrap paths containing spaces inside double quotes "")

----------------------------------------------------------------------------------------
 CLI USAGE EXAMPLES:
----------------------------------------------------------------------------------------

* EXAMPLE 1: Generate PRPD graphs for a SINGLE Switchgear Panel / Feeder
     python scripts/generate_prpd_option_c_html.py -s "C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\RAW MATERIAL\KUANTAN\02. SEPTEMBER\20-09-2026\316\RAW DATA\US+TEV\SWG\FEEDER_1"

* EXAMPLE 2: Generate PRPD graphs for an ENTIRE Substation Survey folder
     python scripts/generate_prpd_option_c_html.py -s "C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\RAW MATERIAL\KUANTAN\02. SEPTEMBER\20-09-2026\316\RAW DATA\US+TEV"

* EXAMPLE 3: Specify a CUSTOM Output Directory for generated PNGs
     python scripts/generate_prpd_option_c_html.py -s "C:\path\to\raw_data" -o "C:\path\to\output_folder"

* EXAMPLE 4: Positional Argument (without -s flag)
     python scripts/generate_prpd_option_c_html.py "C:\path\to\raw_data\SWG\FEEDER_1"

----------------------------------------------------------------------------------------
 OUTPUT LOCATION:
  - By default, all generated .png files are saved to:
      C:\Users\ADAM\Desktop\pahang-cli\docs\prpd_preview\option_c\
  - The script prints the FULL ABSOLUTE PATH of every generated PNG in the terminal.
========================================================================================
"""

import argparse
import json
import os
from pathlib import Path
import sys

# Ensure repository root is in sys.path when executed standalone
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.quick_report.prpd import (
    OPTION_C_INJECTION_TEMPLATE,
    SurveyHttpServer,
    discover_survey_measurements,
    find_chrome_executable,
    find_free_port,
    format_measurement_label,
    is_blank_or_invalid_image,
    render_prpd_option_c_image,
    safe_path,
)


def _sanitize_name(name: str) -> str:
    """Sanitize asset or sub-asset names into filesystem-safe uppercase tokens."""
    return re.sub(r"[^\w]+", "_", name.upper()).strip("_")


def find_survey_root(target_path: Path | str) -> Path:
    """Find the root survey directory by traversing upwards looking for survey_summary.js or resources."""
    cur = Path(target_path).resolve()
    while True:
        if (
            (cur / "survey_summary.js").exists()
            or (cur / "survey_metadata.js").exists()
            or (cur / "resources").exists()
        ):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(target_path).resolve()



def auto_discover_measurements(survey_dir: Path | str) -> list[tuple[str, str, str, str]]:
    """Dynamically discovers all Switchgear and Transformer TEV and Ultrasonic measurements
    using centralized canonical discovery engine from src.quick_report.prpd.

    Returns list of tuples: (label, relative_subpath, html_filename, tech_type)
    """
    target_path = Path(survey_dir).resolve()
    survey_root = find_survey_root(target_path)
    all_measurements = discover_survey_measurements(survey_root)

    items: list[tuple[str, str, str, str]] = []
    for m in all_measurements:
        if target_path != survey_root and not str(m.meas_dir).startswith(str(target_path)):
            continue
        items.append((m.label, m.data_rel_path, m.html_file, m.tech))

    return items


def generate_all_survey_prpd_option_c(survey_dir: Path | str, output_dir: Path | str) -> list[dict]:
    """Auto-discovers and generates Option C images for any given UltraTEV survey folder."""
    target_raw = str(Path(survey_dir).resolve())
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    items = auto_discover_measurements(target_raw)
    if not items:
        print(f"[ERROR] No measurements found in directory: {target_raw}")
        return []

    survey_root = find_survey_root(target_raw)
    survey_root_str = str(survey_root)

    print("================================================================================")
    print("OPTION C: AUTO-DISCOVERED PRPD + MEASUREMENT TABLE GENERATION")
    print(f"Target Path: {target_raw}")
    print(f"Survey Root: {survey_root_str}")
    print(f"Output Directory: {out_path}")
    print(f"Discovered Items: {len(items)}")
    print("================================================================================")

    browser_path = find_chrome_executable()
    results: list[dict] = []

    with SurveyHttpServer(survey_root, temp_dir=out_path) as port:
        for label, rel_subpath, html_name, tech in items:
            folder = Path(safe_path(survey_root / rel_subpath))
            html_file = folder / html_name
            out_png = (out_path / f"{label}.png").resolve()

            if not os.path.exists(safe_path(html_file)):
                print(f"[ERROR] HTML file not found: {html_file}")
                continue

            rendered = render_prpd_option_c_image(
                html_file=html_file,
                output_png=out_png,
                survey_root=survey_root,
                http_port=port,
                chrome_path=browser_path,
            )

            is_valid = rendered is not None and rendered.is_file() and not is_blank_or_invalid_image(rendered)
            out_size = os.path.getsize(safe_path(out_png)) if is_valid else 0
            print(f"[{tech:3s}] {label:20s} -> {'Saved' if is_valid else 'BLANK/INVALID'} ({out_size:,} bytes) to {out_png.name}")
            results.append({
                "label": label,
                "tech": tech,
                "output_file": str(out_png),
                "file_size": out_size,
                "status": "SUCCESS" if is_valid else "FAILED",
            })

    print("================================================================================")
    print(f"Successfully generated {len(results)} Option C images!")
    for res in results:
        print(f"  - [{res['tech']}] {res['output_file']}")
    print("================================================================================")
    return results


if __name__ == "__main__":
    epilog_text = """
----------------------------------------------------------------------------------------
JUNIOR TECHNICIAN QUICK START EXAMPLES:
----------------------------------------------------------------------------------------
1. Render graphs for a SINGLE Switchgear Feeder:
   python scripts/generate_prpd_option_c_html.py -s "C:\\Users\\ADAM\\Documents\\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\\RAW MATERIAL\\KUANTAN\\02. SEPTEMBER\\20-09-2026\\316\\RAW DATA\\US+TEV\\SWG\\FEEDER_1"

2. Render graphs for an ENTIRE Substation Survey:
   python scripts/generate_prpd_option_c_html.py -s "C:\\Users\\ADAM\\Documents\\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\\RAW MATERIAL\\KUANTAN\\02. SEPTEMBER\\20-09-2026\\316\\RAW DATA\\US+TEV"

3. Save output graphs directly to a specific folder:
   python scripts/generate_prpd_option_c_html.py -s "C:\\path\\to\\raw_folder" -o "C:\\path\\to\\my_output_dir"
"""

    parser = argparse.ArgumentParser(
        description="Option C PRPD + Measurement Table Composite Graph Generator",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "target_path",
        nargs="?",
        default=None,
        help="Path to raw UltraTEV survey folder or specific sub-panel folder (positional argument).",
    )
    parser.add_argument(
        "--survey-dir", "-s", "--input", "-i",
        dest="survey_dir",
        default=None,
        help="Path to raw UltraTEV survey folder or specific sub-panel folder (flag argument).",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=r"docs\prpd_preview\option_c",
        help="Destination directory for generated PNG images. (Default: docs\\prpd_preview\\option_c)",
    )

    args = parser.parse_args()
    selected_dir = args.target_path or args.survey_dir or r"C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\RAW MATERIAL\RAUB\02. SEPTEMBER\04-09-2026\228\RAW DATA\US+TEV\20260904T122744_228-SSU-GALI-TENGAH"
    generate_all_survey_prpd_option_c(selected_dir, args.output_dir)
