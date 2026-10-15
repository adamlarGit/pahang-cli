"""Unit and integration tests for 33kV Quick Report generation (Ticket #096)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.quick_report.cbm_render import _build_swg_render_context
from src.quick_report.cbm_summary import format_summary_equipment, prepare_tech_summary_rows
from src.quick_report.defects import CbmDefectRecord, MasterQr03DefectRepository, ViDefectRecord
from src.quick_report.substation_condition import (
    PpuSubstationConditionPairBuilderPolicy,
    build_substation_condition_pairs,
)
from src.quick_report.transformer import QuickReportTransformer
from src.testsheet.models import (
    FireExtinguisherSpec,
    LVDBSpec,
    PowerTransformerSpec,
    SubstationEquipmentPackage,
    SubstationTestsheetPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
    TransformerSpec,
)


def _make_ppu_package(
    *,
    has_33kv: bool = True,
    has_11kv: bool = True,
    power_tx_count: int = 2,
    has_local_tx: bool = True,
    has_lvdb: bool = True,
    has_fe: bool = True,
    has_ner: bool = True,
    has_control_panel: bool = True,
    has_cable_cellar: bool = True,
    substation_number: int = 1,
    substation_name: str = "PPU APMM 33-11kV",
    extra_switchgears: tuple[SwitchgearSpec, ...] = (),
) -> SubstationTestsheetPackage:
    switchgears: list[SwitchgearSpec] = []
    if has_33kv:
        switchgears.append(
            SwitchgearSpec(
                switchgear_type="GIS 33kV",
                manufacturer="TAMCO",
                model="GV3",
                rating="1250A",
                serial_no="SN-33KV-001",
                panels=(
                    SwitchgearPanelSpec(panel_no=1, panel_feeder_no="1P5", name="INCOMER 1"),
                    SwitchgearPanelSpec(panel_no=2, panel_feeder_no="3P1", name="FEEDER 1"),
                ),
            )
        )
    if has_11kv:
        switchgears.append(
            SwitchgearSpec(
                switchgear_type="VCB 11kV",
                manufacturer="TAMCO",
                model="VH3",
                rating="630A",
                serial_no="SN-11KV-001",
                panels=(
                    SwitchgearPanelSpec(panel_no=1, panel_feeder_no="9", name="PANEL 9"),
                    SwitchgearPanelSpec(panel_no=2, panel_feeder_no="1K5", name="TX 1 FEEDER"),
                ),
            )
        )
    if extra_switchgears:
        switchgears.extend(extra_switchgears)

    transformers: list[TransformerSpec] = []
    for i in range(1, power_tx_count + 1):
        transformers.append(
            PowerTransformerSpec(
                tx_id=f"TX {i}",
                rating_kva="15MVA",
                manufacturer="MTM",
                model="15-201",
                serial_no=f"SN-TX-{i}",
            )
        )
    if has_local_tx:
        transformers.append(
            TransformerSpec(
                tx_id="LOCAL TX",
                rating_kva="500kVA",
                manufacturer="TAMCO",
                model="DTX",
                serial_no="SN-LOCAL-TX",
            )
        )

    lvdb_specs = (
        (LVDBSpec(name="LVDB 1", label="LVDB", source="LOCAL TX"),)
        if has_lvdb
        else ()
    )
    fe_spec = (
        FireExtinguisherSpec(has_fire_extinguisher=True, expiry_date="12/2027", status="GOOD")
        if has_fe
        else FireExtinguisherSpec()
    )

    equipment = SubstationEquipmentPackage(
        switchgears=tuple(switchgears),
        transformers=tuple(transformers),
        lvdb_specs=lvdb_specs,
        fire_extinguisher=fe_spec,
        has_ner=has_ner,
        has_control_panel=has_control_panel,
        has_cable_cellar=has_cable_cellar,
    )

    data = TestsheetData(
        substation_number=substation_number,
        substation_name_site=substation_name,
        substation_name_erms=substation_name,
        station_name="GEBENG",
        fl_site="CGBG-PPU-APMM",
        fl_erms="CGBG-PPU-APMM",
        date_str="07-10-2026",
        substation_type="PPU",
        equipment=equipment,
    )

    return SubstationTestsheetPackage(
        testsheet_path=Path("TESTSHEET/GEBENG/OCTOBER/07-10-2026/01. PPU APMM 33-11kV.xlsx"),
        unsorted_raw_data_dir=Path("TESTSHEET/GEBENG/OCTOBER/07-10-2026/UNSORTED RAW DATA"),
        station="GEBENG",
        month="OCTOBER",
        date_str="07-10-2026",
        substation_number=substation_number,
        data=data,
    )


# ---------------------------------------------------------------------------
# Seam 1: Substation Condition Pair Builder Policy
# ---------------------------------------------------------------------------

def test_ppu_condition_pair_builder_dual_voltage_full_package() -> None:
    """Verify PpuSubstationConditionPairBuilderPolicy produces canonical 4-page 33kV pairs."""
    pkg = _make_ppu_package()
    pairs = PpuSubstationConditionPairBuilderPolicy.build(pkg)

    expected = [
        # Page 1
        ("SUBSTATION OVERVIEW", "SIGNBOARD"),
        ("SWITCHGEAR 33kV", "SWITCHGEAR 33kV NAMEPLATE"),
        ("SWITCHGEAR 11kV", "SWITCHGEAR 11kV NAMEPLATE"),
        # Page 2
        ("POWER TX1", "POWER TX1 NAMEPLATE"),
        ("POWER TX2", "POWER TX2 NAMEPLATE"),
        ("LOCAL TX", "LOCAL TX NAMEPLATE"),
        # Page 3
        ("LVDB", "LVDB NAMEPLATE"),
        ("CONTROL PANEL 33kV", "CONTROL PANEL 11kV"),
        ("FIRE EXTINGUISHER", "FIRE EXTINGUISHER EXPIRY DATE"),
        # Page 4
        ("NER", ""),
        ("33kV CABLE CELLAR", "11kV CABLE CELLAR"),
    ]
    assert pairs == expected


def test_ssu_condition_pair_builder_omits_unpopulated_assets() -> None:
    """Verify SSU condition pairs gracefully omit transformers, NER, 11kV SWG, and cellars."""
    pkg = _make_ppu_package(
        has_33kv=True,
        has_11kv=False,
        power_tx_count=0,
        has_local_tx=False,
        has_lvdb=False,
        has_fe=False,
        has_ner=False,
        has_control_panel=False,
        has_cable_cellar=False,
        substation_number=6,
        substation_name="SSU FLEXSYS CHEMICAL 33kV",
    )
    pairs = PpuSubstationConditionPairBuilderPolicy.build(pkg)

    expected = [
        ("SUBSTATION OVERVIEW", "SIGNBOARD"),
        ("SWITCHGEAR 33kV", "SWITCHGEAR 33kV NAMEPLATE"),
    ]
    assert pairs == expected


def test_build_substation_condition_pairs_dispatcher_routing() -> None:
    """Verify build_substation_condition_pairs routes to PPU policy when voltage_type == '33kV'."""
    pkg = _make_ppu_package()

    # 1. Explicit voltage_type="33kV"
    pairs_33 = build_substation_condition_pairs(pkg, voltage_type="33kV")
    assert ("SWITCHGEAR 33kV", "SWITCHGEAR 33kV NAMEPLATE") in pairs_33

    # 2. Inferred from environment
    env = MagicMock()
    env.voltage_type = "33kV"
    env.metadata.voltage_type = "33kV"
    pairs_env = build_substation_condition_pairs(pkg, environment=env)
    assert ("SWITCHGEAR 33kV", "SWITCHGEAR 33kV NAMEPLATE") in pairs_env

    # 3. 11kV fallback retains 11kV standard pairs
    pairs_11 = build_substation_condition_pairs(pkg, voltage_type="11kV")
    assert ("SWITCHGEAR", "SWITCHGEAR NAMEPLATE") in pairs_11 or any("SWITCHGEAR" in p[0] for p in pairs_11)
    assert not any("SWITCHGEAR 33kV" in p[0] for p in pairs_11)


# ---------------------------------------------------------------------------
# Seam 2: Quick Report Plan Transformer & Output Filename Formatter
# ---------------------------------------------------------------------------

def test_quick_report_transformer_2digit_prefix_for_33kv(tmp_path: Path) -> None:
    """Verify QuickReportTransformer formats 2-digit prefix for 33kV projects."""
    pkg = _make_ppu_package(substation_number=6, substation_name="SSU FLEXSYS CHEMICAL 33kV")
    cbm_defects = [
        CbmDefectRecord(
            equipment="GIS 33kV",
            equipment_id="PANEL 1P5",
            technology="US",
            us_reading="24",
            us_char="CORONA DISCHARGE",
        )
    ]
    vi_defects = [
        ViDefectRecord(
            equipment="CIVIL",
            defect_area="Trench Cover",
            additional_remarks="Broken slab",
        )
    ]

    env = MagicMock()
    env.voltage_type = "33kV"
    env.metadata.voltage_type = "33kV"
    env.get_quick_report_dir.return_value = tmp_path / "QUICK REPORT"
    env.get_vi_front_page_template.return_value = tmp_path / "fp.docx"
    env.get_cbm_summary_template.return_value = tmp_path / "cbm_sum.docx"
    env.get_vi_summary_template.return_value = tmp_path / "vi_sum.docx"
    env.get_vi_defect_template.return_value = tmp_path / "vi_def.docx"
    env.get_template.return_value = tmp_path / "tmpl.docx"

    transformer = QuickReportTransformer()
    # Mock cbm_planner.plan to avoid needing real template files on disk
    transformer._cbm_planner = MagicMock()
    transformer._cbm_planner.plan.return_value = ()

    plan = transformer.transform(
        pkg=pkg,
        cbm_defects=cbm_defects,
        vi_defects=vi_defects,
        environment=env,
    )

    # 33kV must have 2-digit prefix
    assert plan.output_filename == "06. SSU FLEXSYS CHEMICAL 33kV (US+VI).docx"
    assert plan.final_output_path.name == "06. SSU FLEXSYS CHEMICAL 33kV (US+VI).docx"
    # Condition pairs must be attached
    assert ("SWITCHGEAR 33kV", "SWITCHGEAR 33kV NAMEPLATE") in plan.condition_pairs


def test_quick_report_transformer_3digit_prefix_for_11kv(tmp_path: Path) -> None:
    """Verify QuickReportTransformer retains 3-digit prefix for 11kV projects."""
    pkg = _make_ppu_package(substation_number=6, substation_name="PE TIOMAN 1")
    cbm_defects = []
    vi_defects = []

    env = MagicMock()
    env.voltage_type = "11kV"
    env.metadata.voltage_type = "11kV"
    env.get_quick_report_dir.return_value = tmp_path / "QUICK REPORT"
    env.get_vi_front_page_template.return_value = tmp_path / "fp.docx"
    env.get_cbm_summary_template.return_value = None
    env.get_vi_summary_template.return_value = None
    env.get_vi_defect_template.return_value = None
    env.get_template.return_value = tmp_path / "tmpl.docx"

    transformer = QuickReportTransformer()
    transformer._cbm_planner = MagicMock()
    transformer._cbm_planner.plan.return_value = ()

    plan = transformer.transform(
        pkg=pkg,
        cbm_defects=cbm_defects,
        vi_defects=vi_defects,
        environment=env,
    )

    # 11kV must have 3-digit prefix
    assert plan.output_filename == "006. PE TIOMAN 1.docx"


# ---------------------------------------------------------------------------
# Seam 3: Multi-Voltage Switchgear CBM Attribution & Summary Generation
# ---------------------------------------------------------------------------

def test_dual_voltage_cbm_defect_attribution_and_header_rendering() -> None:
    """Verify CBM render context and summary rows iterate equipment.switchgears (plural) and attribute correct voltage classes."""
    pkg = _make_ppu_package()
    pe_info = {
        "equipment": pkg.data.equipment,
        "equipment_package": pkg.data.equipment,
        "equipment_specs": pkg.data.equipment,
        "testsheet_data": pkg.data,
    }

    # Defect 1: on 33kV switchgear panel 1P5
    defect_33 = CbmDefectRecord(
        equipment="GIS 33kV",
        equipment_id="1P5 - INCOMER 1",
        technology="US",
        us_reading="28",
        us_char="CORONA DISCHARGE",
        defect_area="Cable Compartment",
    )

    # Defect 2: on 11kV switchgear panel 9
    defect_11 = CbmDefectRecord(
        equipment="VCB 11kV",
        equipment_id="9",
        technology="TEV",
        tev_reading="32",
        defect_area="Breaker Compartment",
    )

    # Render context for 33kV defect
    ctx_33 = _build_swg_render_context(
        defect_33,
        overview=False,
        item_key="GIS 33kV",
        pe_info=pe_info,
    )
    assert ctx_33["swg"]["type"] == "GIS 33kV"
    assert ctx_33["swg"]["manufacturer"] == "TAMCO"
    assert ctx_33["swg"]["model"] == "GV3"
    assert ctx_33["swg"]["rating"] == "1250A"
    assert "1P5" in ctx_33["panel"]["linknumber"]
    assert ctx_33["panel"]["name"] == "INCOMER 1"

    # Render context for 11kV defect
    ctx_11 = _build_swg_render_context(
        defect_11,
        overview=False,
        item_key="VCB 11kV",
        pe_info=pe_info,
    )
    assert ctx_11["swg"]["type"] == "VCB 11kV"
    assert ctx_11["swg"]["manufacturer"] == "TAMCO"
    assert ctx_11["swg"]["model"] == "VH3"
    assert ctx_11["swg"]["rating"] == "630A"
    assert "9" in ctx_11["panel"]["linknumber"]

    # Technical summary rows attribution across both lineups
    rows = prepare_tech_summary_rows([defect_33, defect_11], pe_info=pe_info)
    assert len(rows) == 2

    row_33 = next(r for r in rows if "1P5" in r.equipment)
    assert "GIS 33kV" in row_33.equipment
    assert row_33.brand == "TAMCO"
    assert row_33.model == "GV3"
    assert row_33.rating == "1250A"

    row_11 = next(r for r in rows if "9" in r.equipment)
    assert "VCB 11kV" in row_11.equipment
    assert row_11.brand == "TAMCO"
    assert row_11.model == "VH3"
    assert row_11.rating == "630A"


# ---------------------------------------------------------------------------
# Seam 4: Master QR03 VI Defect Ingestion
# ---------------------------------------------------------------------------

def test_master_qr03_defect_repository_vi_defects_strict_750_39(tmp_path: Path) -> None:
    """Verify MasterQr03DefectRepository strictly queries sheet 'QR03 VI' in Contract 750-39 workbook for 33kV."""
    import pandas as pd

    engr_dir = tmp_path / "PYTHON" / "ENGR FROM DRIVE"
    engr_dir.mkdir(parents=True, exist_ok=True)

    master_path = engr_dir / "ENGR-750-39 -CBA-PAHANG - 2026.xlsx"

    # Dummy QR03 CBA sheet
    cba_df = pd.DataFrame(
        [
            {
                "FUNCTIONAL LOCATION": "CGBG-PPU-APMM",
                "DEFECT FROM": "US",
                "EQUIPMENT": "GIS 33kV",
                "EQUIPMENT ID": "1P5",
                "BRAND": "TAMCO",
                "MODEL": "GV3",
                "RATING": "1250A",
                "HV/LV": "33kV",
                "DEFECT AREA": "Cable Compartment",
                "ADDITIONAL REMARKS": "High discharge",
                "READING": "28",
            }
        ]
    )

    # QR03 VI sheet with EET filter check
    vi_df = pd.DataFrame(
        [
            {
                "FUNCTIONAL LOCATION": "CGBG-PPU-APMM",
                "EQUIPMENT": "CIVIL",
                "DEFECT AREA": "Trench Cover",
                "ADDITIONAL REMARKS": "Broken slab",
                "REPORT BY": "EET",
            },
            {
                "FUNCTIONAL LOCATION": "CGBG-PPU-APMM",
                "EQUIPMENT": "CIVIL",
                "DEFECT AREA": "Fence",
                "ADDITIONAL REMARKS": "Should be ignored (not EET)",
                "REPORT BY": "CONTRACTOR",
            },
            {
                "FUNCTIONAL LOCATION": "CGBG-PPU-OTHER",
                "EQUIPMENT": "SWITCHGEAR",
                "DEFECT AREA": "Indicator lamp",
                "ADDITIONAL REMARKS": "Other station",
                "REPORT BY": "EET",
            },
        ]
    )

    with pd.ExcelWriter(master_path, engine="openpyxl") as writer:
        cba_df.to_excel(writer, sheet_name="QR03 CBA", index=False)
        vi_df.to_excel(writer, sheet_name="QR03 VI", index=False)

    repo = MasterQr03DefectRepository(engr_dir=engr_dir, voltage_type="33kV")

    vi_defects = repo.fetch_vi_defects("CGBG-PPU-APMM")
    assert len(vi_defects) == 1
    assert vi_defects[0].equipment == "CIVIL"
    assert vi_defects[0].defect_area == "Trench Cover"
    assert vi_defects[0].additional_remarks == "Broken slab"

    # Non-existent station returns empty list without falling back to anything else
    assert repo.fetch_vi_defects("NON-EXISTENT-FL") == []


def test_format_summary_equipment_prefix_handling() -> None:
    """Verify format_summary_equipment correctly strips GIS/VCB prefixes from raw_id."""
    pkg = _make_ppu_package()
    pe_info = {"equipment": pkg.data.equipment}

    defect = CbmDefectRecord(
        equipment="GIS 33kV",
        equipment_id="GIS 33kV - PANEL 1P5",
        technology="US",
        us_reading="25",
    )
    formatted = format_summary_equipment(defect, pe_info=pe_info)
    assert "PANEL GIS 33kV" not in formatted
    assert "PANEL 1P5" in formatted
    assert "INCOMER 1" in formatted


def test_ppu_condition_pairs_dual_33kv_only() -> None:
    """Verify station with two 33kV switchgears and no 11kV switchgear does not falsely emit 11kV pair."""
    swg2 = SwitchgearSpec(
        switchgear_type="GIS 33kV",
        manufacturer="TAMCO",
        model="GV3",
        panels=(SwitchgearPanelSpec(panel_no=1, panel_feeder_no="3P2", name="FEEDER 2"),),
    )
    pkg = _make_ppu_package(has_33kv=True, has_11kv=False, extra_switchgears=(swg2,))

    policy = PpuSubstationConditionPairBuilderPolicy()
    pairs = policy.build(pkg)

    pair_keys = [f"{p[0]}|{p[1]}" for p in pairs]
    assert any("SWITCHGEAR 33kV" in k for k in pair_keys)
    assert not any("SWITCHGEAR 11kV" in k for k in pair_keys)




