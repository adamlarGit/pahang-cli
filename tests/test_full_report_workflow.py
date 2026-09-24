"""Unit tests for FullReportWorkflow Deep Module (Ticket #35 / T6.2).

Verifies:
1. Implements inspect() discovering substations, validating Quick Report presence/integrity,
   and returning inspection telemetry without disk writes.
2. Implements generate() establishing a single BatchComSession context across all batch substations.
3. Implements SubstationIsolatedBatchResiliencePolicy: errors on one station are captured in
   result.errors while remaining stations continue.
4. Reports progress through progress_sink callbacks.
5. Comprehensive unit tests covering single station, batch success, and partial failure modes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import zipfile
import pytest

from src.full_report.composer import FullReportComposer
from src.full_report.plan_builder import FullReportPlanBuilder
from src.full_report.preflight import PreFlightValidationResult
from src.full_report.slicer import FakeDocumentSlicer
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.quick_report.compiler import FakeDocumentCompiler, WordComDocumentCompiler
from src.testsheet.models import (
    SubstationEquipmentPackage,
    SubstationTestsheetPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TestsheetData,
    TransformerSpec,
)
from src.workflows.full_report import (
    FullReportBatchResult,
    FullReportInspection,
    FullReportStationExecutionResult,
    FullReportSubstationTelemetry,
    FullReportWorkflow,
)


def _create_mock_qr_docx(
    path: Path,
    *,
    media_count: int = 8,
    target_size_bytes: int = 1_100_000,
    corrupt_zip: bool = False,
) -> Path:
    """Create a mock .docx archive with controlled size and media count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if corrupt_zip:
        path.write_bytes(b"\x00" * target_size_bytes)
        return path

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        zf.writestr("word/_rels/document.xml.rels", b"<Relationships/>")

        for i in range(media_count):
            zf.writestr(f"word/media/image{i + 1}.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100)

        current_size = sum(info.file_size for info in zf.filelist)
        padding = max(0, target_size_bytes - current_size)
        zf.writestr("word/document.xml", b"<w:document>" + b"a" * padding + b"</w:document>")

    return path


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


def _make_sample_pkg(
    pe_number: int = 5,
    station_name: str = "PE TALAPIA",
    station: str = "RAUB",
    date_str: str = "04-08-2026",
    month: str = "08. AUGUST",
) -> SubstationTestsheetPackage:
    """Create a test SubstationTestsheetPackage with valid equipment."""
    swg = SwitchgearSpec(
        switchgear_type="INDKOM",
        manufacturer="INDKOM",
        panels=(
            SwitchgearPanelSpec(panel_no=1, panel_feeder_no="F1", name="INCOMING", panel_type="INCOMING"),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", manufacturer="MINCONSULT", rating_kva="1000")
    eq = SubstationEquipmentPackage(switchgears=(swg,), transformers=(tx,))

    data = TestsheetData(
        substation_number=pe_number,
        substation_name_erms=station_name,
        station_name=station,
        date_str=date_str,
        fl_erms="FL-RAU-001",
        equipment=eq,
    )
    return SubstationTestsheetPackage(
        testsheet_path=Path(f"TESTSHEET/{station}/{month}/{date_str}/{pe_number:03d}. {station_name}.xlsx"),
        unsorted_raw_data_dir=Path(f"RAW MATERIAL/{station}/{month}/{date_str}/{pe_number:03d}. {station_name}"),
        station=station,
        month=month,
        date_str=date_str,
        substation_number=pe_number,
        data=data,
    )


# ==============================================================================
# 1. Telemetry and Result Dataclass Tests
# ==============================================================================

def test_telemetry_and_result_dataclasses() -> None:
    """Verify fields, properties, and invariants of FullReport telemetry dataclasses."""
    pf_res = PreFlightValidationResult(path=Path("qr.docx"), is_valid=True, exists=True, size_bytes=1_200_000, media_count=8)
    telem = FullReportSubstationTelemetry(
        substation_number=5,
        substation_name="PE TALAPIA",
        functional_location="FL-RAU-001",
        station="RAUB",
        month="08. AUGUST",
        date_str="04-08-2026",
        quick_report_path=Path("qr.docx"),
        is_quick_report_valid=True,
        preflight_result=pf_res,
        target_output_path=Path("out.docx"),
        stem="005. PE TALAPIA (IR)",
        defect_suffix=" (IR)",
        cbm_defect_count=1,
        vi_defect_count=0,
    )
    assert telem.pe_number == 5
    assert telem.quick_report_valid is True
    assert telem.is_ready is True

    # Error invalidates is_ready
    telem_err = FullReportSubstationTelemetry(
        substation_number=6,
        substation_name="PE BROKEN",
        functional_location="FL-002",
        station="RAUB",
        month="08. AUGUST",
        date_str="04-08-2026",
        quick_report_path=None,
        is_quick_report_valid=False,
        preflight_result=None,
        target_output_path=Path("out.docx"),
        stem="006. PE BROKEN",
        defect_suffix="",
        cbm_defect_count=0,
        vi_defect_count=0,
        errors=("Quick Report missing",),
    )
    assert telem_err.is_ready is False

    inspection = FullReportInspection(targets=(telem, telem_err))
    assert len(inspection) == 2
    assert inspection.total_count == 2
    assert inspection.ready_count == 1
    assert inspection.ready_targets == (telem,)
    assert inspection.unready_targets == (telem_err,)

    exec_res = FullReportStationExecutionResult(
        station="PE TALAPIA",
        substation_number=5,
        output_path=Path("out.docx"),
        is_success=True,
        parts_count=7,
    )
    assert exec_res.pe_number == 5
    assert exec_res.is_success is True

    batch_res = FullReportBatchResult(
        total_stations=2,
        succeeded_count=1,
        failed_count=1,
        station_results=(exec_res,),
        generated_paths=(Path("out.docx"),),
        errors=("Station 2 failed",),
    )
    assert batch_res.reports_generated == 1
    assert batch_res.is_success is False
    assert batch_res.is_successful is False


# ==============================================================================
# 2. Initialization and Seams Tests
# ==============================================================================

def test_workflow_init_defaults() -> None:
    """FullReportWorkflow defaults to WordComDocumentCompiler and wires child deep modules."""
    wf = FullReportWorkflow()
    assert isinstance(wf._compiler, WordComDocumentCompiler)
    assert isinstance(wf._composer, FullReportComposer)
    assert isinstance(wf._plan_builder, FullReportPlanBuilder)


def test_workflow_init_custom_compiler() -> None:
    """FullReportWorkflow accepts injected FakeDocumentCompiler and FakeDocumentSlicer."""
    fake_comp = FakeDocumentCompiler()
    fake_slicer = FakeDocumentSlicer()
    wf = FullReportWorkflow(compiler=fake_comp, slicer=fake_slicer)
    assert wf._compiler is fake_comp
    assert wf._composer.compiler is fake_comp
    assert wf._slicer is fake_slicer


# ==============================================================================
# 3. Dry-Run Inspection Tests (inspect)
# ==============================================================================

def test_inspect_discovers_and_validates_without_disk_writes(tmp_path: Path) -> None:
    """inspect() discovers packages, validates Quick Reports, and returns telemetry with zero disk writes."""
    env = _make_mock_env(tmp_path)
    pkg1 = _make_sample_pkg(pe_number=1, station_name="PE TALAPIA", station="RAUB")
    pkg2 = _make_sample_pkg(pe_number=2, station_name="PE CENDERAWASIH", station="RAUB")

    # Create valid QR docx for pkg1 only
    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"
    qr_path1 = qr_dir / "001. PE TALAPIA (IR).docx"
    _create_mock_qr_docx(qr_path1, media_count=8, target_size_bytes=1_200_000)

    # Note: pkg2 has no QR file on disk

    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())

    # Snapshot full report directory before inspect
    full_report_dir = env.base_path / "FULL REPORT"
    files_before = list(full_report_dir.rglob("*"))

    inspection = wf.inspect(target=[pkg1, pkg2], environment=env)

    # Invariant: inspect must NOT create any files on disk
    files_after = list(full_report_dir.rglob("*"))
    assert files_before == files_after

    assert len(inspection) == 2
    assert inspection.total_count == 2
    assert inspection.ready_count == 1

    # Check pkg1 telemetry
    t1 = inspection[0]
    assert t1.substation_number == 1
    assert t1.substation_name == "PE TALAPIA"
    assert t1.is_quick_report_valid is True
    assert t1.is_ready is True
    assert t1.preflight_result is not None
    assert t1.preflight_result.is_valid is True
    assert "001. PE TALAPIA" in str(t1.target_output_path)

    # Check pkg2 telemetry (missing QR)
    t2 = inspection[1]
    assert t2.substation_number == 2
    assert t2.substation_name == "PE CENDERAWASIH"
    assert t2.is_quick_report_valid is False
    assert t2.is_ready is False
    assert t2.preflight_result is not None
    assert t2.preflight_result.exists is False
    assert len(t2.errors) > 0


def test_inspect_station_filtering(tmp_path: Path) -> None:
    """inspect() filters discovered packages according to station parameter."""
    env = _make_mock_env(tmp_path)
    pkg1 = _make_sample_pkg(pe_number=1, station_name="PE TALAPIA", station="RAUB")
    pkg2 = _make_sample_pkg(pe_number=2, station_name="PE TEMERLOH", station="TEMERLOH")

    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())
    inspection = wf.inspect(target=[pkg1, pkg2], environment=env, station="RAUB")

    assert len(inspection) == 1
    assert inspection[0].station == "RAUB"
    assert inspection[0].substation_name == "PE TALAPIA"


# ==============================================================================
# 4. Generation Tests (generate) & BatchCOM Session
# ==============================================================================

def test_generate_single_station_success(tmp_path: Path) -> None:
    """generate() compiles deliverable for single substation using swappable compiler."""
    env = _make_mock_env(tmp_path)
    pkg = _make_sample_pkg(pe_number=5, station_name="PE TALAPIA", station="RAUB")

    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"
    qr_path = qr_dir / "005. PE TALAPIA (IR).docx"
    _create_mock_qr_docx(qr_path, media_count=8, target_size_bytes=1_200_000)

    compiler = FakeDocumentCompiler()
    slicer = FakeDocumentSlicer()
    wf = FullReportWorkflow(compiler=compiler, slicer=slicer)

    progress_messages: list[str] = []
    result = wf.generate(target=pkg, environment=env, progress_sink=progress_messages.append)

    assert result.total_stations == 1
    assert result.succeeded_count == 1
    assert result.failed_count == 0
    assert result.is_success is True
    assert len(result.generated_paths) == 1

    out_file = result.generated_paths[0]
    assert out_file.exists()
    assert out_file.stat().st_size > 0
    assert "FULL REPORT" in str(out_file)

    # Progress sink reported
    assert any("PE TALAPIA" in msg for msg in progress_messages)


def test_generate_recycles_batch_com_session_per_substation(tmp_path: Path) -> None:
    """generate() recycles BatchComSession per substation when com_session=None, and reuses when explicit."""
    env = _make_mock_env(tmp_path)
    pkg1 = _make_sample_pkg(pe_number=1, station_name="PE TALAPIA", station="RAUB")
    pkg2 = _make_sample_pkg(pe_number=2, station_name="PE CENDERAWASIH", station="RAUB")

    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"
    _create_mock_qr_docx(qr_dir / "001. PE TALAPIA (IR).docx", media_count=8, target_size_bytes=1_200_000)
    _create_mock_qr_docx(qr_dir / "002. PE CENDERAWASIH (IR).docx", media_count=8, target_size_bytes=1_200_000)

    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())

    with patch("src.workflows.full_report.BatchComSession") as mock_session_cls:
        mock_cm = MagicMock()
        mock_session_cls.return_value = mock_cm
        mock_cm.__enter__.return_value = mock_cm

        result = wf.generate(target=[pkg1, pkg2], environment=env)

        assert result.succeeded_count == 2
        # Ticket #65: BatchComSession is recycled per substation (2 stations -> 2 sessions)
        assert mock_session_cls.call_count == 2
        assert mock_cm.__enter__.call_count == 2
        assert mock_cm.__exit__.call_count == 2

    # Preserves explicit com_session across all packages if passed
    explicit_session = MagicMock()
    result_explicit = wf.generate(target=[pkg1, pkg2], environment=env, com_session=explicit_session)
    assert result_explicit.succeeded_count == 2
    explicit_session.__enter__.assert_called_once()
    explicit_session.__exit__.assert_called_once()


