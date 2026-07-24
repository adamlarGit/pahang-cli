"""Interactive CLI module for project workflow and utility actions in Pahang CLI."""

from __future__ import annotations

import logging
import re
import shutil
import sys
from pathlib import Path
from typing import Callable, Sequence

from src import cli_menu, cli_selectors
from src.cli_session import CliSession
from src.project.environment import (
    ProjectEnvironment,
    create_project_environment,
    get_default_project_key,
    get_project_name,
    list_project_keys,
)
from src.project.models import ProjectMetadata
from src.project.repository import JsonFileProjectRepository
from src.project_workflow_actions import (
    ProjectWorkflowAction,
    get_project_workflow_actions,
)
from src.utility_actions import UtilityAction, get_utility_actions


def _initialize_project_workspace(base_path: Path) -> None:
    """Create required directories and seed initial Excel files if missing."""
    import config as cfg
    from src.project.storage import LocalWorkspaceStorage

    storage = LocalWorkspaceStorage(base_path)
    folders = [
        storage.root_path / "PYTHON",
        storage.get_engr_folder(),
        storage.get_testsheet_dir(),
        storage.get_raw_material_dir(),
        storage.get_quick_report_dir(),
        storage.get_whatsapp_dir(),
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    for src_rel, dest_rel in cfg.SEED_FILES.items():
        src_path = cfg.GLOBAL_TEMPLATES_DIR / src_rel
        dest_path = base_path / dest_rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if src_path.exists() and not dest_path.exists():
            try:
                shutil.copy2(src_path, dest_path)
            except Exception as exc:
                logging.warning("Could not copy seed file %s: %s", src_rel, exc)


def _add_new_project_wizard() -> ProjectMetadata | None:
    """Guide user through registering a new Pahang project."""
    print("\n  ➕ ADD NEW PAHANG PROJECT")
    print("  -------------------------")

    try:
        raw_name = input("  Project Name (e.g. Pahang Kuantan): ").strip()
        if not raw_name:
            print("  Project name cannot be empty.")
            return None

        po_number = input("  PO Number (e.g. 42239999): ").strip()

        voltage_options = [
            cli_selectors.SelectOption("11kV", "11kV"),
            cli_selectors.SelectOption("33kV", "33kV"),
        ]
        voltage_type = cli_selectors.select_one("  Select Voltage Rating", voltage_options, default_value="11kV")
        if not voltage_type:
            voltage_type = "11kV"

        year = input("  Inspection Year [2026]: ").strip() or "2026"
        cycle = input("  Inspection Cycle [Cycle 1]: ").strip() or "Cycle 1"

        raw_path = input("  Project Workspace Root Directory Path: ").strip().strip('"')
        if not raw_path:
            print("  Project path cannot be empty.")
            return None

        base_path = Path(raw_path)
        base_path.mkdir(parents=True, exist_ok=True)
        _initialize_project_workspace(base_path)

        # Generate unique key from name, year, cycle
        slug_base = re.sub(r"[^a-z0-9]+", "_", raw_name.lower()).strip("_")
        key = f"{slug_base}_{year}_{re.sub(r'[^a-z0-9]+', '', cycle.lower())}"

        metadata = ProjectMetadata(
            key=key,
            name=f"{raw_name} ({year} - {cycle})",
            po_number=po_number,
            state="pahang",
            voltage_type=voltage_type,
            year=year,
            cycle=cycle,
            technologies=("IR", "US", "TEV"),
            base_path=str(base_path),
        )

        repo = JsonFileProjectRepository()
        repo.save(metadata)
        print(f"  ✓ Project '{metadata.name}' created and saved successfully.\n")
        return metadata

    except KeyboardInterrupt:
        print("\n  Project creation cancelled.")
        return None


def _first_run_setup(project_key: str) -> bool:
    """Ensure base_path exists and folder structure is initialized."""
    repo = JsonFileProjectRepository()
    try:
        meta = repo.get(project_key)
    except KeyError:
        return False

    base_path = Path(meta.base_path) if meta.base_path else None
    if base_path and base_path.exists() and (base_path / "PYTHON").exists():
        _initialize_project_workspace(base_path)
        return True

    print(f"\n  Project setup required for: {meta.name}")
    print(f"  Please enter the path to your project root folder.\n")

    try:
        raw_path = input("  Project path: ").strip().strip('"')
    except KeyboardInterrupt:
        return False

    if not raw_path:
        print("  Path cannot be empty.")
        return False

    path = Path(raw_path)
    path.mkdir(parents=True, exist_ok=True)

    _initialize_project_workspace(path)

    updated_meta = ProjectMetadata(
        key=meta.key,
        name=meta.name,
        po_number=meta.po_number,
        state=meta.state,
        voltage_type=meta.voltage_type,
        year=meta.year,
        cycle=meta.cycle,
        technologies=meta.technologies,
        base_path=str(path),
    )
    repo.save(updated_meta)
    print(f"  ✓ Project path saved and folder structure initialized.\n")
    return True


def run_cli(session: CliSession | None = None) -> None:
    """Run the interactive CLI until the operator exits."""
    if sys.platform == "win32":
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    from src import __version__

    print("\n" + "=" * 55)
    print(f"  ⚡ PAHANG AUTOMATION CLI  —  Version {__version__}")
    print("=" * 55)

    if any(arg in sys.argv for arg in ("-h", "--help")):
        print("\nUsage: pahang-cli [OPTIONS]")
        print("\nPahang Area 300 PE IR US TEV - Interactive CLI for PE inspection workflows\n")
        print("Options:")
        print("  -h, --help     Show this help message and exit")
        print("  -v, --version  Show version number and exit\n")
        return
    if any(arg in sys.argv for arg in ("-v", "--version")):
        return

    cli_session = session or CliSession()
    project_actions = get_project_workflow_actions()
    utility_actions = get_utility_actions()

    while True:
        try:
            selection = cli_menu.select_top_level_destination()
        except Exception as exc:
            if "NoConsoleScreenBufferError" in type(exc).__name__ or "No Windows console found" in str(exc):
                print("\n❌ Error: No interactive Windows console found.")
                print("Please run `pahang-cli` directly inside an interactive PowerShell or Command Prompt (cmd.exe) window.\n")
                return
            raise
        if selection is None or selection is cli_menu.TopLevelSelection.EXIT:
            logging.warning("Exiting program...")
            return
        if selection is cli_menu.TopLevelSelection.PROJECT_WORKFLOW:
            _run_project_workflow_menu(cli_session, project_actions)
        elif selection is cli_menu.TopLevelSelection.UTILITY_ACTION:
            _run_utility_actions_menu(utility_actions)
        elif selection is cli_menu.TopLevelSelection.SETTINGS:
            _run_settings_menu()
        else:
            logging.warning("Exiting program...")
            return


def _prompt_for_project_key(last_project_key: str | None, allow_cancel: bool = True) -> str | None:
    """Prompt the operator to choose an active project or add a new one."""
    project_keys = list_project_keys()
    default_key = get_default_project_key(last_project_key)

    options = [
        cli_selectors.SelectOption(
            (
                f"{get_project_name(project_key)} ({project_key})"
                + (" [Last used]" if project_key == last_project_key else "")
            ),
            project_key,
        )
        for project_key in project_keys
    ]

    options.append(cli_selectors.SelectOption("+ Add New Project", "__add_new__"))
    if allow_cancel:
        options.append(cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"))

    selection = cli_selectors.select_one(
        "PROJECT SELECTION",
        options,
        default_value=default_key,
    )
    if selection in (None, "__cancel__"):
        return None

    if selection == "__add_new__":
        new_meta = _add_new_project_wizard()
        if new_meta is None:
            return None
        return new_meta.key

    return selection


def _select_active_project(
    session: CliSession,
    allow_cancel: bool = True,
) -> ProjectEnvironment | None:
    """Select and activate a project for the current CLI session."""
    last_project_key = (
        session.active_project.project_key
        if session.active_project is not None
        else session.load_last_project_key()
    )

    while True:
        project_key = _prompt_for_project_key(last_project_key, allow_cancel=allow_cancel)
        if project_key is None:
            return None

        if not _first_run_setup(project_key):
            continue

        try:
            environment = create_project_environment(project_key)
        except Exception as exc:
            print(f"Project activation failed: {exc}")
            last_project_key = project_key
            continue

        session.activate_project(environment)
        print(f"Active project set to: {environment.project_data['name']}")
        return environment


def _run_action(action_label: str, callback: Callable[[], object]) -> None:
    """Run one action with centralized generic failure handling."""
    try:
        callback()
    except Exception as exc:
        logging.error("Action '%s' failed: %s", action_label, exc)
        print(f"Action failed: {exc}")


def _run_project_workflow_menu(
    session: CliSession,
    project_actions: Sequence[ProjectWorkflowAction],
) -> None:
    """Run the project workflow submenu."""
    if session.active_project is None and _select_active_project(session) is None:
        return

    while True:
        environment = session.active_project
        if environment is None:
            return

        selection = cli_menu.select_project_workflow_action(
            project_actions,
            active_project_name=environment.project_data["name"],
        )
        if selection is None:
            return
        if isinstance(selection, ProjectWorkflowAction):
            _run_action(selection.label, lambda: selection.run(environment))
        elif selection is cli_menu.SessionCommand.CHANGE_ACTIVE_PROJECT:
            _select_active_project(session)
        elif selection is cli_menu.SessionCommand.BACK:
            return


def _run_utility_actions_menu(
    utility_actions: Sequence[UtilityAction],
) -> None:
    """Run the utility actions submenu."""
    while True:
        selection = cli_menu.select_utility_action(utility_actions)
        if selection is None:
            return
        if isinstance(selection, UtilityAction):
            _run_action(selection.label, selection.run)
        elif selection is cli_menu.SessionCommand.BACK:
            return


def _run_settings_menu() -> None:
    """Run the settings submenu."""
    from src.settings_actions import run_rollback

    while True:
        selection = cli_menu.select_settings_action()
        if selection is None:
            return
        if selection == "rollback":
            _run_action("Rollback Version", run_rollback)
        elif selection is cli_menu.SessionCommand.BACK:
            return
