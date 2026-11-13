---
description: GitHub-only completion workflow for implementation and Wayfinder decision tickets.
---

# Ticket completion

GitHub Issues is the source of truth for tickets and Wayfinder maps. Local `.wayfinder` files are historical; ticket work does not create or synchronize local ticket files or map mirrors.

When a ticket's acceptance criteria or decision question are satisfied:

1. Post a completion or resolution comment with the outcome, relevant evidence, validation results and remaining limitations. Include a commit only if one exists. Use `gh issue comment <number> --body-file <file>` for multiline text. A research or prototype ticket uses the fixed comment form in `docs/agents/research-and-prototypes.md`, and its detailed answer lives in the Ticket Folder.
2. Close the issue with `gh issue close <number>`.
3. For a Wayfinder child, re-read the parent map issue and append a linked, one-line gist to its Decisions so far. Preserve concurrent edits; keep the detailed answer in the child's resolution comment, or in its Ticket Folder for a research or prototype ticket. Follow `docs/agents/issue-tracker.md` for tracker operations.
4. Verify the issue is closed and the parent pointer is present before reporting completion.

Apply these steps to every ticket resolved in the session. An unresolved ticket stays open with its remaining work or blocker recorded on GitHub.
