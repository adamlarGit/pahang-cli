# Ticket 040: Port Frozen uv Sync and Lockfile EOL Enforcement

## Parent Map

[Map 036: Port Johor JBU CLI Features (v2.9.0 -> v2.12.2) to Pahang CLI](file:///.issues/036-port-johor-v2-9-to-latest-features-map.md)

## Type

`task` (AFK)

## Question

How should we update `start_cli.bat` and `.gitattributes` to enforce `--frozen` execution mode during `uv sync` / `uv run` and maintain consistent `eol=lf` on `uv.lock`?

## Source Commits

- `b8b6d0c`: `fix(cli): enforce frozen uv sync and eol for lockfile`

## Summary of Work

1. Add `--frozen` flag to `uv sync` and `uv run` commands in `start_cli.bat` to prevent unintentional `uv.lock` mutation during execution.
2. Add `.gitattributes` specifying `uv.lock text eol=lf`.
