"""Interactive CLI menu definitions and selection helpers for Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Generic, Sequence, TypeVar

from src import __version__, cli_selectors

if TYPE_CHECKING:
    from src.project_workflow_actions import ProjectWorkflowAction
    from src.utility_actions import UtilityAction

T = TypeVar("T")


class SessionCommand(Enum):
    """CLI-owned navigation commands."""

    CHANGE_ACTIVE_PROJECT = "change_active_project"
    ADD_NEW_PROJECT = "add_new_project"
    BACK = "back"
    EXIT = "exit"


class TopLevelSelection(Enum):
    """Top-level CLI destinations."""

    PROJECT_WORKFLOW = "project_workflow"
    UTILITY_ACTION = "utility_action"
    SETTINGS = "settings"
    EXIT = "exit"


@dataclass(frozen=True)
class MenuItem(Generic[T]):
    """One operator-facing menu item with a semantic selection value."""

    label: str
    value: T


def select_menu(
    title: str,
    items: Sequence[MenuItem[T]],
    *,
    active_project_name: str | None = None,
    default_value: T | None = None,
) -> T | None:
    """Render one menu and return the selected semantic value."""
    message_lines = [title]
    if active_project_name is not None:
        message_lines.append(f"Active Project: {active_project_name}")

    options = [
        cli_selectors.SelectOption(item.label, item.value)
        for item in items
    ]
    return cli_selectors.select_one(
        "\n".join(message_lines),
        options,
        default_value=default_value,
    )


def select_top_level_destination() -> TopLevelSelection | None:
    """Return the top-level CLI destination chosen by the operator."""
    items = [
        MenuItem("Project Workflow", TopLevelSelection.PROJECT_WORKFLOW),
        MenuItem("Utility Actions", TopLevelSelection.UTILITY_ACTION),
        MenuItem("Settings", TopLevelSelection.SETTINGS),
        MenuItem("Exit", TopLevelSelection.EXIT),
    ]
    return select_menu(
        f"MAIN MENU - Pahang CLI (v{__version__})",
        items,
        default_value=TopLevelSelection.PROJECT_WORKFLOW,
    )


def select_project_workflow_action(
    actions: Sequence["ProjectWorkflowAction"],
    *,
    active_project_name: str,
) -> "ProjectWorkflowAction | SessionCommand | None":
    """Return one project workflow action or session command."""
    items = [
        *(MenuItem(action.label, action) for action in actions),
        MenuItem("Change Active Project", SessionCommand.CHANGE_ACTIVE_PROJECT),
        MenuItem("Back", SessionCommand.BACK),
    ]
    default_value = items[0].value if items else SessionCommand.CHANGE_ACTIVE_PROJECT
    return select_menu(
        f"PROJECT WORKFLOW (v{__version__})",
        items,
        active_project_name=active_project_name,
        default_value=default_value,
    )


def select_utility_action(
    actions: Sequence["UtilityAction"],
) -> "UtilityAction | SessionCommand | None":
    """Return one utility action or a navigation command."""
    items = [
        *(MenuItem(action.label, action) for action in actions),
        MenuItem("Back", SessionCommand.BACK),
    ]
    default_value = items[0].value if items else SessionCommand.BACK
    return select_menu(
        f"UTILITY ACTIONS (v{__version__})",
        items,
        default_value=default_value,
    )


def select_settings_action() -> str | SessionCommand | None:
    """Return a settings action or a navigation command."""
    items = [
        MenuItem("📁 Manage Projects & Workspace Storage", "manage_projects"),
        MenuItem("Configure Camera Patterns", "configure_cameras"),
        MenuItem("Configure PRPD Graph Style", "configure_prpd"),
        MenuItem("Rollback Version", "rollback"),
        MenuItem("Back", SessionCommand.BACK),
    ]
    return select_menu(
        f"SETTINGS (v{__version__})",
        items,
        default_value="manage_projects",
    )


def select_project_management_action() -> str | SessionCommand | None:
    """Return a project management action or a navigation command."""
    items = [
        MenuItem("1. View Current Project Info & Folder Status", "view_info"),
        MenuItem("2. Switch Active Project", "switch_project"),
        MenuItem("3. Add / Register New Project", "add_project"),
        MenuItem("4. Update Project Directory Path", "update_path"),
        MenuItem("5. Unregister Project", "unregister_project"),
        MenuItem("Back to Settings Menu", SessionCommand.BACK),
    ]
    return select_menu(
        f"MANAGE PROJECTS & STORAGE (v{__version__})",
        items,
        default_value="view_info",
    )

