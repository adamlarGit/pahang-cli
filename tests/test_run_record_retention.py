"""Run Record retention, tested by opening Runs on a temporary record folder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
import win32con
import win32file

from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE, open_run

DAY_SECONDS = 24 * 60 * 60
MB = 1024 * 1024
HOLD_FILE_OPEN = """
import sys
with open(sys.argv[1], "a", encoding="utf-8"):
    print("holding", flush=True)
    sys.stdin.readline()
"""


@pytest.fixture
def folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    records = tmp_path / "logs"
    records.mkdir()
    monkeypatch.setenv(RECORD_DIR_OVERRIDE_VARIABLE, str(records))
    return records


def seed_record(folder: Path, suffix: str, age_days: float = 0, size: int = 0) -> Path:
    """Write a Run Record with no finish entry, last written ``age_days`` ago."""
    path = folder / f"20260101-120000-seeded-run-{suffix}.jsonl"
    first_line = json.dumps({"type": "run_start", "time": "2026-01-01T04:00:00+00:00", "label": "Seeded"}) + "\n"
    with open(path, "w", encoding="utf-8") as record:
        record.write(first_line)
        if size:
            record.truncate(size)
    stamp = time.time() - age_days * DAY_SECONDS
    os.utime(path, (stamp, stamp))
    return path


def start_a_run() -> None:
    with open_run("Retention Check"):
        pass


def test_a_run_start_removes_a_record_older_than_90_days_and_keeps_a_younger_one(folder: Path) -> None:
    expired = seed_record(folder, "aaaaa1", age_days=91)
    recent = seed_record(folder, "aaaaa2", age_days=89)

    start_a_run()

    assert not expired.exists()
    assert recent.exists()


def test_the_oldest_records_are_removed_until_the_folder_is_within_200_mb(folder: Path) -> None:
    oldest = seed_record(folder, "bbbbb1", age_days=3, size=90 * MB)
    middle = seed_record(folder, "bbbbb2", age_days=2, size=90 * MB)
    newest = seed_record(folder, "bbbbb3", age_days=1, size=90 * MB)

    start_a_run()

    assert not oldest.exists()
    assert middle.exists()
    assert newest.exists()


@contextmanager
def held_open_by_another_process(path: Path) -> Iterator[None]:
    """Hold ``path`` open the way a running CLI holds its record, from a real second process."""
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLD_FILE_OPEN, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "holding"
        yield
    finally:
        holder.communicate(input="done\n", timeout=30)


def test_a_record_open_in_another_process_survives_and_older_records_are_still_removed(folder: Path) -> None:
    active = seed_record(folder, "ccccc1", age_days=120)
    expired = seed_record(folder, "ccccc2", age_days=100)

    with held_open_by_another_process(active):
        start_a_run()
        assert active.exists()
        assert not expired.exists()


def test_an_active_record_still_counts_towards_the_size_target(folder: Path) -> None:
    active = seed_record(folder, "ccccc5", age_days=3, size=90 * MB)
    middle = seed_record(folder, "ccccc6", age_days=2, size=90 * MB)
    newest = seed_record(folder, "ccccc7", age_days=1, size=90 * MB)

    with held_open_by_another_process(active):
        start_a_run()
        assert active.exists()
        assert not middle.exists()
        assert newest.exists()


def test_a_record_with_no_finish_entry_is_removed_once_its_owner_has_exited(folder: Path) -> None:
    abandoned = seed_record(folder, "ccccc3", age_days=100)

    with held_open_by_another_process(abandoned):
        start_a_run()
        assert abandoned.exists()

    start_a_run()
    assert not abandoned.exists()


def test_a_recent_record_with_no_finish_entry_is_kept_while_within_the_limits(folder: Path) -> None:
    incomplete = seed_record(folder, "ccccc4", age_days=1)

    start_a_run()

    assert incomplete.exists()


def test_files_that_are_not_run_records_are_untouched(folder: Path) -> None:
    lookalike = folder / "20260101-120000-seeded-run-ddddd1.jsonl"
    lookalike.write_text('{"type": "something_else"}\n', encoding="utf-8")
    others = [lookalike, folder / "notes.jsonl", folder / "20260101-120000-report-ddddd2.docx"]
    for other in others[1:]:
        other.write_text("keep me", encoding="utf-8")
    folder_with_a_record_name = folder / "20260101-120000-seeded-run-ddddd3.jsonl.d"
    folder_with_a_record_name.mkdir()
    long_ago = time.time() - 200 * DAY_SECONDS
    for other in others:
        os.utime(other, (long_ago, long_ago))

    start_a_run()

    assert all(other.exists() for other in others)
    assert folder_with_a_record_name.is_dir()


def test_a_directory_named_exactly_like_a_record_is_untouched(folder: Path) -> None:
    directory = folder / "20260101-120000-seeded-run-ddddd4.jsonl"
    directory.mkdir()
    long_ago = time.time() - 200 * DAY_SECONDS
    os.utime(directory, (long_ago, long_ago))

    start_a_run()

    assert directory.is_dir()


def test_an_unrelated_file_does_not_use_up_the_size_target(folder: Path) -> None:
    unrelated = folder / "backup.zip"
    with open(unrelated, "wb") as file:
        file.truncate(250 * MB)
    record = seed_record(folder, "ddddd5", age_days=1)

    start_a_run()

    assert record.exists()
    assert unrelated.exists()


def test_a_large_lookalike_file_does_not_cost_a_real_record(folder: Path) -> None:
    record = seed_record(folder, "ddddd6", age_days=5)
    lookalike = folder / "20260101-120000-seeded-run-ddddd7.jsonl"
    with open(lookalike, "wb") as file:
        file.write(b'{"type": "something_else"}\n')
        file.truncate(250 * MB)
    recent = time.time() - DAY_SECONDS
    os.utime(lookalike, (recent, recent))

    start_a_run()

    assert record.exists()
    assert lookalike.exists()


def test_a_record_locked_against_reading_stays_and_still_counts(folder: Path) -> None:
    locked = seed_record(folder, "ccccc8", age_days=3, size=90 * MB)
    middle = seed_record(folder, "ccccc9", age_days=2, size=90 * MB)
    newest = seed_record(folder, "cccca1", age_days=1, size=90 * MB)
    handle = win32file.CreateFile(
        str(locked), win32con.GENERIC_READ, 0, None, win32con.OPEN_EXISTING, 0, None
    )
    try:
        start_a_run()
        assert locked.exists()
        assert not middle.exists()
        assert newest.exists()
    finally:
        handle.Close()


def test_an_open_record_counts_at_its_current_size(folder: Path) -> None:
    middle = seed_record(folder, "ccccb1", age_days=3, size=90 * MB)
    newest = seed_record(folder, "ccccb2", age_days=2, size=90 * MB)
    growing = seed_record(folder, "ccccb3", age_days=1)

    with open(growing, "a", encoding="utf-8") as record:
        record.flush()
        record.truncate(90 * MB)
        start_a_run()

    assert not middle.exists()
    assert newest.exists()
    assert growing.exists()


def test_a_current_record_can_outgrow_the_target_and_a_later_cleanup_re_evaluates_it(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("src.run_records._RECORD_SIZE_TARGET_BYTES", 10_000)
    current = open_run("Long Run")
    current.record_warning("x" * 50_000)
    assert current.path is not None
    grown_size = current.path.stat().st_size

    concurrent = open_run("Concurrent Run")
    assert concurrent.path is not None
    assert current.path.stat().st_size == grown_size

    with current:
        current.record_warning("still recording")
    with concurrent:
        pass
    assert "still recording" in current.path.read_text(encoding="utf-8")
    earlier = time.time() - DAY_SECONDS
    os.utime(current.path, (earlier, earlier))

    start_a_run()

    assert not current.path.exists()
    assert concurrent.path.exists()


def test_a_record_another_cleanup_removed_first_counts_as_gone(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    oldest = seed_record(folder, "eeeee1", age_days=3, size=90 * MB)
    middle = seed_record(folder, "eeeee2", age_days=2, size=90 * MB)
    newest = seed_record(folder, "eeeee3", age_days=1, size=90 * MB)
    real_remove = os.remove

    def lose_the_race(path: str) -> None:
        real_remove(path)
        raise FileNotFoundError(path)

    monkeypatch.setattr("src.run_records.os.remove", lose_the_race)

    start_a_run()

    assert not oldest.exists()
    assert middle.exists()
    assert newest.exists()


def test_losing_a_race_for_one_record_does_not_stop_the_cleanup(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raced = seed_record(folder, "eeeee4", age_days=120)
    expired = seed_record(folder, "eeeee5", age_days=100)
    real_remove = os.remove

    def lose_the_race_once(path: str) -> None:
        real_remove(path)
        if Path(path) == raced:
            raise FileNotFoundError(path)

    monkeypatch.setattr("src.run_records.os.remove", lose_the_race_once)

    start_a_run()

    assert not raced.exists()
    assert not expired.exists()


def test_a_cleanup_failure_stops_nothing_and_prints_nothing(
    folder: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_record(folder, "fffff1", age_days=100)

    def unavailable(_path: Path) -> None:
        raise OSError("folder unavailable")

    monkeypatch.setattr("src.run_records.os.scandir", unavailable)

    with open_run("Retention Check") as run:
        run.call(lambda: None)
    run.report_availability()

    assert run.path is not None and run.path.is_file()
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
