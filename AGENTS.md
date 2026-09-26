# Agent Instructions (Worktree: Web Migration & Mobile Testsheet)

> [!IMPORTANT]
> **Worktree Mission**:
> This worktree (`pahang-cli-web` on branch `feature/pwa-web-migration`) is dedicated exclusively to the Web Migration and Mobile Testsheet platform.
> The production branch `main` in the primary workspace must remain untouched and clean until the final synchronized cutover.

## Autonomous Pre-Flight Main Sync Rule

Before claiming any migration ticket or writing code, the agent MUST run:
1. `git log HEAD..main --oneline`
2. If `main` is ahead (contains new commits from hotfixes/maintenance):
   - Automatically run: `git merge main -m "chore: sync with main"`
   - Run tests to confirm zero regressions: `pytest`
   - If any merge conflict arises, immediately invoke the `resolving-merge-conflicts` skill.

## Active Migration Map & Agent Boot Protocol

The single source of truth for all migration work is:
[`.wayfinder/web-migration-and-mobile-testsheet/map.md`](.wayfinder/web-migration-and-mobile-testsheet/map.md)

When asked to work on or advance the migration (e.g. "next ticket", "pick up migration", "proceed"):
1. Open the Master Map [`.wayfinder/web-migration-and-mobile-testsheet/map.md`](.wayfinder/web-migration-and-mobile-testsheet/map.md) and identify the active Stage.
2. Open the active Track Sub-Map under `.wayfinder/web-migration-and-mobile-testsheet/tracks/` and locate the current **Frontier Ticket** (the first open ticket with all blockers closed).
3. Read the ticket's acceptance criteria and verify alignment with Master Decisions `D-MASTER.1` through `D-MASTER.14`.
4. Implement the ticket test-first, maintaining namespace isolation (`src/db/`, `src/web/`, `src/generator/`, `web/pwa/`).
5. Execute the **Mandatory Ticket Completion Checklist** below before ending the turn.

## Mandatory Ticket Completion Checklist

Whenever an agent implements or resolves a ticket, the turn is NOT complete until:
1. **Tests Pass**: Automated tests verifying the feature pass cleanly.
2. **Ticket File Sync**: In `tracks/<track>/tickets/<ticket>.md`, mark criteria `[x]` and set `<!-- status: closed -->`.
3. **Sub-Map Sync**: In `tracks/<track>/map.md`, change status to `Closed` and update the Mermaid diagram node to `Closed`.
4. **Master Map Sync**: If completing a stage, update the Master Map verification gate.
5. **Atomic Commit**: Commit code, tests, and documentation updates together using `caveman-commit`.

---

## Agent skills

### Issue tracker

GitHub Issues via `gh` CLI (`adamlarGit/pahang-cli`). See `docs/agents/issue-tracker.md`.

### Ticket lifecycle

All tickets implemented by agents must be closed locally in `map.md` and remotely via `gh issue close`. See `.agents/rules/ticket-lifecycle.md`.

### Triage labels

Canonical five-role triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`CONTEXT.md` + `docs/adr/`). See `docs/agents/domain.md`.
