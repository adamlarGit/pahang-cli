"""Native Python & Headless Chromium PRPD graph generator and survey directory resolution module.

Implements Option C (Measurement Table + PRPD Graph composite via Headless Chrome)
and Option B (Pure PRPD scatter graph via native Matplotlib and FlatBuffers/JSON decoding),
deterministic asset discovery, and DocxTemplate InlineImage binding.
"""

from __future__ import annotations

import base64
import gzip
import http.server
import json
import logging
import os
from pathlib import Path
import posixpath
import re
import shutil
import socket
import socketserver
import struct
import subprocess
import threading
import time
from typing import Any
import urllib.parse
import uuid

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# Non-overlapping Flexbox Layout: 320px Left Measurement Table + 840px Right PRPD Graph
OPTION_C_INJECTION_TEMPLATE = """
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


def find_free_port() -> int:
    """Finds an available TCP port on localhost dynamically."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_chrome_executable() -> str:
    """Find Google Chrome or Microsoft Edge executable path across standard locations."""
    env_override = os.environ.get("CHROME_PATH") or os.environ.get("CHROMIUM_PATH")
    if env_override and os.path.isfile(env_override):
        return env_override

    candidate_paths: list[str] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    # Google Chrome candidate paths (64-bit, 32-bit, LocalAppData)
    candidate_paths.extend([
        os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe") if local_app_data else "",
    ])

    # Microsoft Edge candidate paths (Edge fallback)
    candidate_paths.extend([
        os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(local_app_data, "Microsoft", "Edge", "Application", "msedge.exe") if local_app_data else "",
    ])

    for path in candidate_paths:
        if path and os.path.isfile(path):
            return path

    for cmd in ("chrome", "google-chrome", "google-chrome-stable", "chromium", "msedge", "edge"):
        found = shutil.which(cmd)
        if found and os.path.isfile(found):
            return found

    raise FileNotFoundError(
        "No Google Chrome or Microsoft Edge executable found. "
        "Please install Google Chrome or Microsoft Edge, or set the CHROME_PATH environment variable."
    )


class SurveyHttpServer:
    """Lightweight localhost HTTP server for serving survey directory assets to Headless Chrome."""

    def __init__(self, survey_dir: Path | str) -> None:
        self.survey_dir = str(Path(survey_dir).resolve())
        self.port = find_free_port()
        self._httpd: socketserver.TCPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        survey_raw = self.survey_dir

        class CustomHandler(http.server.SimpleHTTPRequestHandler):
            def translate_path(self, path: str) -> str:
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

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._httpd = socketserver.TCPServer(("127.0.0.1", self.port), CustomHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        time.sleep(0.1)
        return self.port

    def stop(self) -> None:
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None

    def __enter__(self) -> int:
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


def render_prpd_option_c_image(
    html_file: Path | str,
    output_png: Path | str,
    survey_root: Path | str,
    http_port: int,
    chrome_path: str | None = None,
    timeout_seconds: float = 15.0,
) -> Path | None:
    """Render an UltraTEV HTML measurement page to a composite PNG via Headless Chrome."""
    html_path = Path(safe_path(html_file))
    if not html_path.exists():
        return None

    survey_root_path = Path(safe_path(survey_root))
    out_png_path = Path(output_png).resolve()
    out_png_path.parent.mkdir(parents=True, exist_ok=True)

    chrome = chrome_path or find_chrome_executable()

    try:
        rel_subpath = html_path.parent.relative_to(survey_root_path).as_posix()
    except ValueError:
        rel_subpath = Path(html_path.parent).resolve().relative_to(Path(survey_root_path).resolve()).as_posix()

    with open(safe_path(html_path), "r", encoding="utf-8", errors="ignore") as fh:
        content = fh.read()

    mod_content = content.replace("unipolar_sinewave: true", "unipolar_sinewave: false")
    if "</head>" in mod_content:
        mod_content = mod_content.replace("</head>", OPTION_C_INJECTION_TEMPLATE + "</head>")
    else:
        mod_content = OPTION_C_INJECTION_TEMPLATE + mod_content

    temp_html_name = f"_temp_render_c_{uuid.uuid4().hex[:8]}.html"
    temp_html_file = html_path.parent / temp_html_name

    try:
        with open(safe_path(temp_html_file), "w", encoding="utf-8") as fh:
            fh.write(mod_content)

        url = f"http://127.0.0.1:{http_port}/{rel_subpath}/{temp_html_name}"

        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=5000",
            f"--screenshot={str(out_png_path)}",
            "--window-size=1200,380",
            url,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout_seconds)
    except Exception as exc:
        logging.warning("Option C headless render failed for %s: %s", html_file, exc)
        return None
    finally:
        if os.path.exists(safe_path(temp_html_file)):
            try:
                os.remove(safe_path(temp_html_file))
            except Exception:
                pass

    if os.path.exists(safe_path(out_png_path)) and os.path.getsize(safe_path(out_png_path)) > 0:
        return out_png_path
    return None


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


