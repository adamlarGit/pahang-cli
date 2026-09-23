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
import http.server
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import threading
import time
import urllib.parse

from src.quick_report.prpd import (
    OPTION_C_INJECTION_TEMPLATE,
    ThreadedTCPServer,
    find_chrome_executable,
    find_free_port,
    is_blank_or_invalid_image,
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
    """Dynamically discovers all Switchgear and Transformer TEV and Ultrasonic measurements.

    Primary approach parses survey_summary.js manifest.
    Fallback approach scans filesystem dynamically (SWG, VCB, RMU, TX, outdoor equipment).
    Returns list of tuples: (label, relative_subpath, html_filename, tech_type)
    """
    target_path = Path(survey_dir).resolve()
    survey_root = find_survey_root(target_path)
    base_path = survey_root
    items: list[tuple[str, str, str, str]] = []

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
                                html_name = "TEV.html"
                                tech = "TEV"
                            elif mtype == "$ULTRA":
                                html_name = "Ultrasonic.html"
                                tech = "US"
                            else:
                                continue

                            target_html = base_path / Path(rel_subpath) / html_name
                            if os.path.exists(safe_path(target_html)):
                                full_meas_path = (survey_root / Path(rel_subpath)).resolve()
                                # Filter if user specified a sub-directory
                                if target_path != survey_root and not str(full_meas_path).startswith(str(target_path)):
                                    continue

                                base_label = f"{clean_asset}_{clean_sub}_{tech}" if clean_sub else f"{clean_asset}_{tech}"
                                base_label = base_label.replace(" ", "_")
                                label = base_label
                                if label in seen_labels:
                                    counter = 2
                                    while f"{base_label}_{counter}" in seen_labels:
                                        counter += 1
                                    label = f"{base_label}_{counter}"
                                pair = (label, rel_subpath, html_name, tech)
                                seen_labels.add(label)
                                items.append(pair)
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
        candidate_eq_dirs = []

    # If target_path is inside base_path, also check target_path directly
    scan_roots = candidate_eq_dirs if candidate_eq_dirs else ([target_path] if target_path.is_dir() else [])

    for eq_dir in sorted(scan_roots, key=lambda p: p.name):
        eq_name = _sanitize_name(eq_dir.name)

        try:
            children = [c for c in eq_dir.iterdir() if c.is_dir()]
        except OSError:
            continue

        for child in sorted(children, key=lambda p: p.name):
            tev_html = child / "TEV.html"
            us_html = child / "Ultrasonic.html"
            if os.path.exists(safe_path(tev_html)):
                rel_path = child.relative_to(survey_root).as_posix()
                if target_path != survey_root and not str(child.resolve()).startswith(str(target_path)):
                    continue
                base_label = f"{eq_name}_TEV"
                label = base_label
                if label in seen_labels:
                    c = 2
                    while f"{base_label}_{c}" in seen_labels:
                        c += 1
                    label = f"{base_label}_{c}"
                seen_labels.add(label)
                items.append((label, rel_path, "TEV.html", "TEV"))
                continue
            if os.path.exists(safe_path(us_html)):
                rel_path = child.relative_to(survey_root).as_posix()
                if target_path != survey_root and not str(child.resolve()).startswith(str(target_path)):
                    continue
                base_label = f"{eq_name}_US"
                label = base_label
                if label in seen_labels:
                    c = 2
                    while f"{base_label}_{c}" in seen_labels:
                        c += 1
                    label = f"{base_label}_{c}"
                seen_labels.add(label)
                items.append((label, rel_path, "Ultrasonic.html", "US"))
                continue

            sub_name = _sanitize_name(child.name)
            try:
                meas_dirs = [m for m in child.iterdir() if m.is_dir()]
            except OSError:
                continue

            for meas in sorted(meas_dirs, key=lambda p: p.name):
                tev_html = meas / "TEV.html"
                us_html = meas / "Ultrasonic.html"
                if os.path.exists(safe_path(tev_html)):
                    rel_path = meas.relative_to(survey_root).as_posix()
                    if target_path != survey_root and not str(meas.resolve()).startswith(str(target_path)):
                        continue
                    base_label = f"{eq_name}_{sub_name}_TEV"
                    label = base_label
                    if label in seen_labels:
                        c = 2
                        while f"{base_label}_{c}" in seen_labels:
                            c += 1
                        label = f"{base_label}_{c}"
                    seen_labels.add(label)
                    items.append((label, rel_path, "TEV.html", "TEV"))
                elif os.path.exists(safe_path(us_html)):
                    rel_path = meas.relative_to(survey_root).as_posix()
                    if target_path != survey_root and not str(meas.resolve()).startswith(str(target_path)):
                        continue
                    base_label = f"{eq_name}_{sub_name}_US"
                    label = base_label
                    if label in seen_labels:
                        c = 2
                        while f"{base_label}_{c}" in seen_labels:
                            c += 1
                        label = f"{base_label}_{c}"
                    seen_labels.add(label)
                    items.append((label, rel_path, "Ultrasonic.html", "US"))

    return items



# Reused from src.quick_report.prpd
INJECTION_TEMPLATE = OPTION_C_INJECTION_TEMPLATE



def generate_all_survey_prpd_option_c(survey_dir: Path | str, output_dir: Path | str) -> list[dict]:
    """
    Auto-discovers and generates Option C images for any given UltraTEV survey folder.
    """
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

    # Dynamic HTTP Server
    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            path = path.split("?", 1)[0].split("#", 1)[0]
            trailing_slash = path.rstrip().endswith("/")
            try:
                path = urllib.parse.unquote(path, errors="surrogatepass")
            except UnicodeDecodeError:
                path = urllib.parse.unquote(path)
            path = posixpath.normpath(path)
            words = filter(None, path.split("/"))
            full_path = safe_path(survey_root_str)
            for word in words:
                full_path = os.path.join(full_path, word)
            if trailing_slash:
                full_path += "/"
            return full_path

        def log_message(self, format, *args):
            pass  # Suppress HTTP access logging for clean CLI output

    port = find_free_port()
    httpd = ThreadedTCPServer(("127.0.0.1", port), CustomHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    browser_path = find_chrome_executable()
    results = []

    try:
        for label, rel_subpath, html_name, tech in items:
            folder = Path(safe_path(survey_root / rel_subpath))
            html_file = folder / html_name

            temp_html_file = folder / "_temp_render_c.html"
            out_png = (out_path / f"{label}.png").resolve()

            if not os.path.exists(safe_path(html_file)):
                print(f"[ERROR] HTML file not found: {html_file}")
                continue

            with open(safe_path(html_file), "r", encoding="utf-8") as fh:
                content = fh.read()

            content = content.replace("unipolar_sinewave: true", "unipolar_sinewave: false")
            mod_content = content.replace("</head>", INJECTION_TEMPLATE + "</head>")

            try:
                with open(safe_path(temp_html_file), "w", encoding="utf-8") as fh:
                    fh.write(mod_content)

                url = f"http://127.0.0.1:{port}/{rel_subpath}/_temp_render_c.html"

                cmd = [
                    browser_path,
                    "--headless=new",
                    "--disable-gpu",
                    "--run-all-compositor-stages-before-draw",
                    "--virtual-time-budget=5000",
                    f"--screenshot={out_png}",
                    "--window-size=1200,380",
                    url,
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            finally:
                if os.path.exists(safe_path(temp_html_file)):
                    try:
                        os.remove(safe_path(temp_html_file))
                    except Exception:
                        pass

            is_valid = os.path.exists(safe_path(out_png)) and not is_blank_or_invalid_image(out_png)
            if not is_valid and os.path.exists(safe_path(out_png)):
                try:
                    os.remove(safe_path(out_png))
                except Exception:
                    pass
            out_size = os.path.getsize(safe_path(out_png)) if is_valid else 0
            print(f"[{tech:3s}] {label:20s} -> {'Saved' if is_valid else 'BLANK/INVALID'} ({out_size:,} bytes) to {out_png.name}")
            results.append({
                "label": label,
                "tech": tech,
                "output_file": str(out_png),
                "file_size": out_size,
                "status": "SUCCESS" if is_valid else "FAILED",
            })
    finally:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass
        if t.is_alive():
            t.join(timeout=2.0)

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