# ==============================================================================
# 5. SubstationIsolatedBatchResiliencePolicy Tests
# ==============================================================================

def test_substation_isolated_batch_resilience_policy(tmp_path: Path) -> None:
    """SubstationIsolatedBatchResiliencePolicy: failures on one station do not abort remaining stations."""
    env = _make_mock_env(tmp_path)
    pkg1 = _make_sample_pkg(pe_number=1, station_name="STATION 1", station="RAUB")
    pkg2 = _make_sample_pkg(pe_number=2, station_name="STATION 2", station="RAUB")
    pkg3 = _make_sample_pkg(pe_number=3, station_name="STATION 3", station="RAUB")

    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"

    # Station 1: Valid
    _create_mock_qr_docx(qr_dir / "001. STATION 1 (IR).docx", media_count=8, target_size_bytes=1_200_000)
    # Station 2: Invalid (undersized 100 bytes)
    _create_mock_qr_docx(qr_dir / "002. STATION 2 (IR).docx", media_count=8, target_size_bytes=100)
    # Station 3: Valid
    _create_mock_qr_docx(qr_dir / "003. STATION 3 (IR).docx", media_count=8, target_size_bytes=1_200_000)

    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())
    result = wf.generate(target=[pkg1, pkg2, pkg3], environment=env)

    assert result.total_stations == 3
    assert result.succeeded_count == 2
    assert result.failed_count == 1
    assert len(result.generated_paths) == 2

    # Check station results breakdown
    res1, res2, res3 = result.station_results
    assert res1.is_success is True
    assert res1.station == "STATION 1"

    assert res2.is_success is False
    assert res2.station == "STATION 2"
    assert "floor" in str(res2.error_message).lower() or "pre-flight" in str(res2.error_message).lower()

    assert res3.is_success is True
    assert res3.station == "STATION 3"

    assert len(result.errors) == 1
    assert "STATION 2" in result.errors[0]


