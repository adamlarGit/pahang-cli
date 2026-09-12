---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

Commit your work to the current branch.

### Ticket Completion
After committing, you MUST close the ticket following `.agents/rules/ticket-lifecycle.md`:
1. Mark acceptance criteria `[x]` and `status: closed` in the local ticket file.
2. Mark acceptance criteria `[x]` and `Status: Closed` in `map.md`.
3. Close the GitHub issue via `gh issue close <id> --comment "..."`.
