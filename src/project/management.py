"""Project onboarding, registration, and switching wizards for Pahang CLI."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src import cli_selectors
from src.cli_session import CliSession
from src.project.environment import ProjectEnvironment, create_project_environment
from src.project.models import ProjectMetadata
from src.project.repository import JsonFileProjectRepository, ProjectRepository
from src.project.storage import LocalWorkspaceStorage


logger = logging.getLogger(__name__)


def add_new_project_wizard(
    name: str | None = None,
    po_number: str | None = None,
    voltage_type: str | None = None,
    year: str | None = None,
    cycle: str | None = None,
    base_path: str | None = None,
    repository: ProjectRepository | None = None,
    session: CliSession | None = None,
) -> ProjectMetadata | None:
    """Guide user through creating and registering a new Pahang project."""
    if repository is None:
        repository = JsonFileProjectRepository()

    # Non-interactive mode when name and base_path are supplied programmatically
    if name is not None and base_path is not None:
        po = po_number or ""
        vol = voltage_type or "11kV"
        yr = year or "2026"
        cyc = cycle or "Cycle 1"

        path_obj = Path(base_path)
        path_obj.mkdir(parents=True, exist_ok=True)
        storage = LocalWorkspaceStorage(path_obj)
        storage._initialize_project_workspace()

        slug_base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        key = f"{slug_base}_{yr}_{re.sub(r'[^a-z0-9]+', '', cyc.lower())}"

        metadata = ProjectMetadata(
            key=key,
            name=f"{name} ({yr} - {cyc})",
            po_number=po,
            state="pahang",
            voltage_type=vol,
            year=yr,
            cycle=cyc,
            technologies=("IR", "US", "TEV"),
            base_path=str(path_obj),
        )
        repository.save(metadata)

        if session is not None:
            try:
                env = create_project_environment(key, repository=repository)
                session.activate_project(env)
            except Exception as exc:
                logger.warning("Auto-activation failed for new project %s: %s", key, exc)

        return metadata

    # Interactive CLI Wizard
    print("\n  ➕ ADD / REGISTER NEW PAHANG PROJECT")
    print("  ------------------------------------")

    try:
        raw_name = input("  Project Name (e.g. Pahang Kuantan): ").strip()
        if not raw_name:
            print("  Project name cannot be empty.")
            return None

        po_input = input("  PO Number (e.g. 42239999): ").strip()

        voltage_options = [
            cli_selectors.SelectOption("11kV", "11kV"),
            cli_selectors.SelectOption("33kV", "33kV"),
        ]
        vol_input = cli_selectors.select_one("  Select Voltage Rating", voltage_options, default_value="11kV")
        if not vol_input:
            vol_input = "11kV"

        year_input = input("  Inspection Year [2026]: ").strip() or "2026"
        cycle_input = input("  Inspection Cycle [Cycle 1]: ").strip() or "Cycle 1"

        raw_path = input("  Project Workspace Root Directory Path: ").strip().strip('"')
        if not raw_path:
            print("  Project directory path cannot be empty.")
            return None

        path_obj = Path(raw_path)
        path_obj.mkdir(parents=True, exist_ok=True)
        storage = LocalWorkspaceStorage(path_obj)
        storage._initialize_project_workspace()

        slug_base = re.sub(r"[^a-z0-9]+", "_", raw_name.lower()).strip("_")
        key = f"{slug_base}_{year_input}_{re.sub(r'[^a-z0-9]+', '', cycle_input.lower())}"

        metadata = ProjectMetadata(
            key=key,
            name=f"{raw_name} ({year_input} - {cycle_input})",
            po_number=po_input,
            state="pahang",
            voltage_type=vol_input,
            year=year_input,
            cycle=cycle_input,
            technologies=("IR", "US", "TEV"),
            base_path=str(path_obj),
        )

        repository.save(metadata)
        print(f"  ✓ Project '{metadata.name}' registered and saved successfully.\n")

        if session is not None:
            try:
                env = create_project_environment(key, repository=repository)
                session.activate_project(env)
                print(f"  ✓ Active project set to: {metadata.name}\n")
            except Exception as exc:
                logger.warning("Failed to activate project %s: %s", key, exc)

        return metadata

    except KeyboardInterrupt:
        print("\n  Project creation cancelled.")
        return None


def first_run_setup(project_key: str, repository: ProjectRepository | None = None) -> bool:
    """Ensure base_path exists and folder structure is initialized."""
    if repository is None:
        repository = JsonFileProjectRepository()

    try:
        meta = repository.get(project_key)
    except KeyError:
        return False

    base_path = Path(meta.base_path) if meta.base_path else None
    if base_path and base_path.exists() and (base_path / "PYTHON").exists():
        storage = LocalWorkspaceStorage(base_path)
        storage._initialize_project_workspace()
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

    storage = LocalWorkspaceStorage(path)
    storage._initialize_project_workspace()

    repository.update_base_path(project_key, str(path))
    print(f"  ✓ Project path saved and folder structure initialized.\n")
    return True


def prompt_for_project_key(
    last_project_key: str | None,
    allow_cancel: bool = True,
    repository: ProjectRepository | None = None,
) -> str | None:
    """Prompt the operator to choose an active project or add a new one."""
    if repository is None:
        repository = JsonFileProjectRepository()

    all_projects = repository.list_all()
    default_meta = repository.get_default(last_project_key)
    default_key = default_meta.key if default_meta else None

    options = [
        cli_selectors.SelectOption(
            (
                f"{p.name} ({p.key})"
                + (" [ACTIVE]" if p.key == last_project_key else "")
            ),
            p.key,
        )
        for p in all_projects
    ]

    options.append(cli_selectors.SelectOption("+ Add / Register New Project", "__add_new__"))
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
        new_meta = add_new_project_wizard(repository=repository)
        if new_meta is None:
            return None
        return new_meta.key

    return selection


def select_active_project_wizard(
    session: CliSession,
    allow_cancel: bool = True,
    repository: ProjectRepository | None = None,
) -> ProjectEnvironment | None:
    """Select and activate a project for the current CLI session."""
    if repository is None:
        repository = JsonFileProjectRepository()

    last_project_key = (
        session.active_project.project_key
        if session.active_project is not None
        else session.load_last_project_key()
    )

    while True:
        project_key = prompt_for_project_key(
            last_project_key,
            allow_cancel=allow_cancel,
            repository=repository,
        )
        if project_key is None:
            return None

        if not first_run_setup(project_key, repository=repository):
            continue

        try:
            environment = create_project_environment(project_key, repository=repository)
        except Exception as exc:
            print(f"Project activation failed: {exc}")
            last_project_key = project_key
            continue

        session.activate_project(environment)
        print(f"  ✓ Active project set to: {environment.project_data['name']}\n")
        return environment
