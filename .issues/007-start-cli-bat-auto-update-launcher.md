# Ticket: Port start_cli.bat Auto-Update Launcher for Pahang CLI

**Labels**: `wayfinder:task`
**Parent**: [Map](file:///.issues/001-map.md)
**Status**: Closed
**Blocked By**: [CLI Entrypoint and Verification](file:///.issues/006-cli-entrypoint-and-verification.md)

## Question

How should `start_cli.bat` be adapted from the Johor JBU source to serve as the auto-update launcher for `pahang-cli`?

Source reference: `C:\Users\ADAM\Documents\PO 42234207 - JOHOR - JBU - 400 PE IR US TEV\start_cli.bat`

The launcher needs to:
- Fetch `origin/main` and compare `__version__` between local and remote `src/__init__.py`
- Prompt operator to update (Y/N) → `git pull` + `uv sync`
- Launch `uv run pahang-cli`
- Update all Johor branding references to Pahang

## Resolution

- **`start_cli.bat`**: Ported from source with all version-check and auto-update logic preserved identically. Changed launch command from `uv run johor-cli` to `uv run pahang-cli` and branding from "Johor JBU CLI" to "Pahang CLI".
- **`settings_actions.py`**: Restored the 3 exit-message lines that were trimmed during initial port — rollback now tells operators to restart via `start_cli.bat` and advises choosing 'N' at the update prompt to stay on the rolled-back version.
