---
description: Auto-triggers whenever the user asks to commit, push, or release code. Runs the release workflow on main and a plain commit on every other branch.
---

# Commit workflow

The branch decides the workflow. `docs/agents/factory.md` says only the merge of the Integration Branch into `main` gets a version bump and a CHANGELOG entry. This rule applies that.

## On `main`: release

A commit on `main`, or the merge of the Integration Branch into `main`, is a release. Invoke the **`smart-commit`** skill (`.agents/skills/smart-commit/SKILL.md`) and follow its four phases in order:

1. Sync `README.md` in place and add `CHANGELOG.md` bullets.
2. Evaluate SemVer, bump `pyproject.toml` and `src/__init__.py`, and run `uv lock`.
3. Write the message in `caveman-commit` format.
4. Check syntax, stage, commit, tag and push.

## On every other branch: plain commit

The Integration Branch, ticket branches, and research or prototype branches take a plain commit:

1. Write the message in `caveman-commit` format (`.agents/skills/caveman-commit/SKILL.md`).
2. If any `src/*.py` file changed, run `python -m py_compile` on the changed files.
3. Stage the files that belong to the change, then commit.
4. Push when the user asks, or when `docs/agents/research-and-prototypes.md` says to land.

The version and `CHANGELOG.md` stay as they are on these branches. The release on `main` collects every commit since the last version tag.
