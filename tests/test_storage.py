import os
from pathlib import Path
import zipfile

import config
from src.project.storage import LocalWorkspaceStorage, extract_prefix_safe, repair_openpyxl_zip

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


def test_full_report_storage_template_resolution(tmp_path: Path) -> None:
    """Verify Full Report template resolution and initialization in LocalWorkspaceStorage (Bug 7)."""
    project_root = tmp_path / "workspace"
    project_root.mkdir()

    storage = LocalWorkspaceStorage(project_root)
    storage._initialize_project_workspace()

    fr_dir = storage.get_full_report_templates_dir()
    assert fr_dir == project_root / "templates" / "FULL REPORT"
    assert fr_dir.exists()

    census_tpl = storage.get_full_report_census_template()
    assert census_tpl == fr_dir / "executive_summary_census.docx"
    assert census_tpl.exists()

    normal_dir = storage.get_full_report_normal_templates_dir()
    assert normal_dir == fr_dir / "NORMAL IR US TEV"
    assert normal_dir.exists()

    swg_tpl = storage.get_full_report_normal_template("swg-overview.docx")
    assert swg_tpl == normal_dir / "swg-overview.docx"
    assert swg_tpl.exists()


def test_extract_prefix_safe() -> None:
    """Verify safe extraction of numerical prefix with dot, underscore, or fallback to None."""
    assert extract_prefix_safe("01. PPU PEKAN.xlsx") == 1
    assert extract_prefix_safe("042_PMU_GAMBANG.docx") == 42
    assert extract_prefix_safe("005 SUBSTATION") == 5
    assert extract_prefix_safe("12-PE KELAN.xlsx") == 12
    assert extract_prefix_safe("  07. PPU JENGKA.xlsx") == 7
    assert extract_prefix_safe(Path("03. PPU TEMERLOH.xlsx")) == 3
    assert extract_prefix_safe(Path("099_PMU.docx")) == 99
    assert extract_prefix_safe(None) is None
    assert extract_prefix_safe("   ") is None
    assert extract_prefix_safe("no_prefix_here.xlsx") is None
    assert extract_prefix_safe("") is None
    assert extract_prefix_safe("abc_01.xlsx") is None


def test_repair_openpyxl_zip(tmp_path: Path) -> None:
    """Verify repair_openpyxl_zip corrects relationship targets and restores missing drawings."""
    # Case 1: non-existent target or None inputs return safely without error
    non_existent = tmp_path / "does_not_exist.xlsx"
    repair_openpyxl_zip(non_existent, non_existent)
    repair_openpyxl_zip(None, None)
    repair_openpyxl_zip("", "")

    # Case 2: repair relationship targets and missing drawings
    in_zip = tmp_path / "orig.xlsx"
    out_zip = tmp_path / "modified.xlsx"

    drawing_content = b"<xml>drawing_data</xml>"
    rels_content = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        b'<Relationship Id="rId1" Type="table" Target="/xl/tables/table1.xml"/>\n'
        b'<Relationship Id="rId2" Type="drawing" Target="/xl/drawings/drawing1.xml"/>\n'
        b'</Relationships>'
    )

    with zipfile.ZipFile(in_zip, "w") as z:
        z.writestr("xl/drawings/drawing1.xml", drawing_content)
        z.writestr("[Content_Types].xml", b"<xml/>")

    with zipfile.ZipFile(out_zip, "w") as z:
        z.writestr("xl/worksheets/_rels/sheet1.xml.rels", rels_content)
        z.writestr("[Content_Types].xml", b"<xml/>")

    repair_openpyxl_zip(in_zip, out_zip)

    with zipfile.ZipFile(out_zip, "r") as z:
        names = z.namelist()
        assert "xl/drawings/drawing1.xml" in names
        assert z.read("xl/drawings/drawing1.xml") == drawing_content

        fixed_rels = z.read("xl/worksheets/_rels/sheet1.xml.rels").decode("utf-8")
        assert 'Target="/xl/tables/' not in fixed_rels
        assert 'Target="../tables/table1.xml"' in fixed_rels
        assert 'Target="/xl/drawings/' not in fixed_rels
        assert 'Target="../drawings/drawing1.xml"' in fixed_rels


def test_sanitize_filename_strips_control_and_reserved_characters() -> None:
    """Verify sanitize_filename strips ASCII control characters, newlines, and Windows reserved chars."""
    from src.project.storage import sanitize_filename

    # 1. ASCII control characters (\x00-\x1f, \x7f)
    assert sanitize_filename("hello\x00world\x1f\x7ftest") == "helloworldtest"

    # 2. Multiline whitespace (\r\n, \n, \r, \t) normalized to single spaces
    assert sanitize_filename("33kV TRANSITION\n(BUS - SECTION)") == "33kV TRANSITION (BUS - SECTION)"
    assert sanitize_filename("line1\r\nline2\tline3") == "line1 line2 line3"

    # 3. Windows-reserved characters ([<>:"/\\|?*])
    assert sanitize_filename('bad:file"with*special?chars<and>pipes|end') == "badfilewithspecialcharsandpipesend"
    assert sanitize_filename("path/with\\slashes:and:colons") == "pathwithslashesandcolons"

    # 4. Trailing dots and spaces stripped
    assert sanitize_filename("test_file. ") == "test_file"
    assert sanitize_filename("another_file...") == "another_file"
    assert sanitize_filename("valid_report.docx") == "valid_report.docx"

    # 5. Empty and edge cases
    assert sanitize_filename("") == ""
    assert sanitize_filename("   ") == ""
    assert sanitize_filename(None) == ""




