# Ticket: Port and Adapt pyproject.toml and config.py for Pahang CLI

**Labels**: `wayfinder:grilling`
**Parent**: [Map](file:///.issues/001-map.md)
**Status**: Closed

## Question

How should `pyproject.toml` and `config.py` be structured and configured specifically for Pahang area (station mappings, project constants, dependencies, and CLI entry points)?

## Resolution

- **Station Mappings**: Configured `STATION_MAPPING` with 14 Pahang area station codes (`CMRN`, `CKTN`, `CJEN`, `CBMS`, `CBTG`, `CBGB`, `CROM`, `CTML`, `CPEK`, `CTRI`, `CKLS`, `CCHL`, `CRAU`, `CJRT`).
- **Project Constants**: Set default `total_plan: 300` and `defects_per_page: 6`.
- **Seed Files & ENGR Pattern**: Configured onboarding seed files (`DATA MSMS.xlsx`, `TOTAL PE.xlsx`) and set `ENGR_FILE_PATTERN` to `PYTHON\ENGR FROM DRIVE\ENGR-*.xlsx`.
- **Templates**: Replaced Telegram with WhatsApp template path (`WHATSAPP\TEMPLATE WHATSAPP.docx`), maintaining standard quick report template paths.
- **Package Configuration**: Created `pyproject.toml` for `pahang-cli` executable entrypoint script `pahang-cli = "src.workflow_cli:run_cli"`.
