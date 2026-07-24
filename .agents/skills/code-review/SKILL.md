---
name: code-review
description: Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes — Standards (does the code follow this repo's documented coding standards?) and Spec (does the code match what the originating issue/PRD asked for?). Runs reviews in parallel sub-agents or single combined mode and reports findings with severity tags.
---

Two-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / PRD / spec?

---

## Process

### 1. Pin the fixed point & Evaluate Diff Size

Capture the diff command: `git diff <fixed-point>...HEAD` (or `git add -N . ; git diff <fixed-point>`).
Check the total diff line count:
- **Small/Medium Diffs (<500 lines changed)**: Default to **1 combined subagent** for both Standards & Spec to minimize token consumption and context latency.
- **Large Diffs (≥500 lines changed)**: Spawn **2 parallel subagents** (Standards subagent & Spec subagent).

Before going further, confirm the fixed point resolves (`git rev-parse <fixed-point>`) and the diff is non-empty.

### 2. Identify Spec & Standards Sources

1. **Spec Sources**:
   - Issue/ticket references passed in the prompt or under `.issues/`, `docs/`, or `C:\Users\ADAM\AppData\Local\Temp\*handoff*.md`.
2. **Standards Sources**:
   - Project standards (`CODING_STANDARDS.md`, `CONTRIBUTING.md`) and Fowler baseline code smells.

### 3. Severity Categorization Rule

Every finding in the review report **MUST** be prefixed with a severity tag:

- **`[CRITICAL]`**: Functional bugs, failing unit tests, type/compile errors, or broken spec requirements. **(BLOCKING for merge / triggers fix round)**.
- **`[MAJOR]`**: Missing edge-case handling or missing documentation for new public interfaces.
- **`[NITPICK]`**: Formatting, minor style notes, or subjective code smells (`Middle Man`, `Duplicated Code` in stubs, `Speculative Generality`). **(NON-BLOCKING for merge)**.

### 4. Subagent Prompt Requirements

Prompt the review subagent(s) with:

- The exact diff command and commit list.
- The path to the spec file(s) and standard baseline. **If the caller provides exact spec file paths, use those directly — do NOT search `.issues/`, `docs/`, or temp directories.**
- **The Brief**:
  - Classify every finding explicitly as `[CRITICAL]`, `[MAJOR]`, or `[NITPICK]`.
  - Scope the Spec review strictly to the requested feature/tickets, ignoring unmentioned scaffold stubs.
  - Keep report under 400 words.

### 5. Targeted Re-Review Mode

When invoked as a **round 2 re-review** (the caller indicates this is a follow-up review after fixes):

1. **Scope to changed files only.** Do NOT re-read the full diff from the fixed point. Instead, review only the files that were modified during the fix round.
2. **Re-check only the original CRITICAL items** from round 1 (provided by the caller). Verify each was addressed.
3. **Do NOT raise new NITPICK findings** on unchanged code. Only flag new CRITICALs if the fix introduced a regression.
4. Keep the re-review report under 200 words.

### 6. Aggregate & Summary

Present findings under `## Standards` and `## Spec` headings.

End with a summary line:
- `Total CRITICAL (Blocking): X`
- `Total NITPICK (Non-Blocking): Y`

If `Total CRITICAL == 0`, the review is declared **PASS (Clean)**.
