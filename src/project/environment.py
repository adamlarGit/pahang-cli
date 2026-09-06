"""Project environment composite facade module for Pahang CLI."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import config
from src.project.models import CameraConfig, ProjectMetadata, PrpdConfig
from src.project.repository import JsonFileProjectRepository, ProjectRepository
from src.project.storage import LocalWorkspaceStorage, WorkspaceStorage
from src.whatsapp.models import WhatsAppReportResources


class ProjectEnvironment:
    """Composite facade combining project metadata and workspace storage."""

    def __init__(
        self,
        metadata: ProjectMetadata,
        storage: WorkspaceStorage,
        repository: ProjectRepository | None = None,
    ) -> None:
        if not isinstance(metadata, ProjectMetadata) or not isinstance(storage, WorkspaceStorage):
            raise TypeError("ProjectEnvironment requires explicitly injected ProjectMetadata and WorkspaceStorage instances.")
        self.metadata = metadata
        self.storage = storage
        self._repository = repository

    @property
    def project_key(self) -> str:
        return self.metadata.key

    @property
    def project_data(self) -> dict[str, Any]:
        return self.metadata.to_dict()

    @property
    def base_path(self) -> Path:
        return self.storage.root_path

    @property
    def state(self) -> str:
        return self.metadata.state

    @property
    def po_number(self) -> str:
        return self.metadata.po_number

    @property
    def voltage_type(self) -> str:
        return self.metadata.voltage_type

    @property
    def year(self) -> str:
        return self.metadata.year

    @property
    def cycle(self) -> str:
        return self.metadata.cycle

    @property
    def technologies(self) -> list[str]:
        return list(self.metadata.technologies)

    def validate(self) -> None:
        self.storage.validate_existence()

    def get_python_dir(self) -> Path:
        return self.storage.get_python_dir()

    def get_testsheet_dir(self) -> Path:
        return self.storage.get_testsheet_dir()

    def get_raw_material_dir(self) -> Path:
        return self.storage.get_raw_material_dir()

    def get_quick_report_dir(self) -> Path:
        return self.storage.get_quick_report_dir()

    def get_engr_folder(self) -> Path:
        return self.storage.get_engr_folder()

    def list_engr_files(self) -> list[Path]:
        return self.storage.list_engr_files()

    def get_total_pe_path(self) -> Path:
        return self.storage.get_total_pe_path()

    def get_data_msms_path(self) -> Path:
        return self.storage.get_data_msms_path()

    def get_whatsapp_dir(self) -> Path:
        return self.storage.get_whatsapp_dir()

    def get_sign_dir(self) -> Path:
        return self.storage.get_sign_dir()

    def get_substation_raw_data_dir(
        self,
        station: str,
        month: str | None,
        date_str: str | None,
        substation_number: int,
    ) -> Path | None:
        return self.storage.get_substation_raw_data_dir(
            station=station,
            month=month,
            date_str=date_str,
            substation_number=substation_number,
        )

    def get_po_number(self) -> str:

        return self.metadata.po_number

    def get_station_mapping(self) -> dict[str, str]:
        return dict(config.STATION_MAPPING)

    def get_cbm_defect_folder_name(self) -> str:
        techs = {t.upper() for t in self.metadata.technologies}
        if "TEV" in techs:
            return "DEFECT IR US TEV"
        elif "US" in techs:
            return "DEFECT IR US"
        return "DEFECT IR"

    def get_template(self, key: str) -> Path:
        if hasattr(config, "CBM_DEFECT_TEMPLATES") and key in config.CBM_DEFECT_TEMPLATES:
            folder_name = self.get_cbm_defect_folder_name()
            filename = config.CBM_DEFECT_TEMPLATES[key]
            return self.storage.get_cbm_defect_template(folder_name, filename)
        return self.storage.get_template(key)

    def get_whatsapp_template(self) -> Path:
        return self.get_template("whatsapp_template")

    def get_whatsapp_report_resources(self) -> WhatsAppReportResources:
        return WhatsAppReportResources(
            quick_report_dir=self.get_quick_report_dir(),
            save_dir=self.get_whatsapp_dir(),
            template_path=self.get_whatsapp_template(),
            total_pe_path=self.get_total_pe_path(),
            station_mapping=self.get_station_mapping(),
        )

    def get_vi_front_page_template(self) -> Path:
        techs = {t.upper() for t in self.metadata.technologies}
        if "TEV" in techs:
            return self.get_template("vi_front_page_ir_us_tev")
        elif "US" in techs:
            return self.get_template("vi_front_page_ir_us")
        return self.get_template("vi_front_page_ir")

    def get_vi_summary_template(self) -> Path:
        return self.get_template("vi_summary")

    def get_cbm_summary_template(self) -> Path:
        techs = {t.upper() for t in self.metadata.technologies}
        if "TEV" in techs:
            return self.get_template("cbm_summary_ir_us_tev")
        elif "US" in techs:
            return self.get_template("cbm_summary_ir_us")
        return self.get_template("cbm_summary_ir")

    def get_vi_defect_template(self) -> Path:
        return self.get_template("vi_defect")

    def get_sub_cond_dir(self) -> Path:
        return self.get_template("sub_cond_dir")

    def list_testsheet_folders(self) -> list[Path]:
        return self.storage.list_testsheet_folders()

    def ensure_directory(self, path: Path | str) -> Path:
        return self.storage.ensure_directory(path)

    def resolve_template_path(self, key: str) -> Path:
        return self.get_template(key)

    def _get_repository(self) -> ProjectRepository:
        if self._repository is not None:
            return self._repository
        config_path = self.base_path / "project_config.json"
        return JsonFileProjectRepository(config_path)

    @property
    def repository(self) -> ProjectRepository:
        return self._get_repository()

    def get_camera_config(self) -> CameraConfig:
        config_path = self.base_path / "project_config.json"
        if config_path.exists():
            data = JsonFileProjectRepository._read_json(config_path)
            raw_cfg = data.get("camera_config", data if "ir_mode" in data else None)
            if raw_cfg and isinstance(raw_cfg, dict):
                return CameraConfig.from_dict(raw_cfg)
        return CameraConfig()

    def save_camera_config(self, camera_config: CameraConfig) -> None:
        config_path = self.base_path / "project_config.json"
        data = JsonFileProjectRepository._read_json(config_path)
        data["camera_config"] = camera_config.to_dict()
        JsonFileProjectRepository._write_json(config_path, data)
        if self._repository is not None:
            try:
                self._repository.save_camera_config(camera_config)
            except Exception:
                pass

    def get_prpd_config(self) -> PrpdConfig:
        return self._get_repository().get_prpd_config()

    def save_prpd_config(self, prpd_config: PrpdConfig) -> None:
        self._get_repository().save_prpd_config(prpd_config)


def create_project_environment(
    project_key: str,
    *,
    validate: bool = True,
    repository: ProjectRepository | None = None,
    storage: WorkspaceStorage | None = None,
) -> ProjectEnvironment:
    """Build a project environment, optionally injecting custom repository and storage."""
    if repository is None:
        repository = JsonFileProjectRepository()

    metadata = repository.get(project_key)

    if storage is None:
        storage = LocalWorkspaceStorage(metadata.base_path)

    if hasattr(storage, "_initialize_project_workspace"):
        storage._initialize_project_workspace()

    environment = ProjectEnvironment(metadata=metadata, storage=storage, repository=repository)
    if validate:
        environment.validate()
    return environment


def list_project_keys() -> list[str]:
    """Return configured project keys in display order."""
    return [p.key for p in JsonFileProjectRepository().list_all()]


def is_known_project_key(project_key: str | None) -> bool:
    """Return whether a project key exists in configuration."""
    if not project_key:
        return False
    try:
        JsonFileProjectRepository().get(project_key)
        return True
    except KeyError:
        return False


def get_project_name(project_key: str) -> str:
    """Return the display name for a configured project."""
    return JsonFileProjectRepository().get(project_key).name


def get_station_mapping() -> dict[str, str]:
    """Return the configured station mapping."""
    return dict(config.STATION_MAPPING)


def get_default_project_key(preferred_key: str | None = None) -> str | None:
    """Return a valid default project key or None if no projects registered."""
    if is_known_project_key(preferred_key) and preferred_key is not None:
        return str(preferred_key)
    default_meta = JsonFileProjectRepository().get_default(preferred_key)
    return default_meta.key if default_meta is not None else None


def load_project_environment() -> ProjectEnvironment | None:
    """Load the active project environment if one is saved and valid."""
    from src.cli_session import load_last_project_key
    key = load_last_project_key()
    if key and is_known_project_key(key):
        try:
            return create_project_environment(key)
        except Exception:
            return None
    return None


def get_or_create_utility_environment(target_dir: Path | None = None) -> ProjectEnvironment:
    """
    Get the active project environment or synthesize a transient one.
    """
    env = load_project_environment()
    if env is not None:
        return env
        
    if target_dir is None:
        from src import cli_selectors
        target_dir = cli_selectors.prompt_directory_path(
            "Enter target directory path",
            must_exist=False
        )
        if target_dir is None:
            raise ValueError("Operation cancelled, no target directory provided.")

    base_p = target_dir
    # Try to find a logical base path
    for parent in target_dir.parents:
        if (parent / "TESTSHEET").exists() or (parent / "PYTHON").exists():
            base_p = parent
            break
            
    meta = ProjectMetadata(key="utility", name="Utility Action", base_path=str(base_p), state="pahang", po_number="", voltage_type="11kV", year="2026", cycle="Cycle 1", technologies=("IR", "US", "TEV"))
    storage = LocalWorkspaceStorage(base_p)
    return ProjectEnvironment(metadata=meta, storage=storage)
