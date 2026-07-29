---
name: smart-commit
description: Automated pre-commit release check that updates README.md in-place, evaluates SemVer (MAJOR/MINOR/PATCH), bumps versions, logs CHANGELOG.md, and commits via caveman-commit format.
---

# Smart Commit (`smart-commit`) — Automated Release & Documentation Sync

This skill enforces strict pre-commit discipline before staging and committing changes to version control. Whenever triggered (`/smart-commit`, "commit and push", "release changes", or invoked alongside `/caveman-commit`), the agent **MUST** execute the following 4-phase workflow sequentially:

---

## Phase 1: In-Place Documentation Sync (`README.md` & `CHANGELOG.md`)

Before generating any commit message or running `git commit`, inspect `git status` and `git diff` across all modified source files (`src/*.py`, `config.py`, `templates/`, etc.).

### 1. `README.md` (In-Place Update — NO APPENDING)
- **Rule:** The `README.md` must accurately reflect the *current* state of the codebase.
- **Action:**
  - If a feature or workflow was modified, find its existing description in `README.md` and **update it in-place**.
  - If an old utility or command option was removed, **delete its entry**.
  - **NEVER append** new paragraphs to the bottom of `README.md` or duplicate sections. Keep the file lean (~120–150 lines).
  - If a change introduces complex multi-page mechanics (e.g., COM printer registry keys or exact cell coordinates), document those inside `docs/` (`docs/workflows/*.md`) and keep `README.md` focused on high-level usage.

### 2. `CHANGELOG.md`
- **Rule:** Every code modification must be recorded under [Keep a Changelog](https://keepachangelog.com/) format.
- **Audit Intermediate Commits:** Run `git log <last-version-tag>..HEAD --oneline` (or inspect all small `caveman-commit` history since the last version tag/release). Ensure **ALL** intermediate feature, fix, refactor, and chore commits are aggregated and categorized.
- **Action:** Add concise bullets under the `## [Unreleased]` header (or under the new SemVer version block being prepared in Phase 2) categorized by `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, or `Security`.

---

## Phase 2: SemVer Evaluation & Automatic Version Bump

Evaluate the staged/unstaged changes against **[Semantic Versioning 2.0.0](https://semver.org/)** criteria:

| Severity | Criteria | Example Bump |
| :--- | :--- | :--- |
| **`MAJOR`** | Breaking changes, incompatible API/CLI option removals, or complete architectural overhaul | `1.2.1` → **`2.0.0`** |
| **`MINOR`** | New backwards-compatible features, workflows, interactive menu options, or significant module refactoring | `1.2.1` → **`1.3.0`** |
| **`PATCH`** | Backwards-compatible bug fixes, performance improvements, or documentation/style corrections | `1.2.1` → **`1.2.2`** |

### Actions:
1. Inspect `pyproject.toml` (`version = "..."`) and `src/__init__.py` (`__version__ = "..."`).
2. Update **both files** to the newly calculated version string (`MAJOR.MINOR.PATCH`).
3. Run `uv lock` in the terminal to ensure `uv.lock` is synchronized with the new version.

---

## Phase 3: Terse Commit Message Generation (`caveman-commit`)

Invoke the rules of **`caveman-commit`** (`.agents/skills/caveman-commit/SKILL.md`):
- **Subject Line:** `<type>(<scope>): <imperative summary>` (≤50 chars preferred, max 72). No trailing period.
  - Types: `feat`, `fix`, `refactor`, `docs`, `chore`, `perf`, `build`
- **Body:** Add only when non-obvious *why*, breaking changes, or migration notes exist. Bullets `-` wrapped at 72 chars.
- **No Fluff:** Never use "This commit does X", "I", "we", "now", "currently", or AI attributions unless requested.

---

## Phase 4: Stage, Commit & Push

Once Phases 1–3 are complete and all files (`README.md`, `CHANGELOG.md`, `docs/*.md`, `pyproject.toml`, `src/__init__.py`, `uv.lock`, and code changes) are verified:
1. Run `python -m py_compile src/*.py` (or powershell equivalent on Windows) to verify zero syntax errors.
2. Stage all changes: `git add -A`
3. Commit using the generated caveman message: `git commit -m "<subject>" -m "<body>"`
4. Create a lightweight git tag for the new version: `git tag vX.Y.Z` (e.g. `git tag v2.8.0`)
5. Push to remote repository, including tags: `git push && git push --tags` (or sequential powershell equivalents)
6. Report the new SemVer release (`vX.Y.Z`) and commit hash to the user.
