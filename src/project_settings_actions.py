"""Action handlers for Project & Storage Settings management in Pahang CLI."""

from __future__ import annotations

import logging
from pathlib import Path

from src import cli_selectors
from src.cli_session import CliSession
from src.project.environment import create_project_environment
from src.project.management import add_new_project_wizard, select_active_project_wizard
from src.project.models import WorkspaceHealth
from src.project.repository import JsonFileProjectRepository, ProjectRepository
from src.project.storage import LocalWorkspaceStorage


logger = logging.getLogger(__name__)


def handle_view_project_info(
    session: CliSession,
    repository: ProjectRepository | None = None,
    pause: bool = True,
) -> None:
    """Display active project metadata details and workspace health folder status."""
    if repository is None:
        repository = JsonFileProjectRepository()

    active_key = session.active_project_key
    if not active_key:
        print("\n  ⚠️ No project is currently active.")
        print("  Please select or register a project first.")
        env = select_active_project_wizard(session, repository=repository)
        if not env:
            return
        active_key = env.project_key

    try:
        meta = repository.get(active_key)
    except KeyError:
        print(f"\n  ⚠️ Active project key '{active_key}' not found in configuration.")
        return

    path_obj = Path(meta.base_path) if meta.base_path else None
    storage = LocalWorkspaceStorage(path_obj) if path_obj else None

    print("\n  =======================================================")
    print("    📌 ACTIVE PROJECT DETAILS")
    print("  =======================================================")
    print(f"    Project Name : {meta.name}")
    print(f"    PO Number    : {meta.po_number or '(Not set)'}")
    print(f"    Voltage      : {meta.voltage_type}")
    print(f"    Year / Cycle : {meta.year} / {meta.cycle}")
    print(f"    Technologies : {', '.join(meta.technologies)}")
    print(f"    Folder Path  : {meta.base_path or '(Not configured)'}")

    print("\n    📁 WORKSPACE FOLDER STATUS:")
    if storage and path_obj and path_obj.exists():
        health: WorkspaceHealth = storage.check_workspace_health()
        for item in health.items:
            badge = "  ✓ [OK]     " if item.exists else "  ❌ [MISSING]"
            print(f"      {badge} {item.label:<26} ({item.path})")
        print(f"\n    Overall Workspace Status: {'✅ Healthy' if health.is_healthy else '⚠️ Missing Required Folders/Files'}")
    else:
        print("      ❌ Workspace Root Directory does not exist on disk.")

    print("  =======================================================\n")
    if pause:
        try:
            input("  Press Enter to return to menu...")
        except (EOFError, OSError):
            pass



def handle_switch_project(
    session: CliSession,
    repository: ProjectRepository | None = None,
) -> None:
    """Interactively switch the active project session."""
    select_active_project_wizard(session, repository=repository)


def handle_add_project(
    session: CliSession,
    repository: ProjectRepository | None = None,
) -> None:
    """Interactively register a new project and optionally activate it."""
    add_new_project_wizard(repository=repository, session=session)


def handle_update_project_path(
    project_key: str | None = None,
    new_path: str | None = None,
    session: CliSession | None = None,
    repository: ProjectRepository | None = None,
) -> None:
    """Update workspace root directory path for a registered project."""
    if repository is None:
        repository = JsonFileProjectRepository()

    # Programmatic invocation
    if project_key is not None and new_path is not None:
        repository.update_base_path(project_key, new_path)
        if session is not None and session.active_project_key == project_key:
            try:
                env = create_project_environment(project_key, repository=repository)
                session.activate_project(env)
            except Exception as exc:
                logger.warning("Failed to refresh environment after path update: %s", exc)
        return

    # Interactive CLI invocation
    all_projects = repository.list_all()
    if not all_projects:
        print("\n  ⚠️ No projects registered in configuration.")
        return

    active_key = session.active_project_key if session else None
    options = [
        cli_selectors.SelectOption(
            f"{p.name} ({p.base_path})" + (" [ACTIVE]" if p.key == active_key else ""),
            p.key,
        )
        for p in all_projects
    ]
    options.append(cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"))

    selected_key = cli_selectors.select_one(
        "SELECT PROJECT TO UPDATE DIRECTORY PATH",
        options,
    )
    if not selected_key or selected_key == "__cancel__":
        return

    meta = repository.get(selected_key)
    print(f"\n  Updating Workspace Directory Path for: {meta.name}")
    print(f"  Current Path: {meta.base_path}\n")

    try:
        raw_path = input("  Enter New Workspace Directory Path: ").strip().strip('"')
    except KeyboardInterrupt:
        print("\n  Path update cancelled.")
        return

    if not raw_path:
        print("  Path cannot be empty.")
        return

    repository.update_base_path(selected_key, raw_path)
    print(f"  ✓ Workspace directory path updated successfully to: {raw_path}")

    if session is not None and session.active_project_key == selected_key:
        try:
            env = create_project_environment(selected_key, repository=repository)
            session.activate_project(env)
            print("  ✓ Active project session environment refreshed.")
        except Exception as exc:
            logger.warning("Failed to refresh active session environment: %s", exc)

    print()


def handle_unregister_project(
    project_key: str | None = None,
    session: CliSession | None = None,
    repository: ProjectRepository | None = None,
) -> None:
    """Unregister/delete a project from configuration."""
    if repository is None:
        repository = JsonFileProjectRepository()

    # Programmatic invocation
    if project_key is not None:
        repository.delete(project_key, session=session)
        return

    # Interactive CLI invocation
    all_projects = repository.list_all()
    if not all_projects:
        print("\n  ⚠️ No projects registered in configuration.")
        return

    active_key = session.active_project_key if session else None
    options = [
        cli_selectors.SelectOption(
            f"{p.name} ({p.key})" + (" [ACTIVE]" if p.key == active_key else ""),
            p.key,
        )
        for p in all_projects
    ]
    options.append(cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"))

    selected_key = cli_selectors.select_one(
        "SELECT PROJECT TO UNREGISTER",
        options,
    )
    if not selected_key or selected_key == "__cancel__":
        return

    meta = repository.get(selected_key)
    confirm = input(f"\n  Are you sure you want to unregister '{meta.name}'? [y/N]: ").strip().lower()
    if confirm in ("y", "yes"):
        repository.delete(selected_key, session=session)
        print(f"  ✓ Project '{meta.name}' unregistered successfully.\n")
    else:
        print("  Unregister cancelled.\n")
