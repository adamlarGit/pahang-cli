"""Targeted unit tests verifying Bug A and Bug B 33kV pipeline bugfixes.

Bug A: Switchgear Ultrasound and TEV Readings Wiring from Testsheet
Bug B: Cable Cellar Overview in Full Report Overview & Summary
"""

from __future__ import annotations

from pathlib import Path

from src.core.topology import (
    SwitchgearArchetype,
    SwitchgearTopologyEngine,
    VoltageClass,
    resolve_overview_compartments,
)
from src.full_report.scan_adapters import SwitchgearScanAdapter
from src.quick_report.substation_condition import (
    PpuSubstationConditionPairBuilderPolicy,
)
from src.testsheet.models import (
    SubstationEquipmentPackage,
    SubstationTestsheetPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
)
from src.testsheet.parsers.ppu import PpuTestsheetParser
from tests.fixtures.ppu_workbook_factory import create_ppu_testsheet_workbook


# ==============================================================================
# BUG A TESTS: Switchgear Ultrasound and TEV Readings Wiring from Testsheet
# ==============================================================================


def test_bug_a_readings_wiring_direct_row(tmp_path: Path) -> None:
    """Verify Col R (TEV), Col S (PPC), Col T (US), Col U (US char), Col V (TEV char)

    are correctly wired into SwitchgearPanelSpec from row r.
    """
    wb_path = tmp_path / "01. PPU READINGS DIRECT.xlsx"
    parser = PpuTestsheetParser()

    custom_panels = [
        {
            "feeder_no": "3P1",
            "name": "INCOMING 33kV",
            "status": "CLOSE",
            "tev_reading": "28.5",
            "tev_ppc": "15",
            "us_reading": "12.0",
            "tev_char": "NOISE PATTERN",
        }
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=custom_panels,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    assert len(swg.panels) == 1
    panel = swg.panels[0]

    assert panel.tev_reading == "28.5"
    assert panel.tev_ppc == "15"
    assert panel.us_reading == "12.0"
    assert panel.tev_char == "NOISE PATTERN"


def test_bug_a_readings_sub_row_fallback(tmp_path: Path) -> None:
    """Verify breaker readings are isolated to row r and do not inherit cable readings from sub-row 1,

    while characteristic in Col U falls back across the stride.
    """
    wb_path = tmp_path / "02. PPU READINGS FALLBACK.xlsx"
    parser = PpuTestsheetParser()

    custom_panels = [
        {
            "feeder_no": "3P1",
            "name": "BUS SECTION 33kV",
            "status": "CLOSE",
            # Row r values intentionally empty
            "tev_reading": "",
            "tev_ppc": "",
            "us_reading": "",
            # Place readings on sub-rows (Cable row r+1, Busbar row r+2)
            "sub_rows": {
                1: {"R": "32.0", "S": "40"},
                2: {"T": "16.5", "U": "CORONA DISCHARGE"},
            },
        }
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=custom_panels,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    panel = swg.panels[0]

    # Breaker readings on row r remain empty
    assert panel.tev_reading == ""
    assert panel.tev_ppc == ""
    assert panel.us_reading == ""

    # Cable readings on row r+1 are correctly isolated to cable fields
    assert panel.cable_tev_reading == "32.0"
    assert panel.cable_tev_ppc == "40"

    # Characteristic in Col U falls back across the bay stride
    assert panel.us_char == "CORONA DISCHARGE"
    assert panel.tev_char == "CORONA DISCHARGE"


def test_bug_a_tev_char_ignores_sn_and_gas_pressure(tmp_path: Path) -> None:
    """Verify Column V beginning with 'SN:' or GIS gas pressure is not treated as TEV characteristic,

    and empty Column U correctly defaults tev_char to 'NORMAL'.
    """
    wb_path = tmp_path / "03. PPU SN PREFIX.xlsx"
    parser = PpuTestsheetParser()

    custom_panels = [
        {
            "feeder_no": "3P1",
            "name": "FEEDER 33kV 1",
            "status": "CLOSE",
            "breaker_serial": "SN: VCB-2026-9999",
            # Col V row r has "SN: VCB-2026-9999"
            # Sub-row 1 has GIS gas pressure remarks
            "sub_rows": {
                1: {"V": "B: 0.87 kgf/cm²g"},
            },
        }
    ]

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=custom_panels,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    panel = swg.panels[0]

    assert panel.serial_no == "VCB-2026-9999"
    # Column U is empty, so tev_char must default to 'NORMAL', never GIS gas pressure or serial from Column V
    assert panel.tev_char == "NORMAL"


def test_bug_a_factory_default_wiring(tmp_path: Path) -> None:
    """Verify default integer panels in factory populate Col R, S, T."""
    wb_path = tmp_path / "04. PPU FACTORY DEFAULT.xlsx"
    parser = PpuTestsheetParser()

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=2,
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]
    assert len(swg.panels) == 2

    for p in swg.panels:
        assert p.tev_reading == "0"
        assert p.tev_ppc == "0"
        assert p.us_reading == "0"


# ==============================================================================
# BUG B TESTS: Cable Cellar Overview in Full Report Overview & Summary
# ==============================================================================


def test_bug_b_canonical_overview_compartments_include_cable_cellar() -> None:
    """Verify resolve_overview_compartments includes Cable Cellar LHS and RHS

    for 33kV VCB_CUBICLE and GIS_CUBICLE.
    """
    for arch in (SwitchgearArchetype.VCB_CUBICLE, SwitchgearArchetype.GIS_CUBICLE):
        comps = resolve_overview_compartments(arch, VoltageClass.KV_33)
        assert "OVERVIEW CABLE CELLAR (LHS)" in comps
        assert "OVERVIEW CABLE CELLAR (RHS)" in comps
        # Verify order: front, rear, top, cable cellar, main busbar, reserve busbar
        assert comps == (
            "OVERVIEW FRONT (LHS)",
            "OVERVIEW FRONT (RHS)",
            "OVERVIEW REAR (LHS)",
            "OVERVIEW REAR (RHS)",
            "OVERVIEW TOP (LHS)",
            "OVERVIEW TOP (RHS)",
            "OVERVIEW CABLE CELLAR (LHS)",
            "OVERVIEW CABLE CELLAR (RHS)",
            "OVERVIEW MAIN BUSBAR (LHS)",
            "OVERVIEW MAIN BUSBAR (RHS)",
            "OVERVIEW RESERVE BUSBAR (LHS)",
            "OVERVIEW RESERVE BUSBAR (RHS)",
        )

    # 11kV should NOT have LHS/RHS cable cellar by default
    comps_11 = resolve_overview_compartments(SwitchgearArchetype.VCB_CUBICLE, VoltageClass.KV_11)
    assert comps_11 == ("OVERVIEW FRONT", "OVERVIEW REAR", "OVERVIEW TOP")


def test_bug_b_scan_adapter_with_switchgear_spec(tmp_path: Path) -> None:
    """Verify SwitchgearScanAdapter properly retrieves overview_compartments

    when self.swg is a SwitchgearSpec (not SwitchgearScanSpec), preserving Cable Cellar.
    """
    swg_spec = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="VH3",
        rating="33kV",
        overview_compartments=(
            "OVERVIEW FRONT (LHS)",
            "OVERVIEW FRONT (RHS)",
            "OVERVIEW CABLE CELLAR (LHS)",
            "OVERVIEW CABLE CELLAR (RHS)",
        ),
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="3P1", name="FEEDER 1"),
        ),
    )

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    # Create dummy template file
    (templates_dir / "swg-overview.docx").write_text("dummy")
    (templates_dir / "swg-panel.docx").write_text("dummy")

    adapter = SwitchgearScanAdapter(
        swg=swg_spec,
        substation_info={"substation_name": "TEST", "voltage_type": "33kV"},
        is_33kv=True,
        templates_dir=templates_dir,
    )

    res = adapter.adapt()
    overview_names = [item.component_name for item in res.items if item.is_overview]

    assert "OVERVIEW FRONT (LHS)" in overview_names
    assert "OVERVIEW FRONT (RHS)" in overview_names
    assert "OVERVIEW CABLE CELLAR (LHS)" in overview_names
    assert "OVERVIEW CABLE CELLAR (RHS)" in overview_names