def _is_survey_dir(p: Path) -> bool:
    """Check if a directory looks like an UltraTEV survey root directory."""
    try:
        if not p.is_dir():
            return False
        if (p / "survey_summary.js").exists() or (p / "survey_metadata.js").exists():
            return True
        prefixes = ("SWG", "VCB", "RMU", "TX")
        return any(
            c.is_dir() and (c.name.upper().startswith(prefixes) or "TRANSFORMER" in c.name.upper())
            for c in p.iterdir()
        )
    except OSError:
        return False


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
            if _is_survey_dir(candidate):
                return candidate
            try:
                children = sorted(candidate.iterdir(), reverse=True)
            except OSError:
                children = []
            for child in children:
                if child.is_dir() and _is_survey_dir(child):
                    return child

    # Deep search fallback for any folder containing survey_summary.js or SWG/VCB/RMU
    try:
        for child in sorted(raw_path.rglob("survey_summary.js"), reverse=True):
            if child.parent.is_dir():
                return child.parent
        for pattern in ("SWG*", "VCB*", "RMU*"):
            for child in sorted(raw_path.rglob(pattern), reverse=True):
                parent = child.parent
                if parent.is_dir() and _is_survey_dir(parent):
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
    """Find the target SWG/VCB/RMU feeder survey directory using 3-tier precedence."""
    swg_prefixes = ("SWG", "VCB", "RMU")
    try:
        swg_dirs = [
            d for d in survey_root.iterdir()
            if d.is_dir() and d.name.upper().startswith(swg_prefixes)
        ]
    except OSError:
        return None

    if not swg_dirs:
        return None

    # Canonical exact "SWG", "VCB", "RMU" precede numbered variants
    swg_dirs.sort(key=lambda d: (0 if d.name.upper() in ("SWG", "VCB", "RMU") else 1, d.name.upper()))

    candidate_subdirs: list[Path] = []
    for s_dir in swg_dirs:
        try:
            candidate_subdirs.extend([d for d in s_dir.iterdir() if d.is_dir()])
        except OSError:
            continue

    # Tier 1: Match panel_no (Column A index, 1-based)
    if panel_no > 0:
        p_num_str = str(panel_no)
        target_names = {
            f"FEEDER_{p_num_str}",
            f"FEEDER {p_num_str}",
            f"PANEL_{p_num_str}",
            f"PANEL {p_num_str}",
            f"FEEDER_{p_num_str.zfill(2)}",
            f"PANEL_{p_num_str.zfill(2)}",
        }
        for d in candidate_subdirs:
            d_upper = d.name.upper()
            d_norm = d_upper.replace("-", "_")
            if d_upper in target_names or d_norm in target_names:
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
            f"FEEDER_{int_digit.zfill(2)}",
            f"PANEL_{int_digit.zfill(2)}",
        }
        for d in candidate_subdirs:
            d_upper = d.name.upper()
            d_norm = d_upper.replace("-", "_")
            if d_upper in target_variants or d_norm in target_variants:
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
    target_html = "TEV.html" if is_tev else "Ultrasonic.html"

    candidate_dirs = [
        d
        for d in feeder_or_tx_dir.iterdir()
        if d.is_dir() and target_pattern.upper() in d.name.upper()
    ]
    # Sort descending by timestamp / name
    candidate_dirs.sort(key=lambda x: x.name, reverse=True)

    for d in candidate_dirs:
        payload_file = d / target_payload
        html_file = d / target_html
        if (payload_file.exists() and payload_file.stat().st_size > 0) or (
            html_file.exists() and html_file.stat().st_size > 0
        ):
            return d

    return None


