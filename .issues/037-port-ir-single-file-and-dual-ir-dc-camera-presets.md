# Ticket 037: Port IR Single File and Dual IR/DC Camera Presets

## Parent Map

[Map 036: Port Johor JBU CLI Features (v2.9.0 -> v2.12.2) to Pahang CLI](file:///.issues/036-port-johor-v2-9-to-latest-features-map.md)

## Type

`task` (AFK/HITL)

## Question

How should we port the IR single file (`IR_0001.jpg`), dual `IR_` + `DC_` pair presets, verbose camera menu labels, module-level import fixes, and terminal encoding safeguards into Pahang CLI's `settings_actions.py` and `tests/test_camera_config.py`?

## Source Commits

- `7868d4e`: `feat(settings): add IR_ single file and dual IR_/DC_ presets`
- `3b6cbdb`: `docs(settings): make IR camera menu labels verbose`
- `7b3351b`: `fix(settings): fix CameraConfig NameError in camera pattern settings`

## Summary of Work

1. Add `IR_` Single File (`IR_0001.jpg`) preset and explicit Dual `IR_` + `DC_` Pair preset to camera configuration in `src/settings_actions.py`.
2. Update menu selection text to be verbose and clear regarding thermal and visual photo pairs.
3. Promote `CameraConfig` and `JsonFileProjectRepository` imports to module scope in `settings_actions.py`, save updated `CameraConfig` in `_configure_dg_pattern`, and add stdout encoding protection for Windows terminals.
4. Add unit test suite `tests/test_camera_config.py`.
