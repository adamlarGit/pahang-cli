---
description: Enforces mandatory local map synchronization and GitHub issue closure whenever an agent implements, resolves, or verifies a ticket.
---

# Ticket Lifecycle & Completion Rule

Whenever an agent implements or resolves a ticket from a Wayfinder map or GitHub tracker, the task is **NOT complete** until the following 3-step closure checklist is executed:

## Mandatory Ticket Completion Checklist

### 1. Local Ticket File Sync
In the ticket markdown file (e.g. `.wayfinder/full-report-map/tickets/<ticket>.md`):
- Change `<!-- status: open -->` to `<!-- status: closed -->`.
- Mark all completed acceptance criteria items as `[x]`.

### 2. Canonical Map Sync
In `.wayfinder/full-report-map/map.md`:
- Mark all acceptance criteria checkboxes for that ticket as `[x]`.
- Change `- **Status**: Open` to `- **Status**: Closed`.
- Update the Mermaid diagram node for this ticket to include `- Closed`.

### 3. GitHub Tracker Sync (via `gh` CLI)
Execute the following GitHub CLI commands:
1. Post completion comment:
   ```bash
   gh issue comment <issue-number> --body "Completed in commit <commit-sha>. Verified with test suite passing."
   ```
2. Close the issue:
   ```bash
   gh issue close <issue-number>
   ```

## Invariants
- An agent must **never** finish a ticket turn without executing all 3 steps.
- If multiple tickets were completed in a batch, all corresponding ticket files, map entries, and GitHub issues must be updated and closed before concluding.
