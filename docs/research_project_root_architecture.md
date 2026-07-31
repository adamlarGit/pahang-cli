# Project Root Architecture Audit Findings

## Executive Summary
This audit evaluated `pahang-cli` against **Project Root Architecture** principles and strict project-level template isolation. 

The core requirement is that `pahang-cli` must execute deterministically regardless of the current working directory (`Path.cwd()`), and every project must resolve source files, data workbooks (`PYTHON/`, `TESTSHEET/`, `RAW MATERIAL/`, `QUICK REPORT/`, `WHATSAPP/`), and template files strictly from its own configured `base_path`. Global CLI template fallbacks must be replaced with strict validation and loud error reporting when required project-level templates are missing.

---

## 1. Current Working Directory (`Path.cwd()`, `os.getcwd()`) Violations

### 1.1 `src/quick_report/defects.py`
- **Location:** Line 69
- **Snippet:**
  ```python
  def __init__(self, engr_dir: Path | str | None = None) -> None:
      if engr_dir:
          self.engr_dir = Path(engr_dir)
      else:
          self.engr_dir = Path.cwd() / "PYTHON" / "ENGR FROM DRIVE"
  ```
- **Violation:** If `engr_dir` is not explicitly passed, it defaults to `Path.cwd() / "PYTHON" / "ENGR FROM DRIVE"`. When running `pahang-cli` from outside the project directory, this searches for engineering files in the current shell directory instead of `<base_path>/PYTHON/ENGR FROM DRIVE`.

### 1.2 `src/remove_desktop_ini_workflow.py`
- **Location:** Line 57
- **Snippet:**
  ```python
  def run_remove_desktop_ini() -> int:
      """Interactive entrypoint for removing desktop.ini files."""
      default_path = Path.cwd()
  ```
- **Violation:** Defaults to the process's working directory (`Path.cwd()`) when prompting the user for directory cleaning, rather than anchoring default choices to the active project workspace (`env.storage.root_path`).

---

## 2. Template Path Resolution & Global Fallbacks

### 2.1 `src/project/storage.py` (`_initialize_project_workspace` & `get_template`)
- **Location:** Lines 167-171, 275-290
- **Snippet:**
  ```python
  def get_template(self, key: str) -> Path:
      if key not in config.TEMPLATES:
          raise KeyError(f"Unknown template key: {key}")
      return self._templates_dir / config.TEMPLATES[key]
  ```
  ```python
  # Copy TEMPLATES
  for key, relative_path in config.TEMPLATES.items():
      global_path = config.GLOBAL_TEMPLATES_DIR / relative_path
      local_path = self._templates_dir / relative_path

      if global_path.exists() and not local_path.exists():
          _safe_copy(global_path, local_path)
  ```
- **Violation:** 
  1. `WorkspaceStorage` bootstrap automatically copies missing templates from `config.GLOBAL_TEMPLATES_DIR` (the CLI installation's templates directory) to the workspace root.
  2. Under the updated mandate, templates **must originate from and exist inside the project root**. Silent auto-copying or falling back to global CLI installation paths masks missing template files.
  3. Instead of falling back to CLI defaults, `resolve_template_path(key)` must verify that the template exists within `<base_path>/templates/` (or specified project template path) and raise a **loud `FileNotFoundError`** with actionable instructions if missing.

### 2.2 `config.py`
- **Location:** Line 26
- **Snippet:** `GLOBAL_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"`
- **Violation:** Hardcodes global template location tied to `config.py` location (CLI package root). Projects should rely on their own template directory structure without global dependency.

---

## 3. Hardcoded or Unanchored Path Strings

### 3.1 `config.py`
- **Location:** Lines 56-59, 80
- **Snippet:**
  ```python
  SEED_FILES: dict[str, str] = {
      r"DATA MSMS.xlsx": r"PYTHON\DATA MSMS.xlsx",
      r"TOTAL PE.xlsx": r"PYTHON\TOTAL PE.xlsx",
  }
  ENGR_FILE_PATTERN: str = r"PYTHON\ENGR FROM DRIVE\ENGR-*.xlsx"
  ```
- **Violation:** Hardcoded strings with relative paths bypass the single source of truth (`WorkspaceStorage` methods like `get_python_dir()` and `get_engr_folder()`).

---

## 4. Disconnected Utility & Standalone Actions

### 4.1 `src/utility_actions.py`
- **Location:** Lines 11, 38, 115, 130
- **Snippet:**
  ```python
  class UtilityAction:
      """One standalone action that does not consume the active project."""
  ```
- **Violation:** Utility actions bypass the active `ProjectEnvironment` and instantiate floating/dummy environments or prompt for manual path entries. All CLI actions should execute within the injected `ProjectEnvironment` context.

### 4.2 `src/remove_desktop_ini_workflow.py`
- **Location:** Line 55
- **Snippet:** `def run_remove_desktop_ini() -> int:`
- **Violation:** Invoked without `ProjectEnvironment`, defaulting to interactive path input and `Path.cwd()`.

---

## Recommended Refactoring Plan

1. **Strict Project Template Resolution (`WorkspaceStorage`)**:
   - Update `LocalWorkspaceStorage.resolve_template_path(key)` to look *only* inside `<base_path>/templates/<relative_path>`.
   - If missing, raise a loud `FileNotFoundError(f"Missing required template '{key}' at '{local_path}'. Every project must provide its own templates in its project root directory.")`.
   - Remove automatic copying from `GLOBAL_TEMPLATES_DIR` during workspace initialization.

2. **Eliminate `Path.cwd()` Dependencies**:
   - Pass `ProjectEnvironment` / `WorkspaceStorage` into `CbaDefectProcessor` in `src/quick_report/defects.py` to resolve `engr_dir` via `env.storage.get_engr_folder()`.
   - Update `src/remove_desktop_ini_workflow.py` to accept `ProjectEnvironment` and default to `env.storage.root_path`.

3. **Centralize All Workspace Path Resolution**:
   - Ensure all seed files and engineering file patterns are resolved strictly via `WorkspaceStorage` methods anchored to `self.root_path`.

4. **Inject `ProjectEnvironment` to Utility Actions**:
   - Update `UtilityAction` and its menu handlers to consume the active `ProjectEnvironment`.