def generate_prpd_graphs_for_swg_panel(
    survey_root: Path | None,
    panel_no: int,
    output_dir: Path,
    feeder_no: str = "",
    panel_name: str = "",
    mode: str = "option_c",
    http_port: int | None = None,
    chrome_path: str | None = None,
) -> tuple[Path | None, Path | None]:
    """Generate US and TEV PRPD PNG graph images for a switchgear panel.

    Supports mode='option_c' (Headless Chrome) and mode='option_b' (Native Python).
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

    if mode == "option_b":
        # 1. Ultrasonic Graph (Option B)
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

        # 2. TEV Graph (Option B)
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
    else:
        # Option C: Headless Chrome
        us_dir = find_latest_measurement_dir(feeder_dir, "US")
        tev_dir = find_latest_measurement_dir(feeder_dir, "TEV")
        if not us_dir and not tev_dir:
            return None, None

        def _do_render(port: int, chrome: str) -> tuple[Path | None, Path | None]:
            u_png, t_png = None, None
            if us_dir:
                us_html = us_dir / "Ultrasonic.html"
                if us_html.exists():
                    us_out = output_dir / f"prpd_swg_panel{panel_no}_us.png"
                    u_png = render_prpd_option_c_image(
                        html_file=us_html,
                        output_png=us_out,
                        survey_root=survey_root,
                        http_port=port,
                        chrome_path=chrome,
                    )
            if tev_dir:
                tev_html = tev_dir / "TEV.html"
                if tev_html.exists():
                    tev_out = output_dir / f"prpd_swg_panel{panel_no}_tev.png"
                    t_png = render_prpd_option_c_image(
                        html_file=tev_html,
                        output_png=tev_out,
                        survey_root=survey_root,
                        http_port=port,
                        chrome_path=chrome,
                    )
            return u_png, t_png

        try:
            resolved_chrome = chrome_path or find_chrome_executable()
        except FileNotFoundError as exc:
            logging.warning("Option C rendering skipped: %s", exc)
            return None, None

        if http_port is not None:
            us_png, tev_png = _do_render(http_port, resolved_chrome)
        else:
            with SurveyHttpServer(survey_root) as port:
                us_png, tev_png = _do_render(port, resolved_chrome)

    return us_png, tev_png


def generate_prpd_graphs_for_transformer(
    survey_root: Path | None,
    tx_idx: int,
    output_dir: Path,
    mode: str = "option_c",
    http_port: int | None = None,
    chrome_path: str | None = None,
) -> tuple[Path | None, Path | None]:
    """Generate US and TEV PRPD PNG graph images for a transformer.

    Supports mode='option_c' (Headless Chrome) and mode='option_b' (Native Python).
    Returns (us_png_path, tev_png_path).
    """
    if not survey_root:
        return None, None

    tx_dir = find_tx_survey_dir(survey_root=survey_root, tx_idx=tx_idx)
    if not tx_dir:
        return None, None

    us_png: Path | None = None
    tev_png: Path | None = None

    if mode == "option_b":
        # 1. Ultrasonic Graph (Option B)
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

        # 2. TEV Graph (Option B)
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
    else:
        # Option C: Headless Chrome
        us_dir = find_latest_measurement_dir(tx_dir, "US")
        tev_dir = find_latest_measurement_dir(tx_dir, "TEV")
        if not us_dir and not tev_dir:
            return None, None

        def _do_render(port: int, chrome: str) -> tuple[Path | None, Path | None]:
            u_png, t_png = None, None
            if us_dir:
                us_html = us_dir / "Ultrasonic.html"
                if us_html.exists():
                    us_out = output_dir / f"prpd_tx{tx_idx}_us.png"
                    u_png = render_prpd_option_c_image(
                        html_file=us_html,
                        output_png=us_out,
                        survey_root=survey_root,
                        http_port=port,
                        chrome_path=chrome,
                    )
            if tev_dir:
                tev_html = tev_dir / "TEV.html"
                if tev_html.exists():
                    tev_out = output_dir / f"prpd_tx{tx_idx}_tev.png"
                    t_png = render_prpd_option_c_image(
                        html_file=tev_html,
                        output_png=tev_out,
                        survey_root=survey_root,
                        http_port=port,
                        chrome_path=chrome,
                    )
            return u_png, t_png

        try:
            resolved_chrome = chrome_path or find_chrome_executable()
        except FileNotFoundError as exc:
            logging.warning("Option C rendering skipped: %s", exc)
            return None, None

        if http_port is not None:
            us_png, tev_png = _do_render(http_port, resolved_chrome)
        else:
            with SurveyHttpServer(survey_root) as port:
                us_png, tev_png = _do_render(port, resolved_chrome)

    return us_png, tev_png


def generate_all_substation_prpd_graphs(
    survey_root: Path | str | None,
    output_dir: Path | str,
    mode: str = "option_c",
) -> dict[str, Any]:
    """Discover all SWG feeders and TX units and generate all PRPD PNG graphs in one pass.

    Supports mode='option_c' (Headless Chrome) and mode='option_b' (Native Python).

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

    # 1. SWG / VCB / RMU Feeders & Panels
    swg_prefixes = ("SWG", "VCB", "RMU")
    try:
        swg_dirs = [
            d for d in survey_path.iterdir()
            if d.is_dir() and d.name.upper().startswith(swg_prefixes)
        ]
    except OSError:
        swg_dirs = []
    swg_dirs.sort(key=lambda d: (0 if d.name.upper() in ("SWG", "VCB", "RMU") else 1, d.name.upper()))

    # 2. Transformer (TX) units
    candidate_tx_indices: set[int] = set()
    try:
        survey_children = [c for c in survey_path.iterdir() if c.is_dir()]
    except OSError:
        survey_children = []
    for child in survey_children:
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

    if mode == "option_b":
        # Option B generation (Native Python FlatBuffers/JSON decoding)
        for s_dir in swg_dirs:
            try:
                candidate_feeders = [d for d in s_dir.iterdir() if d.is_dir()]
            except OSError:
                continue
            for feeder_dir in sorted(candidate_feeders, key=lambda d: d.name):
                digits = re.findall(r"\d+", feeder_dir.name)
                if digits:
                    try:
                        panel_idx = int(digits[0])
                    except ValueError:
                        panel_idx = len(catalog["swg"]) + 1
                else:
                    panel_idx = len(catalog["swg"]) + 1

                while panel_idx in catalog["swg"]:
                    panel_idx += 1

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
    else:
        # Option C generation with Headless Chrome and localhost HTTP server
        try:
            chrome_path = find_chrome_executable()
        except FileNotFoundError as exc:
            logging.warning("Option C rendering skipped: %s", exc)
            return catalog

        with SurveyHttpServer(survey_path) as port:
            for s_dir in swg_dirs:
                try:
                    candidate_feeders = [d for d in s_dir.iterdir() if d.is_dir()]
                except OSError:
                    continue
                for feeder_dir in sorted(candidate_feeders, key=lambda d: d.name):
                    digits = re.findall(r"\d+", feeder_dir.name)
                    if digits:
                        try:
                            panel_idx = int(digits[0])
                        except ValueError:
                            panel_idx = len(catalog["swg"]) + 1
                    else:
                        panel_idx = len(catalog["swg"]) + 1

                    while panel_idx in catalog["swg"]:
                        panel_idx += 1

                    us_png: Path | None = None
                    tev_png: Path | None = None

                    us_meas = find_latest_measurement_dir(feeder_dir, "US")
                    if us_meas:
                        us_html = us_meas / "Ultrasonic.html"
                        if us_html.exists():
                            us_out = out_path / f"prpd_swg_panel{panel_idx}_us.png"
                            us_png = render_prpd_option_c_image(
                                html_file=us_html,
                                output_png=us_out,
                                survey_root=survey_path,
                                http_port=port,
                                chrome_path=chrome_path,
                            )

                    tev_meas = find_latest_measurement_dir(feeder_dir, "TEV")
                    if tev_meas:
                        tev_html = tev_meas / "TEV.html"
                        if tev_html.exists():
                            tev_out = out_path / f"prpd_swg_panel{panel_idx}_tev.png"
                            tev_png = render_prpd_option_c_image(
                                html_file=tev_html,
                                output_png=tev_out,
                                survey_root=survey_path,
                                http_port=port,
                                chrome_path=chrome_path,
                            )

                    catalog["swg"][panel_idx] = {
                        "us": us_png,
                        "tev": tev_png,
                    }

            for tx_idx in sorted(candidate_tx_indices):
                tx_dir = find_tx_survey_dir(survey_path, tx_idx=tx_idx)
                if not tx_dir or not tx_dir.exists():
                    continue

                us_png = None
                tev_png = None

                us_meas = find_latest_measurement_dir(tx_dir, "US")
                if us_meas:
                    us_html = us_meas / "Ultrasonic.html"
                    if us_html.exists():
                        us_out = out_path / f"prpd_tx{tx_idx}_us.png"
                        us_png = render_prpd_option_c_image(
                            html_file=us_html,
                            output_png=us_out,
                            survey_root=survey_path,
                            http_port=port,
                            chrome_path=chrome_path,
                        )

                tev_meas = find_latest_measurement_dir(tx_dir, "TEV")
                if tev_meas:
                    tev_html = tev_meas / "TEV.html"
                    if tev_html.exists():
                        tev_out = out_path / f"prpd_tx{tx_idx}_tev.png"
                        tev_png = render_prpd_option_c_image(
                            html_file=tev_html,
                            output_png=tev_out,
                            survey_root=survey_path,
                            http_port=port,
                            chrome_path=chrome_path,
                        )

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
    "OPTION_C_INJECTION_TEMPLATE",
    "SurveyHttpServer",
    "build_prpd_inline_images",
    "decode_tev_event_data",
    "decode_ultrasonic_phase_plot",
    "discover_ultratev_survey_dir",
    "find_chrome_executable",
    "find_free_port",
    "find_latest_measurement_dir",
    "find_swg_feeder_survey_dir",
    "find_tx_survey_dir",
    "generate_all_substation_prpd_graphs",
    "generate_prpd_figure",
    "generate_prpd_graphs_for_swg_panel",
    "generate_prpd_graphs_for_transformer",
    "render_prpd_option_c_image",
    "safe_path",
]

