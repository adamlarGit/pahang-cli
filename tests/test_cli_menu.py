"""Unit tests for interactive CLI menu selections and sub-menu routing."""

from unittest.mock import MagicMock, patch

import pytest
from src.cli_menu import SessionCommand, select_project_management_action, select_settings_action
from src.cli_session import CliSession
from src.workflow_cli import _run_project_management_menu, _run_settings_menu


def test_select_settings_action_menu_items() -> None:
    with patch("src.cli_menu.cli_selectors.select_one") as mock_select:
        mock_select.return_value = "manage_projects"
        result = select_settings_action()
        assert result == "manage_projects"

        # Verify options rendered include Manage Projects
        title, options = mock_select.call_args[0]
        assert "SETTINGS" in title
        option_values = [opt.value for opt in options]
        assert "manage_projects" in option_values
        assert "configure_cameras" in option_values
        assert "rollback" in option_values
        assert SessionCommand.BACK in option_values


def test_select_project_management_action_menu_items() -> None:
    with patch("src.cli_menu.cli_selectors.select_one") as mock_select:
        mock_select.return_value = "view_info"
        result = select_project_management_action()
        assert result == "view_info"

        title, options = mock_select.call_args[0]
        assert "MANAGE PROJECTS & STORAGE" in title
        option_values = [opt.value for opt in options]
        assert option_values == [
            "view_info",
            "switch_project",
            "add_project",
            "update_path",
            "unregister_project",
            SessionCommand.BACK,
        ]


def test_run_project_management_menu_routing() -> None:
    session = MagicMock(spec=CliSession)

    actions = [
        "view_info",
        "switch_project",
        "add_project",
        "update_path",
        "unregister_project",
        SessionCommand.BACK,
    ]

    with patch("src.cli_menu.select_project_management_action", side_effect=actions):
        with patch("src.project_settings_actions.handle_view_project_info") as mock_view, \
             patch("src.project_settings_actions.handle_switch_project") as mock_switch, \
             patch("src.project_settings_actions.handle_add_project") as mock_add, \
             patch("src.project_settings_actions.handle_update_project_path") as mock_update, \
             patch("src.project_settings_actions.handle_unregister_project") as mock_unregister:

            _run_project_management_menu(session)

            mock_view.assert_called_once_with(session)
            mock_switch.assert_called_once_with(session)
            mock_add.assert_called_once_with(session)
            mock_update.assert_called_once_with(session=session)
            mock_unregister.assert_called_once_with(session=session)


def test_run_settings_menu_manage_projects_dispatch() -> None:
    session = MagicMock(spec=CliSession)

    settings_selections = ["manage_projects", SessionCommand.BACK]

    with patch("src.cli_menu.select_settings_action", side_effect=settings_selections):
        with patch("src.workflow_cli._run_project_management_menu") as mock_pm_menu:
            _run_settings_menu(session)

            mock_pm_menu.assert_called_once_with(session)
