# Ticket 038: Port remove_desktop_ini Utility Workflow

## Parent Map

[Map 036: Port Johor JBU CLI Features (v2.9.0 -> v2.12.2) to Pahang CLI](file:///.issues/036-port-johor-v2-9-to-latest-features-map.md)

## Type

`task` (AFK)

## Question

How should we port the recursive `remove_desktop_ini` workflow action, interactive folder prompt, PowerShell script helper, Python fallback, unit tests, and documentation into Pahang CLI?

## Source Commits

- `9b8950e`: `feat(utility): add remove_desktop_ini workflow action`

## Summary of Work

1. Create `src/remove_desktop_ini_workflow.py` for recursive scanning and deletion of hidden `desktop.ini` files.
2. Register "Remove desktop.ini files (recursive)" action in `src/utility_actions.py`.
3. Create `scripts/remove_desktop_ini.ps1` with Python fallback.
4. Add unit test suite `tests/test_remove_desktop_ini.py`.
5. Update `docs/workflows/utility_actions.md` and `README.md`.