def test_composer_exception_resilience(tmp_path: Path) -> None:
    """If compilation raises on one station, subsequent stations still complete."""
    env = _make_mock_env(tmp_path)
    pkg1 = _make_sample_pkg(pe_number=1, station_name="FAILING STATION", station="RAUB")
    pkg2 = _make_sample_pkg(pe_number=2, station_name="PASSING STATION", station="RAUB")

    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"
    _create_mock_qr_docx(qr_dir / "001. FAILING STATION (IR).docx", media_count=8, target_size_bytes=1_200_000)
    _create_mock_qr_docx(qr_dir / "002. PASSING STATION (IR).docx", media_count=8, target_size_bytes=1_200_000)

    mock_composer = MagicMock(spec=FullReportComposer)

    def compose_side_effect(plan, **kwargs):
        if "FAILING" in plan.station:
            raise RuntimeError("Corrupted OLE Object in template")
        dest = plan.final_output_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"PK\x03\x04success")
        from src.full_report.composer import FullReportCompilationResult
        return FullReportCompilationResult(station=plan.station, output_path=dest, part_count=5)

    mock_composer.compose.side_effect = compose_side_effect

    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), composer=mock_composer, slicer=FakeDocumentSlicer())
    result = wf.generate(target=[pkg1, pkg2], environment=env)

    assert result.total_stations == 2
    assert result.succeeded_count == 1
    assert result.failed_count == 1
    assert len(result.generated_paths) == 1
    assert "FAILING STATION" in result.errors[0]
    assert result.station_results[1].is_success is True