def test_bug_b_scan_adapter_fallback_to_canonical_with_cable_cellar(tmp_path: Path) -> None:
    """Verify SwitchgearScanAdapter falls back to canonical 33kV overviews including Cable Cellar

    when overview_compartments is empty.
    """
    swg_spec = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="VH3",
        rating="33kV",
        overview_compartments=(),  # empty -> fallback
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="3P1", name="FEEDER 1"),
        ),
    )

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "swg-overview.docx").write_text("dummy")
    (templates_dir / "swg-panel.docx").write_text("dummy")

    adapter = SwitchgearScanAdapter(
        swg=swg_spec,
        substation_info={"substation_name": "TEST", "voltage_type": "33kV"},
        is_33kv=True,
        templates_dir=templates_dir,
    )

    res = adapter.adapt()
    overview_names = [item.component_name for item in res.items if item.is_overview]

    assert "OVERVIEW CABLE CELLAR (LHS)" in overview_names
    assert "OVERVIEW CABLE CELLAR (RHS)" in overview_names
    assert len(overview_names) == 12


def test_bug_b_ppu_parser_computes_has_cable_cellar(tmp_path: Path) -> None:
    """Verify extract_testsheet_data computes has_cable_cellar=True on SubstationEquipmentPackage

    when switchgear has CELLAR in overview_compartments.
    """
    wb_path = tmp_path / "05. SSU KPC GEBENG 33kV (VI).xlsx"
    parser = PpuTestsheetParser()

    create_ppu_testsheet_workbook(
        path=wb_path,
        has_33kv=True,
        has_11kv=False,
        panels_33kv=2,
        # Photos on rows 63..68 (RHS) and 69..74 (LHS)
        # Row 66 is Cable Cellar RHS (photo 56), Row 72 is Cable Cellar LHS (photo 57)
        overview_rhs_photos_33kv=[51, 52, 53, 56, 54, 55],
        overview_lhs_photos_33kv=[61, 62, 63, 57, 64, 65],
    )

    data = parser.extract_testsheet_data(wb_path)
    swg = data.equipment.switchgears[0]

    assert "OVERVIEW CABLE CELLAR (LHS)" in swg.overview_compartments
    assert "OVERVIEW CABLE CELLAR (RHS)" in swg.overview_compartments
    # Equipment package must have has_cable_cellar=True
    assert data.equipment.has_cable_cellar is True


