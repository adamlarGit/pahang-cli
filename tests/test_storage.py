import os
from pathlib import Path

import config
from src.project.storage import LocalWorkspaceStorage

def test_local_workspace_storage_template_resolution(tmp_path: Path) -> None:
    # Setup global template mock
    original_global_templates = config.GLOBAL_TEMPLATES_DIR
    original_templates = config.TEMPLATES
    original_seed_files = getattr(config, "SEED_FILES", {})

    mock_global_templates = tmp_path / "global_templates"
    mock_global_templates.mkdir()
    config.GLOBAL_TEMPLATES_DIR = mock_global_templates
    
    mock_template_rel = "QUICK REPORT/template.docx"
    config.TEMPLATES = {"test_template": mock_template_rel}
    
    mock_seed_rel = "PYTHON/SEED.xlsx"
    config.SEED_FILES = {mock_seed_rel: mock_seed_rel}

    (mock_global_templates / "QUICK REPORT").mkdir(parents=True)
    (mock_global_templates / mock_template_rel).touch()

    (mock_global_templates / "PYTHON").mkdir(parents=True)
    (mock_global_templates / mock_seed_rel).touch()

    try:
        project_root = tmp_path / "project_root"
        project_root.mkdir()

        # Initialize storage and trigger bootstrap
        storage = LocalWorkspaceStorage(project_root)
        storage._initialize_project_workspace()

        # Verify templates dir defaults to <base_path>/templates
        assert storage._templates_dir == project_root / "templates"

        # Verify template resolution from project workspace templates
        resolved_path = storage.resolve_template_path("test_template")
        assert resolved_path == project_root / "templates" / mock_template_rel
        assert resolved_path.exists()

        # Verify seed file copied to correct path
        seed_target = project_root / mock_seed_rel
        assert seed_target.exists()

    finally:
        # Restore original config
        config.GLOBAL_TEMPLATES_DIR = original_global_templates
        config.TEMPLATES = original_templates
        config.SEED_FILES = original_seed_files


def test_get_substation_raw_data_dir(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path)
    raw_root = storage.get_raw_material_dir()

    # Case 1: Non-existent directory returns None
    assert storage.get_substation_raw_data_dir("KUANTAN", "08. AUGUST", "10-08-2026", 42) is None

    # Case 2: Exact substation number folder (042/RAW DATA)
    pe_dir = raw_root / "KUANTAN" / "08. AUGUST" / "10-08-2026" / "042" / "RAW DATA"
    pe_dir.mkdir(parents=True)
    resolved = storage.get_substation_raw_data_dir("KUANTAN", "08. AUGUST", "10-08-2026", 42)
    assert resolved == pe_dir

    # Case 3: Prefix substation folder (055. URBAN JAYA/RAW DATA)
    pe_prefix_dir = raw_root / "KUANTAN" / "08. AUGUST" / "10-08-2026" / "055. URBAN JAYA" / "RAW DATA"
    pe_prefix_dir.mkdir(parents=True)
    resolved_prefix = storage.get_substation_raw_data_dir("KUANTAN", "08. AUGUST", "10-08-2026", 55)
    assert resolved_prefix == pe_prefix_dir

    # Case 4: Date string used to format month if month is None
    pe_sep_dir = raw_root / "PEKAN" / "09. SEPTEMBER" / "03-09-2026" / "007" / "RAW DATA"
    pe_sep_dir.mkdir(parents=True)
    resolved_sep = storage.get_substation_raw_data_dir("PEKAN", None, "03-09-2026", 7)
    assert resolved_sep == pe_sep_dir

    # Case 5: Direct folder containing US+TEV without RAW DATA subfolder
    pe_direct_dir = raw_root / "PEKAN" / "09. SEPTEMBER" / "03-09-2026" / "008"
    (pe_direct_dir / "US+TEV").mkdir(parents=True)
    resolved_direct = storage.get_substation_raw_data_dir("PEKAN", None, "03-09-2026", 8)
    assert resolved_direct == pe_direct_dir

