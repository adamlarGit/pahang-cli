# Ticket 052: Un-stub Utility Actions Registry

## Parent Map

[Map 048: Standalone Utility Actions Deep Dive & Implementation](file:///.issues/048-standalone-utility-actions-map.md)

## Type

`task` (AFK)

## Status

`CLOSED`

## Question

How should `src/utility_actions.py` be updated to un-stub all 11 runners and connect them to domain workflows with standalone fallback context?

## Resolution

Completely removed `_make_stub_runner` from `src/utility_actions.py`. Un-stubbed all 11 Utility Actions by implementing lazy-loaded runner functions pointing to domain workflow modules under `src/workflows/`. Fixed `_load_whatsapp_runner` to use `get_or_create_utility_environment` fallback when `env is None`.