def test_matches_station_substation_name(tmp_path: Path) -> None:
    """_matches_station should match by district/station, testsheet station_name, or ERMS name."""
    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())
    pkg = _make_sample_pkg(pe_number=5, station_name="TALAPIA", station="RAUB")

    # Match by district station
    assert wf._matches_station(pkg, "RAUB") is True
    # Match by substation name
    assert wf._matches_station(pkg, "TALAPIA") is True
    # Match in a list
    assert wf._matches_station(pkg, ["OTHER", "TALAPIA"]) is True
    # Unmatched
    assert wf._matches_station(pkg, "KUANTAN") is False


# ==============================================================================
# 6. Error and Target Validation Tests
# ==============================================================================

def test_missing_explicit_path_raises_file_not_found(tmp_path: Path) -> None:
    """Target explicit Path that does not exist raises FileNotFoundError."""
    env = _make_mock_env(tmp_path)
    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())
    missing_path = tmp_path / "non_existent_folder"

    with pytest.raises(FileNotFoundError):
        wf.generate(target=missing_path, environment=env)


def test_none_environment_raises_value_error() -> None:
    """ProjectEnvironment cannot be None."""
    wf = FullReportWorkflow()
    with pytest.raises(ValueError, match="ProjectEnvironment cannot be None"):
        wf.generate(target="04-08-2026", environment=None)  # type: ignore

    with pytest.raises(ValueError, match="ProjectEnvironment cannot be None"):
        wf.inspect(target="04-08-2026", environment=None)  # type: ignore


