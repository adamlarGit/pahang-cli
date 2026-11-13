# Agent Instructions

## Agent skills

### Issue tracker

GitHub Issues via `gh` CLI (`adamlarGit/pahang-cli`). See `docs/agents/issue-tracker.md`.

### Ticket lifecycle

When resolving a ticket, follow the GitHub-only closure workflow in `.agents/rules/ticket-lifecycle.md`.

### Research and prototype tickets

Ticket Folder layout, write-up template, claim labels and how to land. Read before working a `wayfinder:research` or `wayfinder:prototype` ticket, or citing research in a spec: `docs/agents/research-and-prototypes.md`.

### Triage labels

Canonical five-role triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` + `docs/adr/`). See `docs/agents/domain.md`.

## Thermal editor (separate repo)

The standalone editor for thermal images lives in its own repo, `adamlarGit/thermal-editor`, with its own map and tickets. Work on the editor goes there, not here.

This repo and the editor share files on disk and no code. The pipeline reads the image in a substation's `RAW DATA/IR/` folder as saved, and the CLI does not launch the editor. The decision record is issue #239.
