"""Ticket #147: run lock, stale temp sweep, Word recycling and restoration telemetry for Full Report post-processing."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.postprocessing.batch_guard import FolderLock, keep_awake, pid_alive, sweep_stale_temps
from src.postprocessing.converters import FakeDocumentConverter, PartConversionOutcome
from src.postprocessing.image_restoration import RestorationReport
from src.workflows.full_report_postprocessing import FullReportPostProcessingWorkflow
from tests.test_full_report_postprocessing import _create_mock_docx, _create_mock_pdf, _make_mock_env


def dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def report(restored: int, unmatched: int = 0, ambiguous: int = 0) -> RestorationReport:
    return RestorationReport(
        images_total=restored + unmatched + ambiguous,
        restored=restored,
        unmatched=unmatched,
        ambiguous=ambiguous,
        self_check_rejected=0,
        elapsed_s=0.0,
    )


# ------------------------------------------------------------------ batch_guard


def test_lock_is_exclusive_and_released(tmp_path: Path) -> None:
    first = FolderLock.acquire(tmp_path)
    assert first is not None
    assert json.loads((tmp_path / ".postprocess.lock").read_text())["pid"] == os.getpid()
    assert FolderLock.acquire(tmp_path) is None  # live holder (this process)
    first.release()
    assert not (tmp_path / ".postprocess.lock").exists()
    assert FolderLock.acquire(tmp_path) is not None


def test_lock_from_dead_pid_is_taken_over(tmp_path: Path) -> None:
    (tmp_path / ".postprocess.lock").write_text(json.dumps({"pid": dead_pid(), "started": 0}))
    lock = FolderLock.acquire(tmp_path)
    assert lock is not None
    assert json.loads(lock.path.read_text())["pid"] == os.getpid()


def test_corrupt_lock_is_taken_over(tmp_path: Path) -> None:
    lock = tmp_path / ".postprocess.lock"
    lock.write_text("{half")
    os.utime(lock, (1, 1))  # long-abandoned
    assert FolderLock.acquire(tmp_path) is not None


def test_pid_alive() -> None:
    assert pid_alive(os.getpid())
    assert not pid_alive(dead_pid())


def test_sweep_removes_dead_run_temps_but_never_word_owner_files(tmp_path: Path) -> None:
    stale = [
        ".tmp_conv_x_part_01.pdf",
        ".tmp_conv_x_master.pdf",
        ".tmp_native_ab12cd34_x.pdf",
        ".tmp_restore_ab12cd34_x.pdf",
        ".tmp_mrg_x.pdf",
    ]
    keep = ["~$port.docx", "x.pdf", "x - Part 01.docx", ".postprocess.lock"]
    for name in stale + keep:
        (tmp_path / name).write_bytes(b"x")
    sweep_stale_temps(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(keep)


def test_keep_awake_sets_and_clears_execution_state() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    calls: list[int] = []
    kernel32 = ctypes.windll.kernel32
    original = kernel32.SetThreadExecutionState

    class Spy:
        def __call__(self, flags):
            calls.append(flags & 0xFFFFFFFF)
            return original(flags)

    kernel32.SetThreadExecutionState = Spy()
    try:
        with keep_awake():
            pass
    finally:
        kernel32.SetThreadExecutionState = original
    assert calls == [0x80000001, 0x80000000]


# ------------------------------------------------------------------ workflow


class RecyclingSession:
    def __init__(self) -> None:
        self.word_app = object()
        self.restarts = 0

    def restart_word(self) -> bool:
        self.restarts += 1
        self.word_app = object()
        return True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None


def build_two_substations(tmp_path: Path):
    env = _make_mock_env(tmp_path)
    date_str = "04-08-2026"
    folder = env.get_full_report_dir() / "RAUB" / "08. AUGUST" / date_str
    docs = {}
    for stem, n_parts in (("005. TALAPIA (IR+VI)", 2), ("006. CHEROH (IR+VI)", 1)):
        docs[stem] = [_create_mock_docx(folder / f"{stem} - Part {i:02d} - X.docx") for i in range(1, n_parts + 1)]
        ts = env.get_testsheet_dir() / "RAUB" / "08. AUGUST" / date_str / "processed_testsheet" / "pdf" / f"{stem}.pdf"
        _create_mock_pdf(ts)
    return env, date_str, folder, docs


def test_restoration_counts_are_attached_and_summarised_per_report(tmp_path: Path) -> None:
    env, date_str, folder, docs = build_two_substations(tmp_path)
    converter = FakeDocumentConverter()
    p1, p2 = docs["005. TALAPIA (IR+VI)"]
    (single,) = docs["006. CHEROH (IR+VI)"]
    converter.conversion_outcomes[p1.name] = PartConversionOutcome(p1, report(10, unmatched=2))
    converter.conversion_outcomes[p2.name] = PartConversionOutcome(
        p2, None, True, "image restoration failed for part 2; kept native PDF"
    )
    converter.conversion_outcomes[single.name] = PartConversionOutcome(single, report(5, ambiguous=1))

    result = FullReportPostProcessingWorkflow(converter=converter).process(date_str, env)

    assert result.succeeded_count == 2
    by_stem = {t.stem: t for t in result.telemetries}
    talapia = by_stem["005. TALAPIA (IR+VI)"]
    assert (talapia.images_restored, talapia.images_unmatched, talapia.fallback_count) == (10, 2, 1)
    assert talapia.restoration_banner == (
        "[IMG] 005. TALAPIA (IR+VI): restored 10 images across 2 parts, 2 unmatched, 0 ambiguous, 1 fallbacks"
    )
    cheroh = by_stem["006. CHEROH (IR+VI)"]
    assert (cheroh.images_restored, cheroh.images_ambiguous, cheroh.fallback_count) == (5, 1, 0)
    assert any("kept native PDF" in w for w in result.warnings)


def test_word_is_recycled_at_each_substation_boundary_only(tmp_path: Path) -> None:
    env, date_str, _folder, _docs = build_two_substations(tmp_path)
    session = RecyclingSession()
    result = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter()).process(
        date_str, env, com_session=session
    )
    assert result.succeeded_count == 2
    assert session.restarts == 1  # between the two substations, not before the first


def test_folder_held_by_live_run_is_skipped_with_message(tmp_path: Path) -> None:
    env, date_str, folder, _docs = build_two_substations(tmp_path)
    held = FolderLock.acquire(folder)
    converter = FakeDocumentConverter()

    result = FullReportPostProcessingWorkflow(converter=converter).process(date_str, env)

    assert result.succeeded_count == 0
    assert converter.convert_docx_calls == []
    assert any("another post-processing run" in e for e in result.errors)
    assert not result.is_success
    assert (folder / ".postprocess.lock").exists()  # the other run's lock is untouched
    held.release()


def test_lock_is_released_and_stale_temps_swept_after_run(tmp_path: Path) -> None:
    env, date_str, folder, _docs = build_two_substations(tmp_path)
    (folder / ".tmp_conv_old_part_01.pdf").write_bytes(b"x")
    (folder / "~$ocument.docx").write_bytes(b"owner")
    (folder / ".postprocess.lock").write_text(json.dumps({"pid": dead_pid(), "started": 0}))

    result = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter()).process(date_str, env)

    assert result.succeeded_count == 2
    names = {p.name for p in folder.iterdir()}
    assert ".tmp_conv_old_part_01.pdf" not in names
    assert ".postprocess.lock" not in names
    assert "~$ocument.docx" in names


def test_word_owner_files_are_ignored_by_discovery(tmp_path: Path) -> None:
    env, date_str, folder, docs = build_two_substations(tmp_path)
    owner = _create_mock_docx(folder / "~$5. TALAPIA (IR+VI) - Part 01 - X.docx")
    workflow = FullReportPostProcessingWorkflow(converter=FakeDocumentConverter())

    for target in (date_str, folder, [folder], docs["005. TALAPIA (IR+VI)"][0]):
        found, _w, _e = workflow._discover_docx_files(target, env)
        assert owner.resolve() not in found, target

    found, _w, errors = workflow._discover_docx_files(owner, env)
    assert found == [] and errors


# ------------------------------------------------------------------ review round: lock safety


def test_young_empty_lock_is_a_live_writer_not_a_stale_lock(tmp_path: Path) -> None:
    lock = tmp_path / ".postprocess.lock"
    lock.write_text("")  # just created, PID not written yet
    assert FolderLock.acquire(tmp_path) is None
    assert lock.exists()


def test_old_empty_lock_is_stale(tmp_path: Path) -> None:
    lock = tmp_path / ".postprocess.lock"
    lock.write_text("")
    os.utime(lock, (1, 1))
    assert FolderLock.acquire(tmp_path) is not None


def test_lock_content_is_complete_the_moment_it_is_visible(tmp_path: Path, monkeypatch) -> None:
    seen = []
    real_link = os.link

    def spy(src, dst, *a, **k):
        seen.append(json.loads(Path(src).read_text())["pid"])  # content written before publication
        return real_link(src, dst, *a, **k)

    monkeypatch.setattr(os, "link", spy)
    assert FolderLock.acquire(tmp_path) is not None
    assert seen == [os.getpid()]
    assert [p.name for p in tmp_path.iterdir()] == [".postprocess.lock"]  # no temp left behind


def test_pid_reuse_is_detected_with_the_started_timestamp(tmp_path: Path) -> None:
    if sys.platform != "win32":
        return
    # a live PID (ours) but a lock written long before this process existed: the PID was recycled
    (tmp_path / ".postprocess.lock").write_text(json.dumps({"pid": os.getpid(), "started": 1.0}))
    assert FolderLock.acquire(tmp_path) is not None


def test_concurrent_takeover_of_a_stale_lock_has_exactly_one_winner(tmp_path: Path) -> None:
    import threading

    for _ in range(20):
        (tmp_path / ".postprocess.lock").write_text(json.dumps({"pid": dead_pid(), "started": 0}))
        barrier = threading.Barrier(8)
        winners: list[FolderLock] = []

        def contend():
            barrier.wait()
            lock = FolderLock.acquire(tmp_path)
            if lock is not None:
                winners.append(lock)

        threads = [threading.Thread(target=contend) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(winners) == 1
        winners[0].release()
        assert not (tmp_path / ".postprocess.lock").exists()
        assert [p.name for p in tmp_path.iterdir()] == []  # no aside/temp files leak


def test_win32_api_declares_pointer_sized_handles() -> None:
    if sys.platform != "win32":
        return
    from ctypes import wintypes

    from src.postprocessing import batch_guard

    k32 = batch_guard._kernel32()
    assert k32.OpenProcess.restype is wintypes.HANDLE
    assert k32.OpenProcess.argtypes is not None
    assert k32.CloseHandle.argtypes == [wintypes.HANDLE]
    assert batch_guard.pid_alive(os.getpid())
    assert not batch_guard.pid_alive(dead_pid())


# ------------------------------------------------------------------ review round: lock leak, CLI summary


def test_locks_are_released_when_the_word_session_fails_to_start(tmp_path: Path, monkeypatch) -> None:
    from src.postprocessing.converters import ComDocumentConverter

    env, date_str, folder, _docs = build_two_substations(tmp_path)

    class Exploding:
        def __enter__(self):
            raise RuntimeError("Word failed to start")

        def __exit__(self, *exc):
            return None

    monkeypatch.setattr(
        "src.workflows.full_report_postprocessing.batch_com_session", lambda **kw: Exploding()
    )
    workflow = FullReportPostProcessingWorkflow(converter=ComDocumentConverter())

    try:
        workflow.process(date_str, env)
    except RuntimeError as exc:
        assert "Word failed to start" in str(exc)
    else:
        raise AssertionError("expected the session failure to propagate")
    assert not (folder / ".postprocess.lock").exists()


def test_cli_summary_prints_restoration_banner_and_fallback_row(tmp_path: Path, capsys) -> None:
    from src.project_workflow_actions import _print_full_report_postprocessing_summary

    env, date_str, _folder, docs = build_two_substations(tmp_path)
    converter = FakeDocumentConverter()
    p1, p2 = docs["005. TALAPIA (IR+VI)"]
    converter.conversion_outcomes[p1.name] = PartConversionOutcome(p1, report(10, unmatched=2))
    converter.conversion_outcomes[p2.name] = PartConversionOutcome(p2, None, True, "kept native PDF")
    result = FullReportPostProcessingWorkflow(converter=converter).process(date_str, env)

    _print_full_report_postprocessing_summary(result)
    out = capsys.readouterr().out

    assert "SOURCE IMAGE RESTORATION" in out
    assert "[IMG] 005. TALAPIA (IR+VI): restored 10 images across 2 parts, 2 unmatched" in out
    assert "[WARN] 005. TALAPIA (IR+VI): 1 part(s) kept their native (unrestored) PDF" in out
    assert "006. CHEROH" in out  # second report also summarised
