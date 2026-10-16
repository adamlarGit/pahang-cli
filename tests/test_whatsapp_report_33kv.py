"""Unit and integration tests for 33kV WhatsApp Daily Report generation (Ticket #099)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import docx
import openpyxl
import pandas as pd
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
import config
from src.whatsapp.models import WhatsAppReportResources
from src.workflows.models import WhatsAppReportRequest
from src.workflows.whatsapp import (
    DEFECT_SUFFIX_PATTERN,
    QUALIFYING_DOCX_PATTERN,
    WHATSAPP_ACTIVITY_11KV,
    WHATSAPP_ACTIVITY_33KV,
    WHATSAPP_LINKS_11KV,
    WHATSAPP_LINKS_33KV,
    WHATSAPP_PENYELIA_11KV,
    WHATSAPP_PENYELIA_33KV,
    WhatsAppReportAuditor,
    WhatsAppReportExtractor,
    WhatsAppReportFilter,
    WhatsAppReportLoader,
    WhatsAppReportPlan,
    WhatsAppReportPreflightGuard,
    WhatsAppReportTransformer,
    WhatsAppReportWorkflow,
    WhatsAppRawTuple,
    WhatsAppTargetEntity,
    run_generate_whatsapp_report,
)


def _create_33kv_total_pe(total_pe_path: Path) -> None:
    """Create synthetic 33kV TOTAL PE workbook with DataCycle1 matching production schema."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DataCycle1"
    ws.append(["PE NO", "FL NUMBER", "SUBSTATION NAME", "DATE", "TYPE", "WO", "SCOPE"])
    ws.append([1, "CGBG/PPU/G00001", "PPU APMM 33/11kV", datetime(2026, 10, 7), "PPU", "W1616898", "FULL"])
    ws.append([2, "CKTN/SSU/G00006", "SSU KIIP (SSU CAMEL POWER) 33kV", datetime(2026, 10, 7), "SSU", "W1616956", "FULL"])
    ws.append([3, "CGBG/SSU/G00003", "SSU LYNAS 33kV", datetime(2026, 10, 7), "SSU", "W1616922", "FULL"])
    ws.append([4, "CGBG/SSU/G00005", "SSU FERRO MANGANESE 33kV", datetime(2026, 10, 7), "SSU", "W1616924", "FULL"])
    # Row with float PE number and missing WO
    ws.append([5.0, "CGBG/SSU/G00006", "SSU KPC GEBENG 33kV", datetime(2026, 10, 8), "SSU", None, "FULL"])
    wb.save(total_pe_path)
    wb.close()


def test_qualifying_docx_pattern_internal_parentheses() -> None:
    """Verify regex preserves internal parentheses and anchors defects to trailing parentheses."""
    # Internal parenthesis with defect suffix
    m1 = QUALIFYING_DOCX_PATTERN.match("02. SSU KIIP (SSU CAMEL POWER) 33kV (VI).docx")
    assert m1 is not None
    assert m1.group(1) == "02"
    assert m1.group(2) == "SSU KIIP (SSU CAMEL POWER) 33kV"
    assert m1.group(3) == "VI"

    # Internal parenthesis without defect suffix
    m2 = QUALIFYING_DOCX_PATTERN.match("02. SSU KIIP (SSU CAMEL POWER) 33kV.docx")
    assert m2 is not None
    assert m2.group(1) == "02"
    assert m2.group(2) == "SSU KIIP (SSU CAMEL POWER) 33kV"
    assert m2.group(3) is None

    # Multiple parenthesized tokens in name with defect suffix
    m_nested = QUALIFYING_DOCX_PATTERN.match("02. SSU KIIP (SSU CAMEL POWER) (PHASE 1) (VI).docx")
    assert m_nested is not None
    assert m_nested.group(1) == "02"
    assert m_nested.group(2) == "SSU KIIP (SSU CAMEL POWER) (PHASE 1)"
    assert m_nested.group(3) == "VI"

    # Multi-technology defect suffix
    m3 = QUALIFYING_DOCX_PATTERN.match("01. PPU APMM 33/11kV (US+VI).docx")
    assert m3 is not None
    assert m3.group(1) == "01"
    assert m3.group(2) == "PPU APMM 33/11kV"
    assert m3.group(3) == "US+VI"

    m4 = QUALIFYING_DOCX_PATTERN.match("03. SSU FERRO MANGANESE 33kV (IR+VI).docx")
    assert m4 is not None
    assert m4.group(1) == "03"
    assert m4.group(2) == "SSU FERRO MANGANESE 33kV"
    assert m4.group(3) == "IR+VI"

    m_all = QUALIFYING_DOCX_PATTERN.match("04. SSU FERRO MANGANESE 33kV (IR+US+TEV+VI).docx")
    assert m_all is not None
    assert m_all.group(3) == "IR+US+TEV+VI"

    # Non-docx files should not match
    assert QUALIFYING_DOCX_PATTERN.match("01. PPU APMM.pdf") is None
    assert QUALIFYING_DOCX_PATTERN.match("desktop.ini") is None


