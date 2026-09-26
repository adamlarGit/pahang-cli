<!-- status: closed -->
Part of #71
Specification: [spec.md](../spec.md)

# 075: refactor(scripts): align preview script with centralized measurement discovery

**What to build:** Refactor the standalone developer preview script (`scripts/generate_prpd_option_c_html.py`) to import and reuse the centralized survey discovery engine (`discover_survey_measurements`) and Option C rendering infrastructure from `src/quick_report/prpd.py`. Eliminates redundant parsing code, eliminates blind numeric suffixes (`_2`, `_3`), and guarantees 100% naming and rendering parity between local preview generation and the production CLI utility.

**Blocked by:** #72 (can run in parallel with #73 and #74)

**Status:** Closed

- [x] Refactor `scripts/generate_prpd_option_c_html.py`:
  - Import `discover_survey_measurements` and `format_measurement_label` from `src/quick_report/prpd.py`.
  - Replace legacy regex-based `auto_discover_measurements()` with `discover_survey_measurements()`.
  - Replace legacy duplicate counter logic with canonical `{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}.png` naming.
  - Re-wire `generate_all_survey_prpd_option_c()` to directly invoke `render_prpd_option_c_image()` and `SurveyHttpServer` from `src/quick_report/prpd.py`.
- [x] Add regression test / validation script in `tests/test_prpd_preview_script.py`:
  - Test executing `generate_all_survey_prpd_option_c` against synthetic survey fixture in `tmp_path`.
  - Verify that generated output files match `{ASSET}_{SUBASSET}_{COMPONENT}_{TECH}.png` schema without `_2` blind suffixes.
- [x] Verify manual CLI execution:
  - Run `python scripts/generate_prpd_option_c_html.py --help` to confirm CLI argument compatibility (`--survey-dir`, `--output-dir`).
  - Dry-run against a sample survey directory to confirm clean headless execution and output.