def test_resolve_target_fl_strings(tmp_path: Path) -> None:
    """FullReportWorkflow._resolve_target correctly parses single, comma-separated, and list FLs."""
    env = _make_mock_env(tmp_path)
    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())

    # Single FL string
    folders, fls = wf._resolve_target("CRAU/PCE/J00251", env)
    assert folders is None
    assert fls == ("CRAU/PCE/J00251",)

    # Comma-separated FL string
    folders, fls = wf._resolve_target("CRAU/PCE/J00251, CKTN/PCE/J00030", env)
    assert folders is None
    assert fls == ("CRAU/PCE/J00251", "CKTN/PCE/J00030")

    # Sequence of FL strings
    folders, fls = wf._resolve_target(["CRAU/PCE/J00251", "CKTN/PCE/J00030"], env)
    assert folders is None
    assert fls == ("CRAU/PCE/J00251", "CKTN/PCE/J00030")


def test_inspect_detects_missing_full_report_templates(tmp_path: Path) -> None:
    """inspect() flags error and sets is_ready=False when Full Report templates are missing (Bug 7)."""
    env = _make_mock_env(tmp_path)
    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())
    pkg = _make_sample_pkg(pe_number=5, station_name="TALAPIA", station="RAUB")

    # Set up valid QR file so preflight passes
    qr_dir = (
        Path(env.base_path)
        / "QUICK REPORT"
        / "RAUB"
        / "08. AUGUST"
        / "04-08-2026"
    )
    qr_dir.mkdir(parents=True, exist_ok=True)
    _create_mock_qr_docx(qr_dir / "005. TALAPIA.docx")

    # Delete census template from workspace
    census_tpl = env.storage.get_full_report_census_template()
    if census_tpl.exists():
        census_tpl.unlink()

    insp = wf.inspect(target=[pkg], environment=env)
    assert len(insp.targets) == 1
    telem = insp.targets[0]
    assert telem.is_ready is False
    assert any("census template" in err.lower() for err in telem.errors)


# ==============================================================================
# 7. Post-Compilation Sanity Check & COM Flush Tests (Ticket #44 / Seams 4 & 5)
# ==============================================================================

def test_generate_post_compilation_sanity_check_quarantine(tmp_path: Path) -> None:
    """If a deliverable contains foreign substation tables, it is quarantined and marked failed."""
    import docx
    env = _make_mock_env(tmp_path)
    pkg = _make_sample_pkg(pe_number=5, station_name="PE TALAPIA", station="RAUB")

    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"
    qr_path = qr_dir / "005. PE TALAPIA (IR).docx"
    _create_mock_qr_docx(qr_path, media_count=8, target_size_bytes=1_200_000)

    class CompromisedDocCompiler:
        """Compiler producing a deliverable with leaked foreign defect table."""
        def compile(self, parts, output_path):
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            doc = docx.Document()
            t = doc.add_table(rows=1, cols=2)
            t.rows[0].cells[0].text = "Substation"
            t.rows[0].cells[1].text = "TELEKOM TANAH PUTIH"  # Foreign substation!
            doc.save(str(p))
            return p

    wf = FullReportWorkflow(compiler=CompromisedDocCompiler(), slicer=FakeDocumentSlicer())
    result = wf.generate(target=pkg, environment=env)

    assert result.total_stations == 1
    assert result.succeeded_count == 0
    assert result.failed_count == 1
    assert result.is_success is False

    st_res = result.station_results[0]
    assert st_res.is_success is False
    assert "attribution sanity check failed" in st_res.error_message.lower()
    assert "quarantined" in st_res.error_message.lower()

    # Original deliverable moved to quarantine
    expected_out = wf._resolve_target_output_path(env, pkg, "005. PE TALAPIA")
    assert not expected_out.exists()
    quarantined = expected_out.parent / ".quarantine" / expected_out.name
    assert quarantined.exists()


