# Map: Port Johor JBU CLI Features (v2.9.0 -> v2.12.2) to Pahang CLI

## Destination

Port all 5 major feature modules and architectural improvements added to Johor JBU CLI after release `v2.9.0` (up to `v2.12.2`) into `pahang-cli`, ensuring feature parity, updated CLI selectors, robust JSON IO, camera configuration presets, desktop.ini utility workflows, and frozen lockfile execution.

## Notes

- **Source Reference CLI**: `C:\Users\ADAM\Documents\PO 42234207 - JOHOR - JBU - 400 PE IR US TEV`
- **Target CLI**: `C:\Users\ADAM\Desktop\pahang-cli`
- **Source Range**: Tag `v2.9.0` to `HEAD` (commits `7868d4e` through `d8de44a`)
- **Key Skills**: `/wayfinder`, `/grilling`, `/tdd`, `/smart-commit`

## Decisions so far

- [Feature Identification](file:///.issues/036-port-johor-v2-9-to-latest-features-map.md) — Audited 11 commits in Johor CLI past `v2.9.0` and consolidated them into 5 distinct feature tickets (037–041).
- [Ticket 040: Port Frozen uv Sync and Lockfile EOL Enforcement](file:///.issues/040-port-frozen-uv-sync-and-lockfile-eol-enforcement.md) — Enforced `--frozen` flag on `uv sync`/`uv run` in `start_cli.bat` and added `.gitattributes` for `uv.lock text eol=lf`.
- [Ticket 039: Port CLI Selectors Multi-Digit Numbering and Shortcuts](file:///.issues/039-port-cli-selectors-multi-digit-numbering-and-shortcuts.md) — Overhauled `src/cli_selectors.py` with modular multi-digit numbering (`1..10..11`), bracketed shortcuts (`[C] Cancel`), prompt_toolkit keybindings (`use_shortcuts=False`), title prefix stripping, and 56 passing unit tests.
- [Ticket 041: Port Project-Centric Architecture and JSON IO Cleanup](file:///.issues/041-port-project-centric-architecture-and-json-io-cleanup.md) — Isolated per-project templates and `.processed_folders.json`, extracted `_read_json`/`_write_json` with `(FileNotFoundError, json.JSONDecodeError)` exception handling, and added pre-flight checks to `start_cli.bat`.
- [Ticket 037: Port IR Single File and Dual IR/DC Camera Presets](file:///.issues/037-port-ir-single-file-and-dual-ir-dc-camera-presets.md) — Ported `IR_` Single File and Dual `IR_`/`DC_` camera presets, verbose menu labels, module-level imports, terminal encoding protection, and unit tests in `tests/test_camera_config.py`.
- [Ticket 038: Port remove_desktop_ini Utility Workflow](file:///.issues/038-port-remove-desktop-ini-utility-workflow.md) — Ported recursive `remove_desktop_ini` workflow action, interactive path selector, `scripts/remove_desktop_ini.ps1`, Python fallback, unit tests, and documentation.
- [Ticket 042: Isolate Per-Project Templates and Implement Workspace Bootstrapping](file:///.issues/042-isolate-per-project-templates-and-workspace-bootstrapping.md) — Isolated template resolution to `<base_path>/templates/`, added `_initialize_project_workspace` bootstrapping with `_safe_copy`, hooked environment instantiation and CLI project wizard, removed dead `GLOBAL_TEMPLATES_DIR` seed copying code, and added test suite `tests/test_storage.py`.



## Child Tickets

- [Ticket 037: Port IR Single File and Dual IR/DC Camera Presets](file:///.issues/037-port-ir-single-file-and-dual-ir-dc-camera-presets.md)
- [Ticket 038: Port remove_desktop_ini Utility Workflow](file:///.issues/038-port-remove-desktop-ini-utility-workflow.md)
- [Ticket 039: Port CLI Selectors Multi-Digit Numbering and Shortcuts](file:///.issues/039-port-cli-selectors-multi-digit-numbering-and-shortcuts.md)
- [Ticket 040: Port Frozen uv Sync and Lockfile EOL Enforcement](file:///.issues/040-port-frozen-uv-sync-and-lockfile-eol-enforcement.md)
- [Ticket 041: Port Project-Centric Architecture and JSON IO Cleanup](file:///.issues/041-port-project-centric-architecture-and-json-io-cleanup.md)
- [Ticket 042: Isolate Per-Project Templates and Implement Workspace Bootstrapping](file:///.issues/042-isolate-per-project-templates-and-workspace-bootstrapping.md)


## Not yet specified

<!-- Fog of war: in-scope fog you can't ticket yet -->
- Potential Pahang-specific adjustments for per-project template directory structures.

## Out of scope

- Direct copying of Johor-specific PE substation data or PO-specific quick report templates without Pahang adaptation.
