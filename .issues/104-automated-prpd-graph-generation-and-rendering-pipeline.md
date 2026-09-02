# Ticket 104: Automated PRPD Graph Generation and Rendering Pipeline

Labels: wayfinder:task, afk, state:closed

## Question

How should the native Python PRPD graph generation module (`src/quick_report/prpd.py`) be integrated into the report generation pipeline, managing temporary rendered image artifacts and binding `InlineImage` instances to `{{ us.prpd }}` and `{{ tev.prpd }}` placeholders with resilient fallback when no defect or no raw survey exists?

## Resolution

- **Module Implementation (`src/quick_report/prpd.py`)**:
  - `decode_tev_event_data`: Base64 decode + gzip decompress + FlatBuffers `UE01` EventVec table traversal unpacks `SingleEvent` structs (`peak`, `integral`, `phase`, `cycle`, `risetime`, `width`, `tf_t`, `tf_f`).
  - `decode_ultrasonic_phase_plot`: Parses JSON 2D arrays with UltraTEV $1/3\text{ dB}$ amplitude rounding.
  - `generate_prpd_figure`: Renders high-resolution PNG PRPD graphs matching UltraTEV's visual appearance and 4-tier repetition density bins (`#00FF00`, `#0000FF`, `#FF0000`, `#640000`) with zero sine wave.
  - `discover_ultratev_survey_dir`: Resolves `US+TEV` survey stems across single-TX and multi-TX configurations.
  - `find_swg_feeder_survey_dir` & `find_tx_survey_dir`: Implements deterministic 3-tier matching and multi-TX resolution (`TX1/Transformer/`, `TX2/Transformer/`, `TX/Transformer/`).
  - `find_latest_measurement_dir`: Discovers the latest timestamp run with valid non-empty data payload.
  - `build_prpd_inline_images`: Wraps generated PNG files in `docxtpl.InlineImage` (width $80\text{--}82\text{ mm}$) for `{{ us.prpd }}` and `{{ tev.prpd }}` with clean fallback to `""`.
- **Verification**: Verified via `tests/test_prpd_generator.py` (8 passing unit tests).