def test_bug_b_substation_condition_pairs_from_overview_compartments() -> None:
    """Verify PpuSubstationConditionPairBuilderPolicy includes 33kV CABLE CELLAR

    when has_cable_cellar is False on package, but switchgear has CELLAR in overview_compartments.
    """
    swg_33 = SwitchgearSpec(
        switchgear_type="VCB",
        rating="33kV",
        overview_compartments=("OVERVIEW FRONT (LHS)", "OVERVIEW CABLE CELLAR (RHS)"),
        panels=(SwitchgearPanelSpec(panel_no=1, name="FEEDER 1"),),
    )

    eq = SubstationEquipmentPackage(
        switchgears=(swg_33,),
        has_cable_cellar=False,  # Unset/False explicitly
    )

    data = TestsheetData(
        substation_number=1,
        substation_name_erms="TEST SSU",
        station_name="TEST SSU",
        date_str="2026-10-07",
        equipment=eq,
    )

    pkg = SubstationTestsheetPackage(
        testsheet_path=Path("dummy.xlsx"),
        unsorted_raw_data_dir=Path("."),
        station="TEST SSU",
        month="10",
        date_str="2026-10-07",
        substation_number=1,
        data=data,
    )

    pairs = PpuSubstationConditionPairBuilderPolicy.build(pkg)
    pair_labels = [p[0] for p in pairs]

    assert "33kV CABLE CELLAR" in pair_labels


def test_ticket_116_gps_extracted_from_m3_not_d3(tmp_path: Path) -> None:
    """Verify Ticket #116: GPS coordinate extracted from M3 (adjacent to GPS:), not D3 substation name."""
    parser = PpuTestsheetParser()
    wb_path = tmp_path / "33. MINI PPU KUALA TAHAN 33-11kV.xlsx"

    create_ppu_testsheet_workbook(
        path=wb_path,
        substation_name="MINI PPU KUALA TAHAN 33/11kV",
        gps_coordinate="4.359481, 102.405296",
    )

    data = parser.extract_testsheet_data(wb_path)
    meta = parser.extract_testsheet_metadata(wb_path)

    assert data.gps_coordinate == "4.359481, 102.405296"
    assert meta.gps_coordinate == "4.359481, 102.405296"
    assert data.substation_name_site == "MINI PPU KUALA TAHAN 33/11kV"


