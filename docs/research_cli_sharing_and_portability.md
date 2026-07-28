# Research Report: CLI Portability, Onboarding & Continuous Update Architecture

## Executive Summary
This document investigates the end-to-end user experience for non-developer colleagues running the **Pahang CLI** via `start_cli.bat`. 

The primary objective is to guarantee a **zero-friction, fail-safe environment** where:
1. First-time non-developer colleagues can clone/download and launch the CLI without pre-configured environment errors.
2. Ongoing colleagues can update seamlessly via `start_cli.bat` whenever new code or dependencies are pushed to GitHub.
3. Local laptop settings (`base_path`, `.cli_config.json`, active projects) remain strictly local and isolated without breaking Git updates.

---

## Key Findings & Primary Source Analysis

### 1. First-Time User Onboarding & Dependency Verification
* **Source:** `start_cli.bat`
* **Finding:** The launcher script currently assumes `git` and `uv` are pre-installed and available on system `%PATH%`.
  * If `git` is missing, `git rev-list` fails and leaves `!BEHIND!` uninitialized, leading to a raw Batch syntax error (`if !BEHIND! GTR 0` fails with `Missing operand`).
  * If `uv` is missing, `uv run` fails with an obscure `'uv' is not recognized as an internal or external command`.
* **Recommendation:** Add explicit pre-flight environment checks (`where git` and `where uv`) at the top of `start_cli.bat` with clear, user-friendly instructions on how to install them before continuing.

### 2. Local Settings & State File Isolation
* **Source:** `.gitignore` and `.processed_folders.json`
* **Finding:**
  * `.cli_config.json` and `.active_project.json` are properly ignored in `.gitignore`. On first launch, `_first_run_setup()` in `src/workflow_cli.py` interactively prompts the user for their local project directory and seeds default template folders gracefully.
  * **CRITICAL BLOCKER:** `.processed_folders.json` is currently **tracked in Git**. Whenever a colleague runs `populate_total_pe_workflow`, this file is modified locally with processed timestamps. When they later run `start_cli.bat` and attempt to update, `git pull origin main` **fails with a local uncommitted changes error**.
* **Recommendation:** Remove `.processed_folders.json` from Git tracking (`git rm --cached .processed_folders.json`) and add it to `.gitignore`.

### 3. Continuous Update Resilience
* **Source:** `start_cli.bat`
* **Finding:** Using `uv sync --frozen` and `uv run --frozen` (recently added) successfully prevents `uv` from mutating `uv.lock` at runtime. However, if a colleague accidentally modifies or creates an un-ignored local file, standard `git pull` will still fail.
* **Recommendation:** Enhance update logic in `start_cli.bat` to default `BEHIND=0` safely, handling offline network states gracefully without syntax errors.

---

## Action Plan Overview

1. **Fix Git Tracking Leak**: Untrack `.processed_folders.json` and ignore it in `.gitignore`.
2. **Add Pre-Flight Checks in `start_cli.bat`**: Check for `git` and `uv` availability, printing human-readable installation hints if missing.
3. **Bulletproof Update Parsing in `start_cli.bat`**: Initialize `set BEHIND=0` to prevent batch evaluation errors during offline use or Git failures.
