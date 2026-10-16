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
from src.whatsapp.models import WhatsAppReportResources
from src.workflows.models import WhatsAppReportRequest
from src.workflows.whatsapp import (
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
    """Create synthetic 33kV TOTAL PE workbook with DataCycle1."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DataCycle1"
    ws.append(["PE NO", "FL NUMBER", "SUBSTATION NAME", "DATE", "TYPE", "WO", "SCOPE"])
    ws.append([1, "CGBG/PPU/G00001", "PPU APMM 33/11kV", datetime(2026, 10, 7), "PPU", "W1616898", "FULL"])
    ws.append([2, "CGBG/SSU/G00002", "SSU LYNAS 33kV", datetime(2026, 10, 7), "SSU", "W1616922", "FULL"])
    ws.append([3, "CGBG/SSU/G00003", "SSU FERRO MANGANESE 33kV", datetime(2026, 10, 7), "SSU", "W1616924", "FULL"])
    ws.append([4, "CKTN/SSU/G00004", "SSU KIIP (SSU CAMEL POWER) 33kV", datetime(2026, 10, 7), "SSU", "W1616956", "FULL"])
    # Row with float PE number and missing WO
    ws.append([5.0, "CGBG/SSU/G00005", "SSU KPC GEBENG 33kV", datetime(2026, 10, 8), "SSU", None, "FULL"])
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

    # Non-docx files should not match
    assert QUALIFYING_DOCX_PATTERN.match("01. PPU APMM.pdf") is None
    assert QUALIFYING_DOCX_PATTERN.match("desktop.ini") is None


def test_cross_station_date_folder_discovery_and_sorting(tmp_path: Path) -> None:
    """Verify WhatsAppReportExtractor aggregates across station directories and sorts by PE int."""
    qr_dir = tmp_path / "QUICK REPORT"
    date_str = "07-10-2026"
    
    # Station 1: GEBENG (PE 1, 3, 2)
    gebeng_dir = qr_dir / "GEBENG" / "10. OCTOBER" / date_str
    gebeng_dir.mkdir(parents=True)
    (gebeng_dir / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")
    (gebeng_dir / "03. SSU FERRO MANGANESE 33kV (VI).docx").write_bytes(b"dummy")
    (gebeng_dir / "02. SSU LYNAS 33kV (VI).docx").write_bytes(b"dummy")

    # Station 2: KUANTAN (PE 4)
    kuantan_dir = qr_dir / "KUANTAN" / "10. OCTOBER" / date_str
    kuantan_dir.mkdir(parents=True)
    (kuantan_dir / "04. SSU KIIP (SSU CAMEL POWER) 33kV (VI).docx").write_bytes(b"dummy")

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

    # 4 files discovered across GEBENG and KUANTAN, 08-10-2026 excluded
    assert len(raw.substation_docx_files) == 4
    file_names = [p.name for p in raw.substation_docx_files]
    assert file_names == [
        "01. PPU APMM 33-11kV (VI).docx",
        "02. SSU LYNAS 33kV (VI).docx",
        "03. SSU FERRO MANGANESE 33kV (VI).docx",
        "04. SSU KIIP (SSU CAMEL POWER) 33kV (VI).docx",
    ]
    assert raw.station_hints[raw.substation_docx_files[0]] == "GEBENG"
    assert raw.station_hints[raw.substation_docx_files[3]] == "KUANTAN"


def test_whatsapp_filter_33kv() -> None:
    """Verify WhatsAppReportFilter extracts PE integer, WONUM, and defect suffix."""
    df = pd.DataFrame([
        {"PE NO": 1, "SUBSTATION NAME": "PPU APMM", "WO": "W1616898", "DATE": datetime(2026, 10, 7), "FL NUMBER": "CGBG/PPU/G00001"},
        {"PE NO": "2.0", "SUBSTATION NAME": "SSU LYNAS", "WO": 40012345.0, "DATE": datetime(2026, 10, 7), "FL NUMBER": "CGBG/SSU/G00002"},
        {"PE NO": 3, "SUBSTATION NAME": "SSU FERRO", "WO": None, "DATE": datetime(2026, 10, 7), "FL NUMBER": "CGBG/SSU/G00003"},
    ])
    raw = WhatsAppRawTuple(
        substation_docx_files=[
            Path("01. PPU APMM (VI).docx"),
            Path("02. SSU LYNAS (US+VI).docx"),
            Path("03. SSU FERRO.docx"),
        ],
        total_pe_df=df,
        resources=WhatsAppReportResources(
            quick_report_dir=Path("/qr"),
            save_dir=Path("/save"),
            template_path=Path("/template.docx"),
            total_pe_path=Path("/total_pe.xlsx"),
            station_mapping={"CGBG": "GEBENG"},
            voltage_type="33kV",
        ),
        station_hints={
            Path("01. PPU APMM (VI).docx"): "GEBENG",
            Path("02. SSU LYNAS (US+VI).docx"): "GEBENG",
            Path("03. SSU FERRO.docx"): "GEBENG",
        },
    )

    stage = WhatsAppReportFilter()
    targets = stage.filter(raw)

    assert len(targets) == 3
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


def test_whatsapp_transformer_multi_station_grouping_and_links() -> None:
    """Verify multi-station grouping header, subheadings, continuous indexing, and 33kV links."""
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
            substation_name="SSU LYNAS 33kV",
            defect="VI",
            msms="W1616922",
            raw_date=datetime(2026, 10, 7),
            fl_number="CGBG/SSU/G00002",
            station="GEBENG",
        ),
        WhatsAppTargetEntity(
            substation_number=3,
            substation_name="SSU KIIP (SSU CAMEL POWER) 33kV",
            defect="VI",
            msms="W1616956",
            raw_date=datetime(2026, 10, 7),
            fl_number="CKTN/SSU/G00004",
            station="KUANTAN",
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

    # Continuous 1-based sequential numbering
    items = ctx["items"]
    assert len(items) == 3
    assert items[0]["index"] == 1
    assert items[0]["station_header"] == "GEBENG"
    assert items[1]["index"] == 2
    assert items[1]["station_header"] is None
    assert items[2]["index"] == 3
    assert items[2]["station_header"] == "KUANTAN"


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

    # Multi-station layout: GEBENG (PE 1, 2, 3) and KUANTAN (PE 4)
    gebeng_dir = qr_dir / "GEBENG" / "10. OCTOBER" / target_date
    kuantan_dir = qr_dir / "KUANTAN" / "10. OCTOBER" / target_date
    gebeng_dir.mkdir(parents=True)
    kuantan_dir.mkdir(parents=True)
    python_dir.mkdir(parents=True)

    (gebeng_dir / "01. PPU APMM 33-11kV (VI).docx").write_bytes(b"dummy")
    (gebeng_dir / "02. SSU LYNAS 33kV (VI).docx").write_bytes(b"dummy")
    (gebeng_dir / "03. SSU FERRO MANGANESE 33kV (VI).docx").write_bytes(b"dummy")
    (kuantan_dir / "04. SSU KIIP (SSU CAMEL POWER) 33kV (VI).docx").write_bytes(b"dummy")

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
