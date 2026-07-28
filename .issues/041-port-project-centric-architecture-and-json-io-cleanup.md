# Ticket 041: Port Project-Centric Architecture and JSON IO Cleanup

## Parent Map

[Map 036: Port Johor JBU CLI Features (v2.9.0 -> v2.12.2) to Pahang CLI](file:///.issues/036-port-johor-v2-9-to-latest-features-map.md)

## Type

`task` (AFK)

## Question

How should we enforce project-centric configuration in `src/project/repository.py`, isolate `.processed_folders.json` and template paths inside project `base_path`, extract specific `_read_json`/`_write_json` IO helpers, and update `start_cli.bat` pre-flight checks and documentation?

## Source Commits

- `b4e23f4`: `feat(arch): implement project-centric architecture and per-project templates`
- `bb099bc`: `refactor(repo): enforce project-centric configuration and clean up json IO`
- `d8de44a`: `docs(config): clarify template relative sub-paths in Project-Centric Architecture`

## Summary of Work

1. Isolate `project_config.json`, `.processed_folders.json`, and project templates within the active project `base_path`.
2. Ensure `.processed_folders.json` is untracked in `.gitignore`.
3. Refactor `JsonFileProjectRepository` (`src/project/repository.py`) to extract `_read_json` and `_write_json` helper methods with specific exception handling (`FileNotFoundError`, `json.JSONDecodeError`) instead of broad exception swallowing.
4. Remove dual-writing of camera configs to global `.cli_config.json`.
5. Add pre-flight checks and offline resilience to `start_cli.bat`.
6. Add `docs/project_centric_architecture.md` and `docs/research_cli_sharing_and_portability.md`.
