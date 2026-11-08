"""Interactive CLI module for project workflow and utility actions in Pahang CLI."""

from __future__ import annotations

import logging
import sys
from functools import partial
from typing import Callable, Sequence

from src import cli_menu, run_records
from src.cli_session import CliSession
from src.project.management import select_active_project_wizard
from src.project_workflow_actions import (
    ProjectWorkflowAction,
    get_project_workflow_actions,
)
from src.utility_actions import UtilityAction, get_utility_actions


def run_cli(session: CliSession | None = None) -> None:
    """Run the interactive CLI until the operator exits."""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8", errors="replace")
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
            _run_settings_menu(cli_session)
        else:
            logging.warning("Exiting program...")
            return


def _run_action(action_label: str, callback: Callable[[], object]) -> None:
    """Run one action with centralized generic failure handling."""
    try:
        callback()
    except Exception as exc:
        logging.error("Action '%s' failed: %s", action_label, exc)
        print(f"Action failed: {exc}")


def _run_recorded_action(action_label: str, callback: Callable[[], object], environment: object = None) -> None:
    """Run one action as _run_action does, saving a Run Record of it."""
    with run_records.open_run(action_label, environment) as run:
        try:
            _run_action(action_label, lambda: run.call(callback))
        finally:
            # In a finally so a Ctrl+C after a failed item still shows where the record is.
            if run.failed and run.path:
                print(f"Run Record: {run.path}")


def _select_project(session: CliSession) -> object:
    """Select a project. A failure here has no project, so its Run Record uses the per-user folder."""
    try:
        return select_active_project_wizard(session, on_activation_failure=_record_selection_failure)
    except Exception as exc:
        _record_selection_failure(exc)
        raise


def _record_selection_failure(exc: Exception) -> None:
    record_path = run_records.save_failure("Select Active Project", exc)
    if record_path:
        print(f"Run Record: {record_path}")


def _run_project_workflow_menu(
    session: CliSession,
    project_actions: Sequence[ProjectWorkflowAction],
) -> None:
    """Run the project workflow submenu."""
    if session.active_project is None and _select_project(session) is None:
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
            _run_recorded_action(selection.label, partial(selection.run, environment), environment)
        elif selection is cli_menu.SessionCommand.CHANGE_ACTIVE_PROJECT:
            _select_project(session)
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
            _run_recorded_action(selection.label, selection.run)
        elif selection is cli_menu.SessionCommand.BACK:
            return


def _run_settings_menu(session: CliSession) -> None:
    """Run the settings submenu."""
    from src.settings_actions import (
        run_configure_camera_patterns,
        run_configure_prpd_style,
        run_rollback,
    )

    while True:
        selection = cli_menu.select_settings_action()
        if selection is None:
            return
        if selection == "manage_projects":
            _run_project_management_menu(session)
        elif selection == "rollback":
            _run_action("Rollback Version", run_rollback)
        elif selection == "configure_cameras":
            _run_action("Configure Camera Patterns", run_configure_camera_patterns)
        elif selection == "configure_prpd":
            _run_action("Configure PRPD Graph Style", run_configure_prpd_style)
        elif selection is cli_menu.SessionCommand.BACK:
            return


def _run_project_management_menu(session: CliSession) -> None:
    """Run the project and workspace storage management submenu."""
    from src.project_settings_actions import (
        handle_add_project,
        handle_switch_project,
        handle_unregister_project,
        handle_update_project_path,
        handle_view_project_info,
    )

    while True:
        selection = cli_menu.select_project_management_action()
        if selection is None or selection is cli_menu.SessionCommand.BACK:
            return
        if selection == "view_info":
            _run_action("View Current Project Info", lambda: handle_view_project_info(session))
        elif selection == "switch_project":
            _run_action("Switch Active Project", lambda: handle_switch_project(session))
        elif selection == "add_project":
            _run_action("Add / Register New Project", lambda: handle_add_project(session))
        elif selection == "update_path":
            _run_action("Update Project Directory Path", lambda: handle_update_project_path(session=session))
        elif selection == "unregister_project":
            _run_action("Unregister Project", lambda: handle_unregister_project(session=session))
