# 1. Configurable PRPD Graph Generation Strategy (Option C Headless Chrome / Option B Native Python)

Date: 2026-09-07
Status: Accepted

## Context

In the Quick Report CBM defect detail pages (`swg-panel.docx` and `tx-hv-sides.docx`), the report embeds Partial Discharge (PD) analysis into `{{ us.prpd }}` and `{{ tev.prpd }}` placeholders.

We evaluated two distinct rendering approaches:
1. **Option C (Composite Table + PRPD Graph)**: Generates a 1200x380 px composite image containing the UltraTEV Bootstrap measurement table (sensor readings, accessory type, interpretation, noise level, and phase reference lock details) alongside the native Flot PRPD scatter graph (0-360 degree phase angle, 4-tier repetition density colors). Rendered via Headless Chromium.
2. **Option B (Pure PRPD Scatter Graph)**: Generates a pure PRPD scatter graph using native Python Matplotlib by decoding FlatBuffers binary records (`eventData.js`, UE01) and JSON acoustic events (`ultrasonic_phase_plot.js`).

Operators require the flexibility to select between Option C and Option B depending on deliverable presentation needs, while ensuring zero breakage to existing templates and automated report pipelines.

## Decision

1. **Default Mode**: Set **Option C** as the default PRPD generation mode for high-fidelity defect detail reporting.
2. **Configurable Strategy**: Make Option B switchable via a new Settings menu (`Configure PRPD Graph Style`) in the CLI.
3. **Configuration Storage**: Store `PrpdConfig` (`mode: "option_c" | "option_b"`) in `project_config.json` alongside `CameraConfig`. Exposed through `ProjectRepository` and `ProjectEnvironment`.
4. **Resilient Chromium Discovery**: Implement `find_chrome_executable()` checking standard Chrome paths (64-bit, 32-bit, LocalAppData) with Microsoft Edge (`msedge.exe`) fallback to guarantee execution on standard Windows client machines.
5. **Unified Catalog Return Signature**: Both Option B and Option C in `src/quick_report/prpd.py` return an identical, unified catalog structure:
   - `catalog['swg'][panel_no]['us']` and `catalog['swg'][panel_no]['tev']`
   - `catalog['tx'][tx_idx]['us']` and `catalog['tx'][tx_idx]['tev']`
6. **Canonical Fallback Policy**: Strict self-containment with no cross-option fallback. If Option C fails or a measurement is not recorded, the slot returns `None` which cleanly maps to an empty string `""` in DOCX templates.
7. **Document Sizing**: Image sizing in Word templates remains standardized at `width=Mm(80)` (or `82mm`).

## Consequences

- **Positive**:
  - Deliverable CBM defect pages in Quick Reports display comprehensive instrument metadata side-by-side with PRPD scatter graphs without manual editing.
  - Operators can switch between Option C and Option B without altering template layouts or schemas.
  - Windows workstations without Google Chrome automatically run via Microsoft Edge without configuration overhead.
- **Negative / Trade-offs**:
  - Option C headless browser execution takes ~1-2 seconds per screenshot versus sub-second native Matplotlib generation. Mitigated by reusing a single localhost HTTP server session across batch substation runs.
