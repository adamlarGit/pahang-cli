import argparse
import http.server
import json
import os
from pathlib import Path
import posixpath
import socket
import socketserver
import subprocess
import threading
import time
import urllib.parse
from PIL import Image


def safe_path(p: Path | str) -> str:
    """Ensure Windows extended-length path compatibility (\\\\?\\)."""
    s = str(Path(p).resolve())
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def find_free_port() -> int:
    """Finds an available TCP port on localhost dynamically."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def auto_discover_measurements(survey_dir: Path | str) -> list[tuple[str, str, str, str]]:
    """
    Dynamically discovers all Switchgear and Transformer TEV and Ultrasonic measurements.
    Returns list of tuples: (label, relative_subpath, html_filename, tech_type)
    """
    base_path = Path(safe_path(survey_dir))
    items = []

    # 1. Scan SWG directory (FEEDER_1, FEEDER_2, ..., FEEDER_N)
    swg_dir = base_path / "SWG"
    if swg_dir.exists() and swg_dir.is_dir():
        for feeder_folder in sorted(swg_dir.iterdir(), key=lambda p: p.name):
            if not feeder_folder.is_dir():
                continue
            feeder_name = feeder_folder.name.upper()  # e.g. FEEDER_1

            # Find TEV measurement subfolder
            for meas in feeder_folder.iterdir():
                if meas.is_dir() and meas.name.endswith("_TEV"):
                    html_file = meas / "TEV.html"
                    if html_file.exists():
                        rel_path = f"SWG/{feeder_folder.name}/{meas.name}"
                        label = f"SWG_{feeder_name}_TEV"
                        items.append((label, rel_path, "TEV.html", "TEV"))

            # Find Ultrasonic measurement subfolder
            for meas in feeder_folder.iterdir():
                if meas.is_dir() and meas.name.endswith("_Ultrasonic"):
                    html_file = meas / "Ultrasonic.html"
                    if html_file.exists():
                        rel_path = f"SWG/{feeder_folder.name}/{meas.name}"
                        label = f"SWG_{feeder_name}_US"
                        items.append((label, rel_path, "Ultrasonic.html", "US"))

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
                    html_file = meas / "Ultrasonic.html"
                    if html_file.exists():
                        rel_path = f"TX/{tx_folder.name}/{meas.name}"
                        label = f"TX_{tx_name}_US"
                        items.append((label, rel_path, "Ultrasonic.html", "US"))

            # Find TEV measurement subfolder if any on TX
            for meas in tx_folder.iterdir():
                if meas.is_dir() and meas.name.endswith("_TEV"):
                    html_file = meas / "TEV.html"
                    if html_file.exists():
                        rel_path = f"TX/{tx_folder.name}/{meas.name}"
                        label = f"TX_{tx_name}_TEV"
                        items.append((label, rel_path, "TEV.html", "TEV"))

    return items


# Non-overlapping Flexbox Layout: 320px Left Measurement Table + 840px Right PRPD Graph
INJECTION_TEMPLATE = """
<style>
header, ul.nav, #graphcontroltab, #maximise_prpd, #zoom_help, #tf_wfm_section, .navbar-fixed-bottom { display: none !important; }
#survey-container .panel:nth-child(1), #survey-container .panel:nth-child(2) { display: none !important; }
#survey-container .panel:nth-child(3) { display: block !important; margin: 0 !important; border: 1px solid #bce8f1 !important; }
#survey-container .panel-heading { font-weight: bold !important; font-size: 13px !important; padding: 6px 12px !important; }
#survey-container table { font-size: 11px !important; margin-bottom: 0 !important; width: 100% !important; }
#survey-container table td { padding: 4px 8px !important; }
</style>
<script>
window.addEventListener('load', function() {
    document.body.style.cssText = 'display: flex !important; flex-direction: row !important; align-items: stretch !important; justify-content: flex-start !important; width: 1200px !important; height: 380px !important; margin: 0 !important; padding: 10px !important; box-sizing: border-box !important; background: white !important; overflow: hidden !important;';

    var surveyEl = document.querySelector('.survey');
    if (surveyEl) {
        surveyEl.className = 'survey';
        surveyEl.style.cssText = 'width: 320px !important; min-width: 320px !important; max-width: 320px !important; flex: 0 0 320px !important; margin: 0 15px 0 0 !important; padding: 0 !important; float: none !important;';
        var surveyTab = surveyEl.querySelector('.tab-content');
        if (surveyTab) surveyTab.style.cssText = 'width: 100% !important; padding: 0 !important; margin: 0 !important;';
    }

    var allTabContents = document.querySelectorAll('.tab-content');
    var graphTabContent = allTabContents[allTabContents.length - 1];
    if (graphTabContent) {
        graphTabContent.style.cssText = 'flex: 1 1 840px !important; width: 840px !important; height: 360px !important; margin: 0 !important; padding: 0 !important; float: none !important; overflow: hidden !important;';
    }

    var phaseTab = document.getElementById('phase_tab');
    if (phaseTab) {
        phaseTab.style.cssText = 'width: 100% !important; height: 100% !important; margin: 0 !important; padding: 0 !important; float: none !important; display: block !important;';
    }

    var prpdSection = document.getElementById('prpd_section');
    if (prpdSection) {
        prpdSection.style.cssText = 'width: 100% !important; height: 100% !important; margin: 0 !important; padding: 0 !important; float: none !important; position: relative !important;';
    }

    var prpdGraph = document.getElementById('prpd_graph');
    if (prpdGraph) {
        prpdGraph.style.cssText = 'width: 100% !important; height: 100% !important;';
    }

    setTimeout(function() {
        if (typeof prpd !== 'undefined') {
            prpd.sinewave_mode = 0;
            prpd.Plot();
        }
    }, 150);
});
</script>
"""


def generate_all_survey_prpd_option_c(survey_dir: Path | str, output_dir: Path | str) -> list[dict]:
    """
    Auto-discovers and generates Option C images for any given UltraTEV survey folder.
    """
    survey_raw = str(Path(survey_dir).resolve())
    out_path = Path(output_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    items = auto_discover_measurements(survey_raw)
    if not items:
        print(f"[ERROR] No measurements found in survey directory: {survey_raw}")
        return []

    print("================================================================================")
    print("OPTION C: AUTO-DISCOVERED PRPD + MEASUREMENT TABLE GENERATION")
    print(f"Source Survey: {survey_raw}")
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
            full_path = safe_path(survey_raw)
            for word in words:
                full_path = os.path.join(full_path, word)
            if trailing_slash:
                full_path += "/"
            return full_path

        def log_message(self, format, *args):
            pass  # Suppress HTTP access logging for clean CLI output

    port = find_free_port()
    httpd = socketserver.TCPServer(("127.0.0.1", port), CustomHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)

    chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    results = []

    try:
        for label, rel_subpath, html_name, tech in items:
            folder = Path(safe_path(Path(survey_raw) / rel_subpath))
            html_file = folder / html_name
            temp_html_file = folder / "_temp_render_c.html"
            out_png = out_path / f"{label}.png"

            if not os.path.exists(safe_path(html_file)):
                print(f"[ERROR] HTML file not found: {html_file}")
                continue

            with open(safe_path(html_file), "r", encoding="utf-8") as fh:
                content = fh.read()

            content = content.replace("unipolar_sinewave: true", "unipolar_sinewave: false")
            mod_content = content.replace("</head>", INJECTION_TEMPLATE + "</head>")

            with open(safe_path(temp_html_file), "w", encoding="utf-8") as fh:
                fh.write(mod_content)

            url = f"http://127.0.0.1:{port}/{rel_subpath}/_temp_render_c.html"

            cmd = [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=5000",
                f"--screenshot={out_png}",
                "--window-size=1200,380",
                url,
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            if os.path.exists(safe_path(temp_html_file)):
                try:
                    os.remove(safe_path(temp_html_file))
                except Exception:
                    pass

            out_size = os.path.getsize(safe_path(out_png)) if os.path.exists(safe_path(out_png)) else 0
            print(f"[{tech:3s}] {label:20s} -> Saved ({out_size:,} bytes) to {out_png.name}")
            results.append({
                "label": label,
                "tech": tech,
                "output_file": str(out_png),
                "file_size": out_size,
                "status": "SUCCESS" if out_size > 0 else "FAILED",
            })
    finally:
        httpd.shutdown()

    print("================================================================================")
    print(f"Successfully generated {len(results)} Option C images!")
    print("================================================================================")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Option C PRPD + Measurement Table composite graphs.")
    parser.add_argument(
        "--survey-dir", "-s",
        default=r"C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\RAW MATERIAL\RAUB\02. SEPTEMBER\02-09-2026\199\RAW DATA\US+TEV\20260902T103527_199-LEMBAH-KLAU-BARU",
        help="Path to the raw UltraTEV survey folder."
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=r"docs\prpd_preview\option_c",
        help="Destination directory for generated PNG images."
    )

    args = parser.parse_args()
    generate_all_survey_prpd_option_c(args.survey_dir, args.output_dir)
