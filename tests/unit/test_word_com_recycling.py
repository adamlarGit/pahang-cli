"""Unit tests for Word COM process recycling across batch report workflows (#65)."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import zipfile
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.quick_report.compiler import FakeDocumentCompiler
from src.full_report.slicer import FakeDocumentSlicer
from src.testsheet.models import (
    SubstationEquipmentPackage,
    SubstationTestsheetPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
    TransformerSpec,
)
from src.workflows.full_report import FullReportWorkflow
from src.workflows.quick_report import QuickReportWorkflow


def _make_pkg(pe_number: int, station_name: str, station: str = "RAUB") -> SubstationTestsheetPackage:
    swg = SwitchgearSpec(
        switchgear_type="INDKOM",
        manufacturer="INDKOM",
        panels=(
            SwitchgearPanelSpec(panel_no=1, name="INCOMING", panel_type="LBS"),
            SwitchgearPanelSpec(panel_no=2, name="TX 1", panel_type="LBS"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="ABB", rating_kva="500")
    eq = SubstationEquipmentPackage(switchgears=(swg,), transformers=(tx,))

    data = TestsheetData(
        substation_number=pe_number,
        substation_name_erms=station_name,
        station_name=station,
        date_str="04-08-2026",
        fl_erms=f"FL-RAU-{pe_number:03d}",
        equipment=eq,
    )
    return SubstationTestsheetPackage(
        testsheet_path=Path(f"TESTSHEET/{station}/08. AUGUST/04-08-2026/{pe_number:03d}. {station_name}.xlsx"),
        unsorted_raw_data_dir=Path(f"RAW MATERIAL/{station}/08. AUGUST/04-08-2026/{pe_number:03d}. {station_name}"),
        station=station,
        month="08. AUGUST",
        date_str="04-08-2026",
        substation_number=pe_number,
        data=data,
    )


def _make_mock_env(tmp_path: Path) -> ProjectEnvironment:
    """Construct a minimal ProjectEnvironment rooted in tmp_path."""
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    (root / "TESTSHEET").mkdir(parents=True, exist_ok=True)
    (root / "QUICK REPORT").mkdir(parents=True, exist_ok=True)
    (root / "FULL REPORT").mkdir(parents=True, exist_ok=True)

    storage = LocalWorkspaceStorage(root)
    storage._initialize_project_workspace()
    metadata = ProjectMetadata(
        key="TEST_PROJ",
        name="Test Project",
        state="PAHANG",
        po_number="PO123456",
        year="2026",
        cycle="1",
        voltage_type="11kV",
        technologies=("IR", "US", "TEV"),
        base_path=str(root),
    )
    return ProjectEnvironment(metadata=metadata, storage=storage)


def _create_mock_qr_docx(path: Path, media_count: int = 8, target_size_bytes: int = 1_200_000) -> Path:
    """Create a minimal mock .docx file satisfying pre-flight size and media requirements."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types></Types>")
        for i in range(media_count):
            zf.writestr(f"word/media/image{i + 1}.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100)

        current_size = sum(info.file_size for info in zf.filelist)
        padding = max(0, target_size_bytes - current_size)
        zf.writestr("word/document.xml", b"<w:document>" + b"a" * padding + b"</w:document>")

    return path


def test_full_report_recycles_session_per_substation_when_session_none(tmp_path: Path):
    """FullReportWorkflow creates a fresh BatchComSession per substation when com_session=None."""
    env = _make_mock_env(tmp_path)
    pkg1 = _make_pkg(1, "PE ONE")
    pkg2 = _make_pkg(2, "PE TWO")
    pkg3 = _make_pkg(3, "PE THREE")

    # Create dummy Quick Reports for preflight validation
    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"
    _create_mock_qr_docx(qr_dir / "001. PE ONE (IR).docx")
    _create_mock_qr_docx(qr_dir / "002. PE TWO (IR).docx")
    _create_mock_qr_docx(qr_dir / "003. PE THREE (IR).docx")

    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())

    flush_calls = []
    orig_flush = wf._flush_substation_com_handles

    def track_flush(word_app, st_name):
        flush_calls.append(st_name)
        orig_flush(word_app, st_name)

    wf._flush_substation_com_handles = track_flush

    with patch("src.workflows.full_report.BatchComSession") as mock_session_cls:
        session_instances = []

        def make_session(*args, **kwargs):
            inst = MagicMock()
            inst.__enter__.return_value = inst
            session_instances.append(inst)
            return inst

        mock_session_cls.side_effect = make_session

        res = wf.generate(target=[pkg1, pkg2, pkg3], environment=env, com_session=None)

    assert res.succeeded_count == 3
    # Exactly 3 sessions created and cleaned up
    assert mock_session_cls.call_count == 3
    assert len(session_instances) == 3
    for inst in session_instances:
        inst.__enter__.assert_called_once()
        inst.__exit__.assert_called_once()

    # Flush handles called once per substation before session cleanup
    assert len(flush_calls) == 3