def test_cross_station_date_folder_discovery_and_sorting(tmp_path: Path) -> None:
    """Verify WhatsAppReportExtractor aggregates across station directories and sorts by PE int."""
    qr_dir = tmp_path / "QUICK REPORT"
    date_str = "07-10-2026"
    
    # Interleaved multi-station layout: GEBENG (PE 1, 3, 4) and KUANTAN (PE 2)
    gebeng_dir = qr_dir / "GEBENG" / "10. OCTOBER" / date_str
    gebeng_dir.mkdir(parents=True)
    (gebeng_dir / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")
    (gebeng_dir / "04. SSU FERRO MANGANESE 33kV (VI).docx").write_bytes(b"dummy")
    (gebeng_dir / "03. SSU LYNAS 33kV (VI).docx").write_bytes(b"dummy")

    # Station 2: KUANTAN (PE 2)
    kuantan_dir = qr_dir / "KUANTAN" / "10. OCTOBER" / date_str
    kuantan_dir.mkdir(parents=True)
    (kuantan_dir / "02. SSU KIIP (SSU CAMEL POWER) 33kV (VI).docx").write_bytes(b"dummy")

    # Other date: should be excluded
    other_date_dir = qr_dir / "GEBENG" / "10. OCTOBER" / "08-10-2026"
    other_date_dir.mkdir(parents=True)
    (other_date_dir / "05. SSU KPC GEBENG 33kV.docx").write_bytes(b"dummy")

    total_pe_path = tmp_path / "TOTAL PE.xlsx"
    _create_33kv_total_pe(total_pe_path)

    metadata = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV 2026",
        po_number="PO42394550",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    env = ProjectEnvironment(metadata=metadata, storage=storage)

    resources = WhatsAppReportResources(
        quick_report_dir=qr_dir,
        save_dir=tmp_path / "PYTHON" / "WHATSAPP",
        template_path=tmp_path / "TEMPLATE.docx",
        total_pe_path=total_pe_path,
        station_mapping={"CGBG": "GEBENG", "CKTN": "KUANTAN"},
        voltage_type="33kV",
    )
    env.get_whatsapp_report_resources = lambda: resources

    extractor = WhatsAppReportExtractor()
    # Invoke by passing gebeng_dir as report_dir (date 07-10-2026)
    request = WhatsAppReportRequest(report_dir=gebeng_dir)
    raw = extractor.extract(env, request)

    # 4 files discovered across GEBENG and KUANTAN, 08-10-2026 excluded, sorted by PE integer
    assert len(raw.substation_docx_files) == 4
    file_names = [p.name for p in raw.substation_docx_files]
    assert file_names == [
        "01. PPU APMM 33-11kV (VI).docx",
        "02. SSU KIIP (SSU CAMEL POWER) 33kV (VI).docx",
        "03. SSU LYNAS 33kV (VI).docx",
        "04. SSU FERRO MANGANESE 33kV (VI).docx",
    ]
    assert raw.station_hints[raw.substation_docx_files[0]] == "GEBENG"
    assert raw.station_hints[raw.substation_docx_files[1]] == "KUANTAN"
    assert raw.station_hints[raw.substation_docx_files[2]] == "GEBENG"
    assert raw.station_hints[raw.substation_docx_files[3]] == "GEBENG"


def test_whatsapp_filter_33kv() -> None:
    """Verify WhatsAppReportFilter extracts PE integer, WONUM, defect suffix, handles non-defect parens and date fallback."""
    df = pd.DataFrame([
        {"PE NO": 1, "SUBSTATION NAME": "PPU APMM", "WO": "W1616898", "DATE": datetime(2026, 10, 7), "FL NUMBER": "CGBG/PPU/G00001"},
        {"PE NO": "2.0", "SUBSTATION NAME": "SSU LYNAS", "WO": 40012345.0, "DATE": datetime(2026, 10, 7), "FL NUMBER": "CGBG/SSU/G00002"},
        {"PE NO": 3, "SUBSTATION NAME": "SSU FERRO", "WO": None, "DATE": datetime(2026, 10, 7), "FL NUMBER": "CGBG/SSU/G00003"},
        # PE 4 has unpopulated DATE in TOTAL PE, should fallback to folder_date
        {"PE NO": 4, "SUBSTATION NAME": None, "WO": "W1616956", "DATE": None, "FL NUMBER": "CKTN/SSU/G00004"},
    ])
    raw = WhatsAppRawTuple(
        substation_docx_files=[
            Path("01. PPU APMM (VI).docx"),
            Path("02. SSU LYNAS (US+VI).docx"),
            Path("03. SSU FERRO.docx"),
            Path("04. SSU KULIM (OLD).docx"),  # Non-defect trailing parens
        ],
        total_pe_df=df,
        resources=WhatsAppReportResources(
            quick_report_dir=Path("/qr"),
            save_dir=Path("/save"),
            template_path=Path("/template.docx"),
            total_pe_path=Path("/total_pe.xlsx"),
            station_mapping={"CGBG": "GEBENG", "CKTN": "KUANTAN"},
            voltage_type="33kV",
        ),
        station_hints={
            Path("01. PPU APMM (VI).docx"): "GEBENG",
            Path("02. SSU LYNAS (US+VI).docx"): "GEBENG",
            Path("03. SSU FERRO.docx"): "GEBENG",
            Path("04. SSU KULIM (OLD).docx"): "KUANTAN",
        },
        folder_date="07-10-2026",
    )

    stage = WhatsAppReportFilter()
    targets = stage.filter(raw)

    assert len(targets) == 4
    # PE 1
    assert targets[0].substation_number == 1
    assert targets[0].substation_name == "PPU APMM"
    assert targets[0].defect == "VI"
    assert targets[0].msms == "W1616898"
    assert targets[0].station == "GEBENG"

    # PE 2: WO float normalized to clean integer string
    assert targets[1].substation_number == 2
    assert targets[1].defect == "US+VI"
    assert targets[1].msms == "40012345"

    # PE 3: Unpopulated WO rendered as "-" and defect as "-"
    assert targets[2].substation_number == 3
    assert targets[2].defect == "-"
    assert targets[2].msms == "-"

    # PE 4: (OLD) is not a defect -> retained in substation name, defect="-", date falls back to folder_date
    assert targets[3].substation_number == 4
    assert targets[3].substation_name == "SSU KULIM (OLD)"
    assert targets[3].defect == "-"
    assert targets[3].raw_date == "07-10-2026"
    assert targets[3].station == "KUANTAN"


def test_whatsapp_transformer_multi_station_grouping_and_links() -> None:
    """Verify multi-station grouping header, subheadings, continuous indexing, and 33kV links even with interleaved targets."""
    # Interleaved input: PE 1 (GEBENG), PE 2 (KUANTAN), PE 3 (GEBENG), PE 4 (GEBENG)
    targets = [
        WhatsAppTargetEntity(
            substation_number=1,
            substation_name="PPU APMM 33/11kV",
            defect="VI",
            msms="W1616898",
            raw_date=datetime(2026, 10, 7),
            fl_number="CGBG/PPU/G00001",
            station="GEBENG",
        ),
        WhatsAppTargetEntity(
            substation_number=2,
            substation_name="SSU KIIP (SSU CAMEL POWER) 33kV",
            defect="VI",
            msms="W1616956",
            raw_date=datetime(2026, 10, 7),
            fl_number="CKTN/SSU/G00004",
            station="KUANTAN",
        ),
        WhatsAppTargetEntity(
            substation_number=3,
            substation_name="SSU LYNAS 33kV",
            defect="VI",
            msms="W1616922",
            raw_date=datetime(2026, 10, 7),
            fl_number="CGBG/SSU/G00002",
            station="GEBENG",
        ),
        WhatsAppTargetEntity(
            substation_number=4,
            substation_name="SSU FERRO MANGANESE 33kV",
            defect="VI",
            msms="W1616924",
            raw_date=datetime(2026, 10, 7),
            fl_number="CGBG/SSU/G00003",
            station="GEBENG",
        ),
    ]

    resources = WhatsAppReportResources(
        quick_report_dir=Path("/qr"),
        save_dir=Path("/save"),
        template_path=Path("/template.docx"),
        total_pe_path=Path("/total_pe.xlsx"),
        station_mapping={"CGBG": "GEBENG", "CKTN": "KUANTAN"},
        voltage_type="33kV",
    )

    transformer = WhatsAppReportTransformer()
    plan = transformer.transform(targets, resources)

    assert plan.station_name == "GEBENG/KUANTAN"
    assert plan.report_date == "07/10/2026"
    assert plan.voltage_type == "33kV"

    ctx = plan.context
    assert ctx["activity"] == WHATSAPP_ACTIVITY_33KV  # "CBM 33KV"
    assert ctx["penyelia"] == WHATSAPP_PENYELIA_33KV  # "ZULHUSNI"
    assert ctx["station"] == "GEBENG/KUANTAN"
    assert ctx["show_subheadings"] is True
    assert ctx["link_laporan"] == WHATSAPP_LINKS_33KV["laporan"]
    assert ctx["link_engr"] == WHATSAPP_LINKS_33KV["engr"]

    # Verify grouping: all GEBENG items grouped together first (items 1, 2, 3), then KUANTAN (item 4)
    items = ctx["items"]
    assert len(items) == 4
    # Item 1: GEBENG (PE 1)
    assert items[0]["index"] == 1
    assert items[0]["name"] == "PPU APMM 33/11kV"
    assert items[0]["station_header"] == "GEBENG"
    # Item 2: GEBENG (PE 3)
    assert items[1]["index"] == 2
    assert items[1]["name"] == "SSU LYNAS 33kV"
    assert items[1]["station_header"] is None
    # Item 3: GEBENG (PE 4)
    assert items[2]["index"] == 3
    assert items[2]["name"] == "SSU FERRO MANGANESE 33kV"
    assert items[2]["station_header"] is None
    # Item 4: KUANTAN (PE 2)
    assert items[3]["index"] == 4
    assert items[3]["name"] == "SSU KIIP (SSU CAMEL POWER) 33kV"
    assert items[3]["station_header"] == "KUANTAN"

    # Verify station_groups structure
    assert len(ctx["station_groups"]) == 2
    assert ctx["station_groups"][0]["station"] == "GEBENG"
    assert len(ctx["station_groups"][0]["items"]) == 3
    assert ctx["station_groups"][1]["station"] == "KUANTAN"
    assert len(ctx["station_groups"][1]["items"]) == 1


def test_whatsapp_transformer_single_station_no_subheadings() -> None:
    """Verify single-station on a date renders without subheadings."""
    targets = [
        WhatsAppTargetEntity(
            substation_number=1,
            substation_name="SSU KPC GEBENG 33kV",
            defect="VI",
            msms="W1616933",
            raw_date=datetime(2026, 10, 8),
            fl_number="CGBG/SSU/G00005",
            station="GEBENG",
        ),
        WhatsAppTargetEntity(
            substation_number=2,
            substation_name="SSU FLEXSYS CHEMICAL 33kV",
            defect="VI",
            msms="W1616923",
            raw_date=datetime(2026, 10, 8),
            fl_number="CGBG/SSU/G00006",
            station="GEBENG",
        ),
    ]

    resources = WhatsAppReportResources(
        quick_report_dir=Path("/qr"),
        save_dir=Path("/save"),
        template_path=Path("/template.docx"),
        total_pe_path=Path("/total_pe.xlsx"),
        station_mapping={"CGBG": "GEBENG"},
        voltage_type="33kV",
    )

    transformer = WhatsAppReportTransformer()
    plan = transformer.transform(targets, resources)

    assert plan.station_name == "GEBENG"
    assert plan.context["station"] == "GEBENG"
    assert plan.context["show_subheadings"] is False
    assert plan.context["items"][0]["station_header"] is None
    assert plan.context["items"][1]["station_header"] is None


def test_whatsapp_loader_output_filename_33kv(tmp_path: Path) -> None:
    """Verify 33kV filename is formatted strictly as '{NN}. {clean_date}.docx'."""
    template_path = tmp_path / "template.docx"
    doc = docx.Document()
    doc.add_paragraph("Test WhatsApp Report")
    doc.save(template_path)

    save_dir = tmp_path / "PYTHON" / "WHATSAPP"
    loader = WhatsAppReportLoader()

    # 1. 33kV Plan: {NN}. {clean_date}.docx (e.g. 01. 07-10-2026.docx)
    plan_33kv = WhatsAppReportPlan(
        template_path=template_path,
        save_dir=save_dir,
        context={"date": "07/10/2026", "station": "GEBENG/KUANTAN", "items": []},
        substations_count=0,
        station_name="GEBENG/KUANTAN",
        report_date="07/10/2026",
        voltage_type="33kV",
    )
    out1 = loader.load(plan_33kv)
    assert out1.name == "01. 07-10-2026.docx"

    # Second file on next date increments to 02.
    plan_33kv_2 = WhatsAppReportPlan(
        template_path=template_path,
        save_dir=save_dir,
        context={"date": "08/10/2026", "station": "GEBENG", "items": []},
        substations_count=0,
        station_name="GEBENG",
        report_date="08/10/2026",
        voltage_type="33kV",
    )
    out2 = loader.load(plan_33kv_2)
    assert out2.name == "02. 08-10-2026.docx"

    # 2. 11kV Plan: preserves {NN}. {station} {clean_date}.docx
    plan_11kv = WhatsAppReportPlan(
        template_path=template_path,
        save_dir=save_dir,
        context={"date": "01/05/2026", "station": "CAMERON HIGHLAND", "items": []},
        substations_count=0,
        station_name="CAMERON HIGHLAND",
        report_date="01/05/2026",
        voltage_type="11kV",
    )
    out3 = loader.load(plan_11kv)
    assert out3.name == "03. CAMERON HIGHLAND 01-05-2026.docx"


def test_whatsapp_preflight_guard_33kv(tmp_path: Path) -> None:
    """Verify preflight guard cross-station date directory validation in 33kV."""
    qr_dir = tmp_path / "QUICK REPORT"
    target_date = "07-10-2026"
    gebeng_dir = qr_dir / "GEBENG" / "10. OCTOBER" / target_date
    gebeng_dir.mkdir(parents=True)
    (gebeng_dir / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")

    total_pe_path = tmp_path / "TOTAL PE.xlsx"
    _create_33kv_total_pe(total_pe_path)

    template_path = tmp_path / "TEMPLATE.docx"
    docx.Document().save(template_path)

    metadata = ProjectMetadata(
        key="pahang_33kv",
        name="Pahang 33kV",
        po_number="PO42394550",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    env = ProjectEnvironment(metadata=metadata, storage=storage)

    resources = WhatsAppReportResources(
        quick_report_dir=qr_dir,
        save_dir=tmp_path / "PYTHON" / "WHATSAPP",
        template_path=template_path,
        total_pe_path=total_pe_path,
        station_mapping={"CGBG": "GEBENG"},
        voltage_type="33kV",
    )
    env.get_whatsapp_report_resources = lambda: resources

    guard = WhatsAppReportPreflightGuard()
    # 1. Valid: gebeng_dir exists with qualifying files
    guard.validate(env, WhatsAppReportRequest(report_dir=gebeng_dir))

    # 2. Valid: invoked with target_date string as report_dir
    guard.validate(env, WhatsAppReportRequest(report_dir=Path(target_date)))

    # 3. Invalid: date with no docx files anywhere raises ValueError
    empty_date = qr_dir / "GEBENG" / "10. OCTOBER" / "09-10-2026"
    empty_date.mkdir(parents=True)
    with pytest.raises(ValueError, match="No qualifying PE DOCX files"):
        guard.validate(env, WhatsAppReportRequest(report_dir=empty_date))

    # 4. Invalid: date folder does not exist raises FileNotFoundError
    with pytest.raises(FileNotFoundError, match="Directory not found"):
        guard.validate(env, WhatsAppReportRequest(report_dir=Path("31-12-2099")))


def test_e2e_generate_whatsapp_report_33kv(tmp_path: Path) -> None:
    """Full end-to-end integration test rendering 33kV multi-station daily WhatsApp report."""
    root_path = tmp_path / "workspace"
    qr_dir = root_path / "QUICK REPORT"
    python_dir = root_path / "PYTHON"
    target_date = "07-10-2026"

    # Multi-station layout with interleaved PE numbers: GEBENG (PE 1, 3, 4) and KUANTAN (PE 2)
    gebeng_dir = qr_dir / "GEBENG" / "10. OCTOBER" / target_date
    kuantan_dir = qr_dir / "KUANTAN" / "10. OCTOBER" / target_date
    gebeng_dir.mkdir(parents=True)
    kuantan_dir.mkdir(parents=True)
    python_dir.mkdir(parents=True)

    (gebeng_dir / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")
    (gebeng_dir / "03. SSU LYNAS 33kV (VI).docx").write_bytes(b"dummy")
    (gebeng_dir / "04. SSU FERRO MANGANESE 33kV (VI).docx").write_bytes(b"dummy")
    (kuantan_dir / "02. SSU KIIP (SSU CAMEL POWER) 33kV (VI).docx").write_bytes(b"dummy")

    total_pe_path = python_dir / "TOTAL PE.xlsx"
    _create_33kv_total_pe(total_pe_path)

    # Use master template from repo
    real_template = Path(__file__).parent.parent / "templates" / "WHATSAPP" / "TEMPLATE WHATSAPP PYTHON.docx"
    template_path = tmp_path / "TEMPLATE WHATSAPP PYTHON.docx"
    template_path.write_bytes(real_template.read_bytes())

    metadata = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV 2026",
        po_number="PO42394550",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
        base_path=str(root_path),
    )
    storage = LocalWorkspaceStorage(root_path, templates_dir=template_path.parent)
    env = ProjectEnvironment(metadata=metadata, storage=storage)

    resources = WhatsAppReportResources(
        quick_report_dir=qr_dir,
        save_dir=python_dir / "WHATSAPP",
        template_path=template_path,
        total_pe_path=total_pe_path,
        station_mapping={"CGBG": "GEBENG", "CKTN": "KUANTAN"},
        voltage_type="33kV",
    )
    env.get_whatsapp_report_resources = lambda: resources

    result = run_generate_whatsapp_report(env, gebeng_dir)

    assert result.substations_count == 4
    assert result.output_path is not None
    assert result.output_path.exists()
    assert result.output_path.name == "01. 07-10-2026.docx"

    # Verify rendered document contents
    output_doc = docx.Document(result.output_path)
    doc_text = "\n".join(p.text for p in output_doc.paragraphs if p.text.strip())

    assert "AKTIVITI : *CBM 33KV*" in doc_text
    assert "TARIKH : *07/10/2026*" in doc_text
    assert "STATION : *GEBENG/KUANTAN*" in doc_text
    assert "PENYELIA : *ZULHUSNI*" in doc_text

    # Grouping subheadings and continuous sequential numbering
    assert doc_text.count("*GEBENG*") == 1
    assert doc_text.count("*KUANTAN*") == 1
    assert "*GEBENG*" in doc_text
    assert "1. PPU APMM 33/11kV" in doc_text
    assert "2. SSU LYNAS 33kV" in doc_text
    assert "3. SSU FERRO MANGANESE 33kV" in doc_text
    assert "*KUANTAN*" in doc_text
    assert "4. SSU KIIP (SSU CAMEL POWER) 33kV" in doc_text

    # Defect and MSMS
    assert "DEFECT : VI" in doc_text
    assert "MSMS : W1616898" in doc_text
    assert "MSMS : W1616956" in doc_text

    # Links
    assert "Link Laporan:" in doc_text
    assert WHATSAPP_LINKS_33KV["laporan"] in doc_text
    assert "Link ENGR:" in doc_text
    assert WHATSAPP_LINKS_33KV["engr"] in doc_text


def test_whatsapp_date_normalization() -> None:
    """Verify _normalize_date_str correctly normalizes date strings with slashes, dashes, backslashes, and directory paths."""
    assert WhatsAppReportPreflightGuard._normalize_date_str("07/10/2026") == "07-10-2026"
    assert WhatsAppReportPreflightGuard._normalize_date_str(r"07\10\2026") == "07-10-2026"
    assert WhatsAppReportPreflightGuard._normalize_date_str(Path("07/10/2026")) == "07-10-2026"
    assert WhatsAppReportPreflightGuard._normalize_date_str("07-10-2026") == "07-10-2026"
    assert WhatsAppReportPreflightGuard._normalize_date_str("QUICK REPORT/GEBENG/10. OCTOBER/07-10-2026") == "07-10-2026"
    assert WhatsAppReportPreflightGuard._normalize_date_str("C:/path/to/07-10-2026") == "07-10-2026"


def test_whatsapp_url_xml_escaping_idempotent(tmp_path: Path) -> None:
    """Verify WhatsAppReportLoader handles XML entity escaping idempotently without double-escaping."""
    template_path = tmp_path / "template.docx"
    doc = docx.Document()
    doc.add_paragraph("Laporan: {{link_laporan}}")
    doc.add_paragraph("ENGR: {{link_engr}}")
    doc.save(template_path)

    save_dir = tmp_path / "save"
    loader = WhatsAppReportLoader()

    # Pass pre-escaped and unescaped URLs
    plan = WhatsAppReportPlan(
        template_path=template_path,
        save_dir=save_dir,
        context={
            "link_laporan": "https://test.com/view?a=1&amp;b=2",
            "link_engr": "https://test.com/view?c=3&d=4",
        },
        substations_count=0,
        station_name="TEST",
        report_date="07/10/2026",
        voltage_type="33kV",
    )
    out_path = loader.load(plan)
    rendered_doc = docx.Document(out_path)
    full_text = "\n".join(p.text for p in rendered_doc.paragraphs)

    assert "https://test.com/view?a=1&b=2" in full_text
    assert "&amp;" not in full_text
    assert "https://test.com/view?c=3&d=4" in full_text


def test_whatsapp_station_resolution_all_districts(tmp_path: Path) -> None:
    """Verify discovery extracts station names for all Pahang districts including Cameron Highland and Lipis alias."""
    qr_dir = tmp_path / "QUICK REPORT"
    date_str = "16-10-2026"

    chl_dir = qr_dir / "CAMERON HIGHLAND" / "10. OCTOBER" / date_str
    chl_dir.mkdir(parents=True)
    (chl_dir / "26. MINI PPU TELANOK 33-11kV (US+VI).docx").write_bytes(b"dummy")

    lipis_dir = qr_dir / "LIPIS" / "10. OCTOBER" / date_str
    lipis_dir.mkdir(parents=True)
    (lipis_dir / "27. PMU BENTA 132-11kV (VI).docx").write_bytes(b"dummy")

    extractor = WhatsAppReportExtractor()
    files, hints = extractor._scan_qualifying_docx_files_33kv(qr_dir, date_str)

    assert len(files) == 2
    assert hints[files[0]] == "CAMERON HIGHLAND"
    assert hints[files[1]] == "KUALA LIPIS"


def test_normalize_date_str_single_digit_and_preflight(tmp_path: Path) -> None:
    """Verify single-digit date normalization and preflight guard directory discovery."""
    guard = WhatsAppReportPreflightGuard()

    # Single-digit day/month normalization and edge cases with spaces/slashes
    assert guard._normalize_date_str("7/10/2026") == "07-10-2026"
    assert guard._normalize_date_str(" 7 / 10 / 2026 ") == "07-10-2026"
    assert guard._normalize_date_str("7/10/2026/") == "07-10-2026"
    assert guard._normalize_date_str("7\\10\\2026\\") == "07-10-2026"
    assert guard._normalize_date_str(" 7 \\ 10 \\ 2026 \\ ") == "07-10-2026"
    assert guard._normalize_date_str("7/1/2026") == "07-01-2026"
    assert guard._normalize_date_str("07-10-2026") == "07-10-2026"
    assert guard._normalize_date_str("2026-10-07") == "07-10-2026"
    assert guard._normalize_date_str("7-10-2026") == "07-10-2026"
    assert guard._normalize_date_str("7\\10\\2026") == "07-10-2026"
    assert guard._normalize_date_str(Path("C:/QUICK REPORT/GEBENG/7-10-2026")) == "07-10-2026"
    assert guard._normalize_date_str(Path("C:/QUICK REPORT/GEBENG/10. OCTOBER/7-10-2026/")) == "07-10-2026"
    assert guard._normalize_date_str(Path("C:/QUICK REPORT/GEBENG/10. OCTOBER/07-10-2026/01. PPU.docx")) == "07-10-2026"

    # Preflight guard validate with single-digit date input string "7/10/2026"
    qr_dir = tmp_path / "QUICK REPORT"
    date_folder = qr_dir / "GEBENG" / "10. OCTOBER" / "07-10-2026"
    date_folder.mkdir(parents=True)
    (date_folder / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")

    total_pe_path = tmp_path / "TOTAL PE.xlsx"
    _create_33kv_total_pe(total_pe_path)

    template_path = tmp_path / "TEMPLATE.docx"
    template_path.write_bytes(b"dummy template")

    metadata = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV 2026",
        po_number="PO42394550",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "US", "TEV"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    env = ProjectEnvironment(metadata=metadata, storage=storage)

    resources = WhatsAppReportResources(
        quick_report_dir=qr_dir,
        save_dir=tmp_path / "PYTHON" / "WHATSAPP",
        template_path=template_path,
        total_pe_path=total_pe_path,
        station_mapping={"CGBG": "GEBENG"},
        voltage_type="33kV",
    )
    env.get_whatsapp_report_resources = lambda: resources

    # Passing "7/10/2026", " 7 / 10 / 2026 ", and "7/10/2026/" must succeed without FileNotFoundError
    guard.validate(env, WhatsAppReportRequest(report_dir="7/10/2026"))
    guard.validate(env, WhatsAppReportRequest(report_dir=" 7 / 10 / 2026 "))
    guard.validate(env, WhatsAppReportRequest(report_dir="7/10/2026/"))


def test_defect_suffix_pattern_spaced_operators() -> None:
    """Verify DEFECT_SUFFIX_PATTERN and filter stage support spaced defect operators without losing defects."""
    # Pattern matching
    assert DEFECT_SUFFIX_PATTERN.match("US + VI") is not None
    assert DEFECT_SUFFIX_PATTERN.match("US+VI") is not None
    assert DEFECT_SUFFIX_PATTERN.match("IR + US + TEV + VI") is not None
    assert DEFECT_SUFFIX_PATTERN.match("TEV + VI") is not None
    assert DEFECT_SUFFIX_PATTERN.match("US+ VI") is not None
    assert DEFECT_SUFFIX_PATTERN.match("IR+US") is not None
    assert DEFECT_SUFFIX_PATTERN.match("VI") is not None

    # Non-defect suffixes
    assert DEFECT_SUFFIX_PATTERN.match("SSU CAMEL POWER") is None
    assert DEFECT_SUFFIX_PATTERN.match("OLD") is None
    assert DEFECT_SUFFIX_PATTERN.match("PHASE 1") is None

    stage = WhatsAppReportFilter()

    # Spaced operator: (US + VI) -> defect="US+VI", clean stem
    p1 = stage._parse_docx_target(Path("01. PPU APMM 33-11kV (US + VI).docx"))
    assert p1 is not None
    assert p1[0] == 1
    assert p1[1] == "PPU APMM 33-11kV"
    assert p1[2] == "US+VI"

    # Multi-spaced: (IR + US + VI) -> defect="IR+US+VI", internal parens preserved
    p2 = stage._parse_docx_target(Path("02. SSU KIIP (SSU CAMEL POWER) 33kV (IR + US + VI).docx"))
    assert p2 is not None
    assert p2[0] == 2
    assert p2[1] == "SSU KIIP (SSU CAMEL POWER) 33kV"
    assert p2[2] == "IR+US+VI"

    # Non-defect parens: (OLD) -> defect="-", appended to stem
    p3 = stage._parse_docx_target(Path("04. SSU KULIM (OLD).docx"))
    assert p3 is not None
    assert p3[0] == 4
    assert p3[1] == "SSU KULIM (OLD)"
    assert p3[2] == "-"


def test_load_total_pe_resilient_date_columns(tmp_path: Path) -> None:
    """Verify _load_total_pe_dataframe and _lookup_substation_row handle TARIKH and DATE with trailing space."""
    # Workbook 1: Uses TARIKH instead of DATE
    wb1 = openpyxl.Workbook()
    ws1 = wb1.active
    ws1.title = "DataCycle1"
    ws1.append(["PE NO", "FL NUMBER", "SUBSTATION NAME", "TARIKH", "TYPE", "WO", "SCOPE"])
    ws1.append([1, "CGBG/PPU/G00001", "PPU APMM 33/11kV", datetime(2026, 10, 7), "PPU", "W1616898", "FULL"])
    wb1_path = tmp_path / "total_pe_tarikh.xlsx"
    wb1.save(wb1_path)
    wb1.close()

    extractor = WhatsAppReportExtractor()
    df1 = extractor._load_total_pe_dataframe(wb1_path)
    assert not df1.empty
    assert "TARIKH" in df1.columns

    filter_stage = WhatsAppReportFilter()
    sub_name, wo, raw_dt, fl = filter_stage._lookup_substation_row(df1, 1, "PPU APMM")
    assert sub_name == "PPU APMM 33/11kV"
    assert wo == "W1616898"
    assert raw_dt is not None

    # Workbook 2: Uses "DATE " with trailing space
    wb2 = openpyxl.Workbook()
    ws2 = wb2.active
    ws2.title = "DataCycle1"
    ws2.append(["PE NO", "FL NUMBER", "SUBSTATION NAME", "DATE ", "TYPE", "WO", "SCOPE"])
    ws2.append([2, "CKTN/SSU/G00002", "SSU KIIP", datetime(2026, 10, 7), "SSU", "W1616956", "FULL"])
    wb2_path = tmp_path / "total_pe_trailing_space.xlsx"
    wb2.save(wb2_path)
    wb2.close()

    df2 = extractor._load_total_pe_dataframe(wb2_path)
    assert not df2.empty

    sub_name2, wo2, raw_dt2, fl2 = filter_stage._lookup_substation_row(df2, 2, "SSU KIIP")
    assert sub_name2 == "SSU KIIP"
    assert wo2 == "W1616956"
    assert raw_dt2 is not None


def test_total_pe_empty_and_dash_dates_fallback_to_folder_date() -> None:
    """Verify empty string, whitespace, dash, and unparseable date values in TOTAL PE fall back to folder_date."""
    df = pd.DataFrame([
        {"PE NO": 1, "SUBSTATION NAME": "PPU APMM", "WO": "W123", "DATE": "", "FL NUMBER": "CGBG/PPU/G00001"},
        {"PE NO": 2, "SUBSTATION NAME": "SSU KIIP", "WO": "W124", "DATE": "-", "FL NUMBER": "CKTN/SSU/G00002"},
        {"PE NO": 3, "SUBSTATION NAME": "SSU LYNAS", "WO": "W125", "DATE": "  ", "FL NUMBER": "CGBG/SSU/G00003"},
        {"PE NO": 4, "SUBSTATION NAME": "SSU FERRO", "WO": "W126", "DATE": "N/A", "FL NUMBER": "CGBG/SSU/G00004"},
    ])
    filter_stage = WhatsAppReportFilter()
    for pe_num in (1, 2, 3, 4):
        _, _, raw_dt, _ = filter_stage._lookup_substation_row(df, pe_num, "STEM")
        assert raw_dt is None

    raw = WhatsAppRawTuple(
        substation_docx_files=[
            Path("01. PPU APMM (VI).docx"),
            Path("02. SSU KIIP (VI).docx"),
        ],
        total_pe_df=df,
        resources=WhatsAppReportResources(
            quick_report_dir=Path("/qr"),
            save_dir=Path("/save"),
            template_path=Path("/template.docx"),
            total_pe_path=Path("/total_pe.xlsx"),
            station_mapping={"CGBG": "GEBENG", "CKTN": "KUANTAN"},
            voltage_type="33kV",
        ),
        station_hints={},
        folder_date="07-10-2026",
    )
    targets = filter_stage.filter(raw)
    assert len(targets) == 2
    assert targets[0].raw_date == "07-10-2026"
    assert targets[1].raw_date == "07-10-2026"


def test_scan_qualifying_docx_non_standard_folder_depth(tmp_path: Path) -> None:
    """Verify _scan_qualifying_docx_files_33kv identifies known station despite non-standard folder depth."""
    qr_dir = tmp_path / "QUICK REPORT"
    date_str = "07-10-2026"

    # Non-standard nested folder structure with "UNASSIGNED" prefix
    nested_dir = qr_dir / "UNASSIGNED" / "GEBENG" / "10. OCTOBER" / date_str
    nested_dir.mkdir(parents=True)
    (nested_dir / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")

    extractor = WhatsAppReportExtractor()
    files, hints = extractor._scan_qualifying_docx_files_33kv(qr_dir, date_str)

    assert len(files) == 1
    # station_hints must resolve to "GEBENG", NOT "UNASSIGNED"
    assert hints[files[0]] == "GEBENG"


def test_scan_qualifying_docx_nearest_ancestor_resolution(tmp_path: Path) -> None:
    """Verify _scan_qualifying_docx_files_33kv resolves to the nearest ancestor station folder when parent folders also contain station names."""
    qr_dir = tmp_path / "QUICK REPORT"
    date_str = "07-10-2026"

    # Nested folder where KUANTAN is an outer folder, but GEBENG is the actual station folder
    nested_dir = qr_dir / "KUANTAN" / "BACKUP" / "GEBENG" / "10. OCTOBER" / date_str
    nested_dir.mkdir(parents=True)
    (nested_dir / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")

    extractor = WhatsAppReportExtractor()
    files, hints = extractor._scan_qualifying_docx_files_33kv(qr_dir, date_str)

    assert len(files) == 1
    assert hints[files[0]] == "GEBENG"


def test_asymmetric_date_padding_discovery(tmp_path: Path) -> None:
    """Verify _find_qualifying_33kv and _scan_qualifying_docx_files_33kv discover folders with asymmetric padding (07-1-2026 and 7-01-2026)."""
    qr_dir = tmp_path / "QUICK REPORT"

    # Station 1: padded day, unpadded month (07-1-2026)
    dir1 = qr_dir / "GEBENG" / "01. JANUARY" / "07-1-2026"
    dir1.mkdir(parents=True)
    (dir1 / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")

    # Station 2: unpadded day, padded month (7-01-2026)
    dir2 = qr_dir / "KUANTAN" / "01. JANUARY" / "7-01-2026"
    dir2.mkdir(parents=True)
    (dir2 / "02. SSU KIIP (VI).docx").write_bytes(b"dummy")

    guard = WhatsAppReportPreflightGuard()
    extractor = WhatsAppReportExtractor()

    # Query using normalized "07-01-2026"
    files_guard = guard._find_qualifying_33kv(qr_dir, "07-01-2026")
    assert len(files_guard) == 2

    files_ext, hints = extractor._scan_qualifying_docx_files_33kv(qr_dir, "07-01-2026")
    assert len(files_ext) == 2
    assert hints[files_ext[0]] == "GEBENG"
    assert hints[files_ext[1]] == "KUANTAN"


def test_lowercase_fl_number_code_resolution() -> None:
    """Verify lowercase FL number codes (e.g. cgbg/ppu/g00001) are resolved to stations in filter and transformer."""
    targets = [
        WhatsAppTargetEntity(
            substation_number=1,
            substation_name="PPU APMM",
            defect="VI",
            msms="W1616898",
            raw_date=datetime(2026, 10, 7),
            fl_number="cgbg/ppu/g00001",
            station="",
        )
    ]
    resources = WhatsAppReportResources(
        quick_report_dir=Path("/qr"),
        save_dir=Path("/save"),
        template_path=Path("/template.docx"),
        total_pe_path=Path("/total_pe.xlsx"),
        station_mapping={"CGBG": "GEBENG"},
        voltage_type="33kV",
    )
    transformer = WhatsAppReportTransformer()
    plan = transformer.transform(targets, resources)
    assert plan.station_name == "GEBENG"
    assert plan.context["items"][0]["station"] == "GEBENG"


def test_dynamic_known_stations_derivation(tmp_path: Path) -> None:
    """Verify known_stations is dynamically derived from config.STATION_MAPPING and custom mappings."""
    qr_dir = tmp_path / "QUICK REPORT"
    date_str = "07-10-2026"

    # Create folder for TEMERLOH (from config.STATION_MAPPING) and CUSTOM_STATION (from station_mapping)
    temerloh_dir = qr_dir / "TEMERLOH" / "10. OCTOBER" / date_str
    temerloh_dir.mkdir(parents=True)
    (temerloh_dir / "10. SSU TEMERLOH (VI).docx").write_bytes(b"dummy")

    custom_dir = qr_dir / "CUSTOM_AREA" / "10. OCTOBER" / date_str
    custom_dir.mkdir(parents=True)
    (custom_dir / "11. SSU SPECIAL (VI).docx").write_bytes(b"dummy")

    extractor = WhatsAppReportExtractor()
    custom_mapping = {"CCST": "CUSTOM_AREA"}

    files, hints = extractor._scan_qualifying_docx_files_33kv(
        qr_dir, date_str, station_mapping=custom_mapping
    )

    assert len(files) == 2
    # TEMERLOH derived from config.STATION_MAPPING
    assert hints[files[0]] == "TEMERLOH"
    # CUSTOM_AREA derived from station_mapping
    assert hints[files[1]] == "CUSTOM_AREA"


def test_preflight_guard_rejects_loose_file_matching_date_pattern(tmp_path: Path) -> None:
    """Verify preflight guard raises FileNotFoundError when a date pattern matches a file instead of a directory."""
    qr_dir = tmp_path / "QUICK REPORT"
    qr_dir.mkdir(parents=True)
    # Create a loose file named "07-10-2026" inside QUICK REPORT
    (qr_dir / "07-10-2026").write_bytes(b"not a directory")

    total_pe_path = tmp_path / "TOTAL PE.xlsx"
    _create_33kv_total_pe(total_pe_path)
    template_path = tmp_path / "TEMPLATE.docx"
    template_path.write_bytes(b"dummy")

    metadata = ProjectMetadata(
        key="pahang_33kv_2026",
        name="Pahang 33kV 2026",
        po_number="PO42394550",
        state="Pahang",
        voltage_type="33kV",
        year="2026",
        cycle="Cycle 1",
        technologies=("IR", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    env = ProjectEnvironment(metadata=metadata, storage=storage)
    resources = WhatsAppReportResources(
        quick_report_dir=qr_dir,
        save_dir=tmp_path / "PYTHON" / "WHATSAPP",
        template_path=template_path,
        total_pe_path=total_pe_path,
        station_mapping={"CGBG": "GEBENG"},
        voltage_type="33kV",
    )
    env.get_whatsapp_report_resources = lambda: resources

    guard = WhatsAppReportPreflightGuard()
    with pytest.raises(FileNotFoundError, match="Directory not found"):
        guard.validate(env, WhatsAppReportRequest(report_dir="07-10-2026"))




