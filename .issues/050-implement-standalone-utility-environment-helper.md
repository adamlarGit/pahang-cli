# Ticket 050: Implement Standalone Utility Environment Helper

## Parent Map

[Map 048: Standalone Utility Actions Deep Dive & Implementation](file:///.issues/048-standalone-utility-actions-map.md)

## Type

`task` (AFK)

## Status

`CLOSED`

## Question

How should `get_or_create_utility_environment(target_dir: Path | None = None)` be implemented in `src/project/environment.py` to seamlessly handle active projects vs transient standalone directory execution?

## Resolution

Implemented `get_or_create_utility_environment(target_dir: Path | None = None) -> ProjectEnvironment` in `src/project/environment.py`. It checks `load_project_environment()`, returning the active environment if present, or interactively prompting for a target directory and synthesizing a transient `ProjectEnvironment` anchored at that location.
