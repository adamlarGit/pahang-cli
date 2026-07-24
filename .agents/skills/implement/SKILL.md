---
name: implement
description: "Implement a piece of work based on a spec or set of tickets with shift-left self-verification and strict review bounds."
disable-model-invocation: true
---

You will be the orchestrator of the implementation work.

### 1. Capture Fixed Point
Ask the user for a **fixed point** to diff against later (commit SHA, branch, tag). Default to the current `HEAD` if they don't specify one. Capture this before any implementation work begins.

### 2. Spawn Implementation Subagent (Shift-Left Verification)
Spawn subagent (model Gemini 3.6 Flash) to implement the work described by the user in the spec or tickets. Always explicitly tell the subagent which files/folder it will be working on. The subagent must:
1. Check codebase structure and follow deep module architecture.
2. Use /tdd where possible at pre-agreed seams.
3. **Mandatory Self-Verification Phase** before reporting done:
   - Run full test suite (`pytest`) — 100% pass required.
   - Run type checking / compile check (`py_compile` / `mypy`).
   - Audit all new code for complete type annotations and class/module docstrings.
   - Fix syntax, import, typing, and regex edge-case errors *inside* the subagent context before reporting complete.

### 3. Bounded Code Review (Max 2 Iterations)
Once the implementation subagent reports done:
1. Run `/code-review` against the fixed point. For small/medium diffs (<500 lines), use 1 combined review subagent to minimize token usage.
2. Filter findings into **CRITICAL** (functional bugs, broken tests, spec contract violations) vs **NITPICK** (formatting, subjective code smells like Middle Man or Speculative Generality).
3. If **CRITICAL** findings exist:
   - Relay ONLY the CRITICAL items to the implementation subagent for a single targeted fix.
   - Re-run `/code-review` once after fixes.
4. **Stopping Criteria**:
   - Proceed to `/smart-commit` as soon as **0 CRITICAL findings** remain.
   - **Hard Cap (2 Rounds Max)**: If CRITICAL findings still remain after 2 review iterations, **HALT automated looping**. Synthesize the remaining CRITICAL items and ask the user for explicit guidance (e.g., run 1 final targeted fix round or proceed to commit).

### 4. Smart Commit
Once the review is clean (or approved by the user), use `/smart-commit` to commit your work to the current branch.
