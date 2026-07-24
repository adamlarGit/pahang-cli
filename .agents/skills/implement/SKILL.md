---
name: implement
description: "Implement a piece of work based on a spec or set of tickets with diff-size gating, bounded self-verification, and strict review bounds."
disable-model-invocation: true
---

You will be the orchestrator of the implementation work.

### 1. Capture Fixed Point & Scope Assessment

Before any implementation:

1. Ask the user for a **fixed point** to diff against later (commit SHA, branch, tag). Default to the current `HEAD` if they don't specify one.
2. **Scope the work** — determine:
   - The exact files/folders to read (max 5 reference files)
   - A template file to follow (an existing file in the same module pattern)
   - The spec/ticket file path (so downstream skills don't waste tokens searching)
   - The seams that need tests (so the subagent doesn't need to ask the user)
3. **Estimate diff size category** based on the spec scope:
   - **Micro (<50 lines expected):** Go to Step 2a
   - **Small/Medium (50–500 lines expected):** Go to Step 2b
   - **Large (500+ lines expected):** Go to Step 2b with parallel review subagents

### 2a. Micro Change Path (No Subagent)

For changes estimated under 50 lines (docstring fixes, config tweaks, single-function additions):

1. Implement the change directly as the orchestrator — no subagent spawn needed.
2. Run `py_compile` / type check only (skip full pytest unless the change touches test-adjacent code).
3. Proceed directly to **Step 4** with lightweight commit mode.

### 2b. Spawn Implementation Subagent (Shift-Left Verification)

Spawn subagent (model: **Gemini 3.6 Flash**) to implement the work described by the user in the spec or tickets. Provide the subagent with:
- **Exact file list** to read (the max 5 reference files from Step 1)
- **Template file** to follow for module structure
- **Pre-determined seams** for testing (from Step 1 — the subagent does NOT ask the user to confirm seams)
- **Spec file path** (the exact path — no searching `.issues/`, `docs/`, or temp dirs)

The subagent must:
1. Read ONLY the provided reference files — do NOT explore the codebase beyond this scope.
2. Follow the template file's module pattern (deep module architecture).
3. Use /tdd at the **pre-determined seams** provided by the orchestrator.
4. **Mandatory Self-Verification Phase (max 3 iterations)** before reporting done:
   - Run full test suite (`pytest`) — 100% pass required.
   - Run type checking / compile check (`py_compile` / `mypy`).
   - Audit all new code for complete type annotations and class/module docstrings.
   - Fix syntax, import, typing, and regex edge-case errors *inside* the subagent context.
   - **If still failing after 3 self-verification iterations, STOP.** Report back to the orchestrator with the failure summary. Do not keep looping.

### 3. Bounded Code Review (Max 2 Iterations)

Once the implementation subagent reports done:

1. Run `/code-review` against the fixed point. Pass the **spec file path** directly to the review skill (skip spec discovery). For small/medium diffs (<500 lines), use 1 combined review subagent.
2. Filter findings into **CRITICAL** (functional bugs, broken tests, spec contract violations) vs **NITPICK** (formatting, subjective code smells like Middle Man or Speculative Generality).
3. If **CRITICAL** findings exist:
   - Relay ONLY the CRITICAL items to the implementation subagent for a single targeted fix.
   - Re-run `/code-review` once after fixes — but as a **targeted re-review**: pass only the CRITICAL items from round 1 and the specific files that were modified, not the full diff.
4. **Stopping Criteria**:
   - Proceed to **Step 4** as soon as **0 CRITICAL findings** remain.
   - **Hard Cap (2 Rounds Max)**: If CRITICAL findings still remain after 2 review iterations, **HALT automated looping**. Synthesize the remaining CRITICAL items and ask the user for explicit guidance (e.g., run 1 final targeted fix round or proceed to commit).

### 4. Commit

Once the review is clean (or approved by the user):

- **Default (lightweight):** Use `/caveman-commit` to commit changes to the current branch. This is the standard path for work-in-progress implementations.
- **Release mode (user opt-in):** If the user explicitly requests a release or says "smart-commit", use `/smart-commit` for the full release ceremony (README sync, CHANGELOG, SemVer bump, tag, push).

Ask the user: "Commit with caveman-commit, or full smart-commit release?" Default to caveman-commit if the user doesn't specify.