def test_full_report_reuses_explicit_com_session(tmp_path: Path):
    """FullReportWorkflow preserves caller-injected com_session across all substations."""
    env = _make_mock_env(tmp_path)
    pkg1 = _make_pkg(1, "PE ONE")
    pkg2 = _make_pkg(2, "PE TWO")

    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"
    _create_mock_qr_docx(qr_dir / "001. PE ONE (IR).docx")
    _create_mock_qr_docx(qr_dir / "002. PE TWO (IR).docx")

    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())

    explicit_session = MagicMock()

    with patch("src.workflows.full_report.BatchComSession") as mock_session_cls:
        res = wf.generate(target=[pkg1, pkg2], environment=env, com_session=explicit_session)

    assert res.succeeded_count == 2
    # BatchComSession class never called since explicit session was provided
    mock_session_cls.assert_not_called()
    explicit_session.__enter__.assert_called_once()
    explicit_session.__exit__.assert_called_once()


def test_quick_report_recycles_session_per_plan_when_session_none(tmp_path: Path):
    """QuickReportWorkflow enters and exits compiler session per plan when com_session is None."""
    mock_compiler = MagicMock()
    mock_composer = MagicMock()
    mock_extractor = MagicMock()
    mock_transformer = MagicMock()

    wf = QuickReportWorkflow(
        compiler=mock_compiler,
        composer=mock_composer,
        extractor=mock_extractor,
        transformer=mock_transformer,
    )

    plan1 = MagicMock()
    plan1.package = _make_pkg(1, "PE ONE")
    plan2 = MagicMock()
    plan2.package = _make_pkg(2, "PE TWO")

    mock_inspection = MagicMock()
    mock_inspection.missing_templates = ()
    mock_inspection.warnings = ()
    mock_inspection.errors = ()
    wf._plan = MagicMock(return_value=(mock_inspection, [plan1, plan2]))

    out1 = tmp_path / "out1.docx"
    out2 = tmp_path / "out2.docx"
    out1.write_bytes(b"dummy docx")
    out2.write_bytes(b"dummy docx")
    mock_composer.load.side_effect = [out1, out2]

    # Track compiler session context manager calls
    session_cms = []

    def make_cm():
        cm = MagicMock()
        cm.__enter__.return_value = cm
        session_cms.append(cm)
        return cm

    mock_compiler.session.side_effect = make_cm

    env = MagicMock()
    res = wf.generate(target="DUMMY", environment=env, com_session=None)

    assert res.reports_generated == 2
    assert mock_compiler.session.call_count == 2
    assert len(session_cms) == 2
    for cm in session_cms:
        cm.__enter__.assert_called_once()
        cm.__exit__.assert_called_once()


def test_quick_report_reuses_explicit_com_session(tmp_path: Path):
    """QuickReportWorkflow reuses explicit com_session across all plans without per-plan recycling."""
    mock_compiler = MagicMock()
    mock_composer = MagicMock()
    mock_extractor = MagicMock()
    mock_transformer = MagicMock()

    wf = QuickReportWorkflow(
        compiler=mock_compiler,
        composer=mock_composer,
        extractor=mock_extractor,
        transformer=mock_transformer,
    )

    plan1 = MagicMock()
    plan1.package = _make_pkg(1, "PE ONE")
    plan2 = MagicMock()
    plan2.package = _make_pkg(2, "PE TWO")

    mock_inspection = MagicMock()
    mock_inspection.missing_templates = ()
    mock_inspection.warnings = ()
    mock_inspection.errors = ()
    wf._plan = MagicMock(return_value=(mock_inspection, [plan1, plan2]))

    out1 = tmp_path / "out1.docx"
    out2 = tmp_path / "out2.docx"
    out1.write_bytes(b"dummy docx")
    out2.write_bytes(b"dummy docx")
    mock_composer.load.side_effect = [out1, out2]

    explicit_session = MagicMock()
    env = MagicMock()
    res = wf.generate(target="DUMMY", environment=env, com_session=explicit_session)

    assert res.reports_generated == 2
    explicit_session.__enter__.assert_called_once()
    explicit_session.__exit__.assert_called_once()
    mock_compiler.session.assert_not_called()
