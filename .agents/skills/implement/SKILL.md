---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

You will be the orchestrator of the implementation work.

Ask the user for a **fixed point** to diff against later (commit SHA, branch, tag). Default to the current `HEAD` if they don't specify one. Capture this before any implementation work begins.

Spawn subagent (model Gemini 3.6 Flash) to implement the work described by the user in the spec or tickets. Always explicitly tell the subagent which files/folder that the subagent will be working on, the subagent then needs to first check how the current codebase is structured and then continue with the implementation according to the architecture with deep modules and modular approach. Use /tdd where possible, at pre-agreed seams. Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once the implementation subagent reports done, spawn a code-review subagent using /code-review. Pass it the fixed-point captured earlier. Read the review report. If there are findings:

1. Relay the findings to the implementation subagent and ask it to fix the issues. Explicitly tell it to do code cleanup and maintain code hygiene.
2. Once fixes are applied, re-run /code-review with the same fixed point.
3. Repeat until the review passes clean or there is a clear reason to stop.

Once the review is clean, use /smart-commit to commit your work to the current branch.
