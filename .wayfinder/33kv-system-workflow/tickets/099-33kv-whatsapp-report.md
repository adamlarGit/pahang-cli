<!-- status: open -->
Part of #90
Specification: [spec.md](../spec.md)

# 099: feat(33kv-whatsapp): 33kV WhatsApp Daily Report generation

**What to build:** Extend `WhatsAppReportWorkflow` to support 33kV projects by consolidating Quick Report `.docx` files matching a target date across all station folders, matching records against `PYTHON/TOTAL PE.xlsx` (`DataCycle1`), programmatically injecting voltage-aware links and activity headers, and rendering daily WhatsApp reports to `PYTHON/WHATSAPP/{NN}. {DD-MM-YYYY}.docx`.

**Blocked by:** #96, #98

**Status:** ready-for-agent

- [ ] Update `QUALIFYING_DOCX_PATTERN` in `src/workflows/whatsapp.py`:
  - Anchor defect indicators to the trailing parentheses (`r"^(\d+)\.?\s*(.*?)(?:\s*\(([^()]+)\))?\.docx$"`)
  - Preserve internal parentheses in station names (e.g. `02. SSU KIIP (SSU CAMEL POWER) 33kV (VI).docx` -> station `SSU KIIP (SSU CAMEL POWER) 33kV`, defect `VI`).
- [ ] Implement cross-station date folder discovery in `WhatsAppReportExtractor` for 33kV:
  - When invoked by target date, discover and aggregate qualifying `.docx` files across all station directories under `QUICK REPORT/` (e.g. `QUICK REPORT/GEBENG/.../07-10-2026/` and `QUICK REPORT/KUANTAN/.../07-10-2026/`).
  - Sort aggregated documents by integer PE number.
- [ ] Ensure `WhatsAppReportFilter` and matching logic against `TOTAL PE.xlsx` (`DataCycle1`):
  - Resolves integer PE number matching (`1`, `2`, `3`...).
  - Extracts substation name and WONUM from Column F (`WO`) (rendering `-` if unpopulated).
  - Populates defect indicators from filename suffix (`VI`, `US+VI`, `IR+VI`, or `-`).
- [ ] Programmatic context & template rendering in `WhatsAppReportTransformer`:
  - Injects `activity`: `"CBM 33KV"` for 33kV (vs `"CBM 11kV"` for 11kV).
  - Injects programmatic SharePoint OneDrive URLs: `link_laporan` and `link_engr` based on `ProjectEnvironment.voltage_type`.
  - Multi-station grouping: when multiple stations exist on the date, formats combined header `STATION : *GEBENG/KUANTAN*` and groups items under station subheadings with continuous 1-based numbering. When single station, formats single header without subheadings.
- [ ] Save output document in `WhatsAppReportLoader`:
  - For 33kV: formats filename strictly as `{next_num:02d}. {clean_date}.docx` (e.g. `01. 07-10-2026.docx`) in `PYTHON/WHATSAPP/`.
  - Preserves `{next_num:02d}. {station} {clean_date}.docx` for 11kV.
- [ ] Ensure CLI Action (`WhatsAppReportAction`) and `run_generate_whatsapp_report` work seamlessly for 33kV active project environments.
- [ ] Add unit tests in `tests/test_whatsapp_report_33kv.py` verifying multi-station discovery, regex matching with internal parentheses, programmatic link injection, grouping, and output naming.
