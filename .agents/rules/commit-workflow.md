---
description: Auto-triggers whenever the user asks to commit, push, or release code. Enforces the smart-commit workflow.
---

# Automated Release & Commit Workflow Rule

Whenever the user requests to commit, push, or release code (`git commit`, `/caveman-commit`, `/commit`, "push to github", "let's commit", etc.), the agent **MUST NOT** run `git commit` immediately.

Instead, the agent **MUST** invoke the **`smart-commit`** skill (`.agents/skills/smart-commit/SKILL.md`) and strictly follow its 4-phase checklist:

1. **In-Place `README.md` & `CHANGELOG.md` Sync**:
   - Inspect all diffs (`git diff`).
   - Update `README.md` *in-place* (`replace_file_content`): remove deprecated behaviors, update modified workflows, and **never append** new text to the bottom. Keep `README.md` lean and push complex implementation details to `docs/workflows/*.md`.
   - Add concise bullets to `CHANGELOG.md` (`Added`, `Changed`, `Fixed`).
2. **SemVer Evaluation & Version Bump**:
   - Determine whether the changes warrant a `MAJOR`, `MINOR`, or `PATCH` bump according to SemVer 2.0.0.
   - Update `version = "..."` in `pyproject.toml` and `__version__ = "..."` in `src/__init__.py`.
   - Run `uv lock` to sync `uv.lock`.
3. **Caveman Commit Formatting**:
   - Generate a terse, exact Conventional Commits subject/body (`why over what`) following `.agents/skills/caveman-commit/SKILL.md`.
4. **Stage, Commit & Push**:
   - Verify zero syntax errors (`python -m py_compile src/*.py`).
   - Run `git add -A; git commit -m "..."; git push`.