# ==============================================================================
# BUG C TESTS: Substation Type Master Enrichment & Local Fallback (Ticket #117)
# ==============================================================================


def test_ticket_117_feedback_loop_assertion(tmp_path: Path) -> None:
    """Feedback loop assertion: Verify CJRT/MPU/G00008 resolves to MPPU

    in plan.pe_info["substation"]["substation_type"] and pe_info["substation"]["type"],
    via local fallback and QR02 CBA enrichment.
    """
    from unittest.mock import MagicMock
    from src.project.environment import ProjectEnvironment
    from src.project.models import ProjectMetadata
    from src.project.storage import LocalWorkspaceStorage
    from src.quick_report.extractor import QuickReportExtractor
    from src.workflows.quick_report import QuickReportWorkflow

    # 1. Local fallback without ENGR CBA: PpuTestsheetParser resolves MINI PPU / MPU to MPPU
    wb_path = tmp_path / "33. MINI PPU KUALA TAHAN 33-11kV.xlsx"
    create_ppu_testsheet_workbook(
        path=wb_path,
        substation_name="MINI PPU KUALA TAHAN 33/11kV",
        fl_number="CJRT/MPU/G00008",
        substation_number=33,
    )
    parser = PpuTestsheetParser()
    data = parser.extract_testsheet_data(wb_path)
    assert data.substation_type == "MPPU", f"Expected MPPU from local fallback, got {data.substation_type!r}"

    # 2. Master QR02 CBA enrichment in QuickReport workflow
    meta = ProjectMetadata(
        key="test_33kv_thunder",
        name="Contract PO 42394550 - THUNDER",
        po_number="PO 42394550",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="Cycle 4",
        technologies=("IR", "US", "TEV"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path, voltage_type="33kV")
    env = ProjectEnvironment(metadata=meta, storage=storage)

    # Synthetic master CBA with Col G=FL, Col H=Name, Col I=Type
    cba_path = tmp_path / "PYTHON" / "ENGR FROM DRIVE" / "ENGR-750-39 -CBA-PAHANG - 2026.xlsx"
    cba_path.parent.mkdir(parents=True, exist_ok=True)
    import openpyxl
    wb_cba = openpyxl.Workbook()
    ws_cba = wb_cba.active
    ws_cba.title = "QR02 CBA"
    ws_cba.append(["NO", "DISTRICT", "ZONE", "STATION CODE", "CYCLE", "VOLTAGE", "FUNCTIONAL LOCATION", "SUBSTATION NAME", "TYPE", "SYSTEM"])
    ws_cba.append([1, "JERANTUT", "CJRT", "MPU", 4, "33kV", "CJRT/MPU/G00008", "MINI PPU KUALA TAHAN 33/11kV", "MPPU", "33/11"])
    wb_cba.save(cba_path)
    wb_cba.close()

    pkg = SubstationTestsheetPackage(
        testsheet_path=wb_path,
        unsorted_raw_data_dir=tmp_path / "raw",
        station="JERANTUT",
        month="OCTOBER",
        date_str="22-10-2026",
        substation_number=33,
        data=data,
    )

    extractor = QuickReportExtractor()
    workflow = QuickReportWorkflow(extractor=extractor)
    extractor.extract = MagicMock(return_value=[pkg])
    extractor.extract_defects = MagicMock(return_value=([], []))
    env.get_vi_front_page_template = MagicMock(return_value=tmp_path / "fp.docx")
    env.get_template = MagicMock(return_value=tmp_path / "sticker.docx")

    inspection, plans = workflow._plan("CJRT/MPU/G00008", env)
    assert len(plans) == 1
    plan = plans[0]

    # Feedback loop core assertions
    assert plan.pe_info["substation"]["substation_type"] == "MPPU"
    assert plan.pe_info["substation"]["type"] == "MPPU"
    assert inspection.targets[0].substation_type == "MPPU"

    # Front page docx rendering verification
    front_page_template = Path("templates/QUICK REPORT/1. FRONT PAGE TEMPLATE IR US TEV BOX Jinja2 updated.docx")
    if front_page_template.exists():
        from src.quick_report.front_page import generate_front_page
        import docx
        out_fp = generate_front_page(plan.pe_info, front_page_template, tmp_path, substation_number=33)
        assert out_fp.exists()
        doc = docx.Document(out_fp)
        doc_text = " ".join([p.text for p in doc.paragraphs] + [c.text for t in doc.tables for row in t.rows for c in row.cells])
        assert "MPPU" in doc_text


# ==============================================================================
# BUG D TESTS: PT Compartment Elimination on Panels 1-4 for Kuala Tahan (Ticket #121)
# ==============================================================================


def test_ticket_121_pt_compartment_elimination_kuala_tahan(tmp_path: Path) -> None:
    """Ticket #121: Verify PT COMPARTMENT elimination on Panels 1-4 and preservation on Panel 5

    for MINI PPU KUALA TAHAN 33/11kV (CJRT/MPU/G00008).
    Validates:
    1. Table 2 Census in Part 01: Panels 1-4 have only
       ("BREAKER COMPARTMENT", "CABLE COMPARTMENT", "BUSBAR COMPARTMENT", "SECONDARY COMPARTMENT"),
       while Panel 5 has ("BREAKER COMPARTMENT", "CABLE COMPARTMENT", "BUSBAR COMPARTMENT", "PT COMPARTMENT", "SECONDARY COMPARTMENT").
    2. Part 02 (Panel 1 - LOCAL TX): Contains NO PT COMPARTMENT scan page.
    3. Part 03 (Panel 2 - SPARE): Contains NO PT COMPARTMENT scan page.
    4. Part 04 (Panel 3 - PE SM K.TAHAN): Contains NO PT COMPARTMENT scan page.
    5. Part 05 (Panel 4 - PE PERSONA): Contains NO PT COMPARTMENT scan page.
    6. Part 06 (Panel 5 - TX 5MVA): Contains valid PT COMPARTMENT scan page with Photo #57 and measurements.
    7. Deliverable Word documents on disk match the expected compartment structure.
    """
    import docx

    # --------------------------------------------------------------------------
    # 1. On-disk deliverable Word documents verification
    # --------------------------------------------------------------------------
    deliverables_dir = Path(
        r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\FULL REPORT\JERANTUT\01. OCTOBER\22-10-2026"
    )

    if deliverables_dir.exists():
        part1_path = deliverables_dir / "33. MINI PPU KUALA TAHAN 3311kV (VI) - Part 01 - Summary.docx"
        part2_path = deliverables_dir / "33. MINI PPU KUALA TAHAN 3311kV (VI) - Part 02 - Panel 1 (11kV - LOCAL TX).docx"
        part3_path = deliverables_dir / "33. MINI PPU KUALA TAHAN 3311kV (VI) - Part 03 - Panel 2 (11kV - SPARE).docx"
        part4_path = deliverables_dir / "33. MINI PPU KUALA TAHAN 3311kV (VI) - Part 04 - Panel 3 (11kV - PE SM K.TAHAN).docx"
        part5_path = deliverables_dir / "33. MINI PPU KUALA TAHAN 3311kV (VI) - Part 05 - Panel 4 (11kV - PE PERSONA).docx"
        part6_path = deliverables_dir / "33. MINI PPU KUALA TAHAN 3311kV (VI) - Part 06 - Panel 5 (11kV - TX 5MVA).docx"
        part7_path = deliverables_dir / "33. MINI PPU KUALA TAHAN 3311kV (VI) - Part 07 - TX and Condition.docx"

        assert part1_path.exists(), f"Part 01 deliverable missing at {part1_path}"
        assert part2_path.exists(), f"Part 02 deliverable missing at {part2_path}"
        assert part3_path.exists(), f"Part 03 deliverable missing at {part3_path}"
        assert part4_path.exists(), f"Part 04 deliverable missing at {part4_path}"
        assert part5_path.exists(), f"Part 05 deliverable missing at {part5_path}"
        assert part6_path.exists(), f"Part 06 deliverable missing at {part6_path}"
        assert part7_path.exists(), f"Part 07 deliverable missing at {part7_path}"

        # 1.1 Verify Part 01 - Summary: Table 2 Census
        doc1 = docx.Document(part1_path)
        census_table = None
        for t in doc1.tables:
            header_text = " ".join(c.text.strip() for c in t.rows[0].cells)
            if "FEEDER" in header_text or "COMPARTMENT" in header_text:
                census_table = t
                break
        if census_table is None and len(doc1.tables) > 2:
            census_table = doc1.tables[2]
        assert census_table is not None, "Table 2 Census not found in Part 01 - Summary.docx"

        panel_census_comps: dict[str, list[str]] = {}
        curr_panel: str | None = None
        for row in census_table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            if len(cells) > 2 and cells[1] and cells[1] != "FEEDER / PANEL NAME":
                curr_panel = cells[1]
                comp = cells[2]
                panel_census_comps.setdefault(curr_panel, []).append(comp)
            elif len(cells) > 2 and curr_panel and cells[2]:
                comp = cells[2]
                panel_census_comps.setdefault(curr_panel, []).append(comp)

        expected_panels_1_to_4 = [
            "PANEL 7 LOCAL TX",
            "PANEL 5 SPARE",
            "PANEL 3 PE SM K.TAHAN",
            "PANEL 1 PE PERSONA",
        ]
        for p_name in expected_panels_1_to_4:
            assert p_name in panel_census_comps, f"Panel {p_name} missing from Table 2 Census"
            comps = panel_census_comps[p_name]
            assert "PT COMPARTMENT" not in comps, f"PT COMPARTMENT found in {p_name} census: {comps}"
            assert comps == [
                "BREAKER COMPARTMENT",
                "CABLE COMPARTMENT",
                "BUSBAR COMPARTMENT",
                "SECONDARY COMPARTMENT",
            ]

        assert "PANEL 31 TX 5MVA" in panel_census_comps, "PANEL 31 TX 5MVA missing from Table 2 Census"
        panel5_comps = panel_census_comps["PANEL 31 TX 5MVA"]
        assert "PT COMPARTMENT" in panel5_comps, "PT COMPARTMENT missing from PANEL 31 TX 5MVA census"
        assert panel5_comps == [
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "PT COMPARTMENT",
            "SECONDARY COMPARTMENT",
        ]

        # 1.2 Verify Parts 02 to 05 contain NO PT COMPARTMENT scan page
        panel_docs = [
            (part2_path, "Panel 1 - LOCAL TX"),
            (part3_path, "Panel 2 - SPARE"),
            (part4_path, "Panel 3 - PE SM K.TAHAN"),
            (part5_path, "Panel 4 - PE PERSONA"),
        ]
        for doc_path, panel_label in panel_docs:
            doc = docx.Document(doc_path)
            all_text = " ".join(
                [p.text for p in doc.paragraphs]
                + [c.text for t in doc.tables for r in t.rows for c in r.cells]
            )
            assert "PT COMPARTMENT" not in all_text, (
                f"{panel_label} ({doc_path.name}) contains 'PT COMPARTMENT'"
            )
            # Verify exactly 4 scan tables (BREAKER, CABLE, BUSBAR, SECONDARY)
            scan_tables = []
            for t in doc.tables:
                for r in t.rows:
                    row_texts = [c.text.strip() for c in r.cells]
                    if "Area" in row_texts:
                        distinct = [x for x in dict.fromkeys(row_texts) if x]
                        scan_tables.append(distinct)
                        break
            assert len(scan_tables) == 4, f"{panel_label} expected 4 scan tables, got {len(scan_tables)}"
            table_areas = [st[1] for st in scan_tables if len(st) > 1]
            assert table_areas == [
                "BREAKER COMPARTMENT",
                "CABLE COMPARTMENT",
                "BUSBAR COMPARTMENT",
                "SECONDARY COMPARTMENT",
            ]

        # 1.3 Verify Part 06 (Panel 5 - TX 5MVA) contains valid PT COMPARTMENT scan page
        doc6 = docx.Document(part6_path)
        scan_tables_p6 = []
        pt_table = None
        for t in doc6.tables:
            for r in t.rows:
                row_texts = [c.text.strip() for c in r.cells]
                if "Area" in row_texts:
                    distinct = [x for x in dict.fromkeys(row_texts) if x]
                    scan_tables_p6.append(distinct)
                    if "PT COMPARTMENT" in distinct:
                        pt_table = t
                    break

        assert len(scan_tables_p6) == 5, f"Panel 5 expected 5 scan tables, got {len(scan_tables_p6)}"
        p6_areas = [st[1] for st in scan_tables_p6 if len(st) > 1]
        assert p6_areas == [
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "PT COMPARTMENT",
            "SECONDARY COMPARTMENT",
        ]
        assert pt_table is not None, "PT COMPARTMENT scan table not found in Part 06"

        pt_table_text = " ".join([c.text.strip() for r in pt_table.rows for c in r.cells])
        assert "PT COMPARTMENT" in pt_table_text
        assert "TX 5MVA" in pt_table_text
        assert "46.1" in pt_table_text  # Sp1 measurement
        assert "45.4" in pt_table_text  # Sp2 measurement
        assert "44.3" in pt_table_text  # Ar1 measurement
        assert "34.0" in pt_table_text  # Ambient temp measurement
        assert "47" in pt_table_text    # Load measurement
        assert "0dB" in pt_table_text   # Ultrasound measurement

        # Check testsheet photo #57
        ts_path = Path(
            r"C:\Users\ADAM\Documents\PO 42394550 - PAHANG - 33kV - THUNDER\TESTSHEET\JERANTUT\01. OCTOBER\22-10-2026\33. MINI PPU KUALA TAHAN 33-11kV (VI).xlsx"
        )
        if ts_path.exists():
            ts_data = PpuTestsheetParser().extract_testsheet_data(ts_path)
            swg = ts_data.equipment.switchgears[0]
            assert len(swg.panels) == 5
            for p in swg.panels[:4]:
                assert p.has_pt_measurement is False
                assert p.pt_photo is None
            p5 = swg.panels[4]
            assert p5.has_pt_measurement is True
            assert p5.pt_photo == 57

    # --------------------------------------------------------------------------
    # 2. Synthetic Unit / Regression Pipeline Verification
    # --------------------------------------------------------------------------
    wb_synthetic = tmp_path / "33. MINI PPU KUALA TAHAN 33-11kV SYNTHETIC.xlsx"
    create_ppu_testsheet_workbook(
        path=wb_synthetic,
        substation_name="MINI PPU KUALA TAHAN 33/11kV",
        fl_number="CJRT/MPU/G00008",
        substation_number=33,
        has_33kv=False,
        has_11kv=True,
        panels_11kv=[
            {"feeder_no": "7", "name": "LOCAL TX", "has_pt_measurement": False},
            {"feeder_no": "5", "name": "SPARE", "has_pt_measurement": False},
            {"feeder_no": "3", "name": "PE SM K.TAHAN", "has_pt_measurement": False},
            {"feeder_no": "1", "name": "PE PERSONA", "has_pt_measurement": False},
            {"feeder_no": "31", "name": "TX 5MVA", "has_pt_measurement": True, "pt_photo": 57},
        ],
    )

    synth_data = PpuTestsheetParser().extract_testsheet_data(wb_synthetic)
    synth_swg = synth_data.equipment.switchgears[0]
    assert len(synth_swg.panels) == 5

    for p in synth_swg.panels[:4]:
        assert p.has_pt_measurement is False
        assert p.pt_photo is None
        comps = SwitchgearTopologyEngine.resolve_panel_compartments(
            archetype=SwitchgearArchetype.VCB_CUBICLE,
            panel=p,
            voltage_class=VoltageClass.KV_11,
            is_33kv=False,
        )
        assert "PT COMPARTMENT" not in comps
        assert comps == (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )

    p5_synth = synth_swg.panels[4]
    assert p5_synth.has_pt_measurement is True
    assert p5_synth.pt_photo == 57
    comps5 = SwitchgearTopologyEngine.resolve_panel_compartments(
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        panel=p5_synth,
        voltage_class=VoltageClass.KV_11,
        is_33kv=False,
    )
    assert "PT COMPARTMENT" in comps5
    assert comps5 == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "PT COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )



