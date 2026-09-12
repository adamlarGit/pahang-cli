# Agent Instructions

## Agent skills

### Issue tracker

GitHub Issues via `gh` CLI (`adamlarGit/pahang-cli`). See `docs/agents/issue-tracker.md`.

### Ticket lifecycle

All tickets implemented by agents must be closed locally in `map.md` and remotely via `gh issue close`. See `.agents/rules/ticket-lifecycle.md`.

### Triage labels

Canonical five-role triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` + `docs/adr/`). See `docs/agents/domain.md`.