def test_flush_substation_com_handles(tmp_path: Path) -> None:
    """_flush_substation_com_handles closes open COM docs, clears clipboard, and collects garbage."""
    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())

    mock_word = MagicMock()
    mock_docs = MagicMock()
    mock_doc1 = MagicMock()
    doc_state = {"count": 2}

    def mock_close(save):
        doc_state["count"] = max(0, doc_state["count"] - 1)

    mock_doc1.Close.side_effect = mock_close
    type(mock_docs).Count = property(lambda self: doc_state["count"])
    mock_docs.side_effect = lambda idx: mock_doc1
    mock_word.Documents = mock_docs

    with patch("src.quick_report.compiler._clear_clipboard") as mock_clear, \
         patch("gc.collect") as mock_gc:
        wf._flush_substation_com_handles(mock_word, "PE TALAPIA")

        assert mock_doc1.Close.call_count == 2
        mock_doc1.Close.assert_called_with(False)
        assert doc_state["count"] == 0
        mock_clear.assert_called_once()
        mock_gc.assert_called_once()


def test_generate_immediate_workspace_cleanup(tmp_path: Path) -> None:
    """Workspace temp directory is cleaned up immediately after station generation."""
    env = _make_mock_env(tmp_path)
    pkg = _make_sample_pkg(pe_number=5, station_name="PE TALAPIA", station="RAUB")

    qr_dir = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / "04-08-2026"
    qr_path = qr_dir / "005. PE TALAPIA (IR).docx"
    _create_mock_qr_docx(qr_path, media_count=8, target_size_bytes=1_200_000)

    wf = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())
    result = wf.generate(target=pkg, environment=env, keep_temp=False)

    assert result.is_success is True
    temp_dir = Path(env.base_path) / ".temp" / "full_report"
    # Temp station subfolders should not exist
    if temp_dir.exists():
        sub_dirs = list(temp_dir.iterdir())
        assert len(sub_dirs) == 0




from pathlib import Path
from unittest.mock import MagicMock, patch
from src.workflows.full_report import FullReportWorkflow
from src.testsheet.models import SubstationTestsheetPackage

def test_full_report_workflow_generate_multi_dates_telemetry(tmp_path: Path):
    mock_env = _make_mock_env(tmp_path)

    date1 = tmp_path / "workspace" / "TESTSHEET" / "RAUB" / "05. MAY" / "01-05-2026"
    date2 = tmp_path / "workspace" / "TESTSHEET" / "RAUB" / "05. MAY" / "02-05-2026"
    date1.mkdir(parents=True, exist_ok=True)
    date2.mkdir(parents=True, exist_ok=True)

    pkg1 = _make_sample_pkg(pe_number=1, station_name="PE TALAPIA", station="RAUB", date_str="01-05-2026", month="05. MAY")
    pkg2 = _make_sample_pkg(pe_number=2, station_name="PE CENDERAWASIH", station="RAUB", date_str="02-05-2026", month="05. MAY")

    qr_dir1 = mock_env.get_quick_report_dir() / "RAUB" / "05. MAY" / "01-05-2026"
    qr_dir2 = mock_env.get_quick_report_dir() / "RAUB" / "05. MAY" / "02-05-2026"
    _create_mock_qr_docx(qr_dir1 / "001. PE TALAPIA (IR).docx", media_count=8, target_size_bytes=1_200_000)
    _create_mock_qr_docx(qr_dir2 / "002. PE CENDERAWASIH (IR).docx", media_count=8, target_size_bytes=1_200_000)

    workflow = FullReportWorkflow(compiler=FakeDocumentCompiler(), slicer=FakeDocumentSlicer())

    def mock_extract(environment, folders=None, fls=None):
        pkgs = []
        if folders:
            for f in folders:
                if "01-05-2026" in str(f):
                    pkgs.append(pkg1)
                elif "02-05-2026" in str(f):
                    pkgs.append(pkg2)
        return pkgs

    progress_messages: list[str] = []

    with patch.object(workflow._extractor, "extract", side_effect=mock_extract):
        result = workflow.generate(
            (date1, date2),
            mock_env,
            progress_sink=progress_messages.append,
            keep_temp=False,
        )

    assert result.succeeded_count == 2
    assert any("[01-05-2026]" in msg for msg in progress_messages)
    assert any("[02-05-2026]" in msg for msg in progress_messages)
