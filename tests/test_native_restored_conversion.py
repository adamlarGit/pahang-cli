"""Ticket #147: native export followed by Source Image Restoration (ADR 0009), with Word stubbed out."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from src.postprocessing.converters import (
    ComDocumentConverter,
    FakeDocumentConverter,
    PartConversionOutcome,
    convert_docx_native_restored,
)
from src.postprocessing.image_restoration import RestorationError, RestorationReport

NO_DELAYS = ()


def make_pdf(path: Path, pages: int = 1) -> None:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def page_count(path: Path) -> int:
    with fitz.open(str(path)) as doc:
        return doc.page_count


def report(restored: int = 1) -> RestorationReport:
    return RestorationReport(
        images_total=restored, restored=restored, unmatched=0, ambiguous=0, self_check_rejected=0, elapsed_s=0.0
    )


def leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.startswith(".tmp_"))


@pytest.fixture
def docx(tmp_path: Path) -> Path:
    path = tmp_path / "part.docx"
    path.write_bytes(b"revision-1")
    return path


def native_export(pages: int = 1):
    def export(_docx: Path, out: Path) -> None:
        make_pdf(out, pages)

    return export


def restoring(pages: int = 3, seen: list | None = None):
    def restore(snapshot: bytes, native: Path, out: Path) -> RestorationReport:
        if seen is not None:
            seen.append(snapshot)
        make_pdf(out, pages)
        return report()

    return restore


def test_restored_pdf_is_published_and_temps_are_removed(tmp_path: Path, docx: Path) -> None:
    out = tmp_path / "out.pdf"
    outcome = convert_docx_native_restored(
        docx, out, native_export(1), restore=restoring(3), retry_delays=NO_DELAYS
    )
    assert page_count(out) == 3  # the restored file, not the native one
    assert outcome.report is not None and outcome.report.restored == 1
    assert not outcome.fell_back and outcome.warning is None
    assert leftovers(tmp_path) == []


def test_restoration_failure_publishes_native_pdf_and_warns(tmp_path: Path, docx: Path) -> None:
    def failing(snapshot, native, out):
        out.write_bytes(b"half written")
        raise RestorationError("no match")

    out = tmp_path / "out.pdf"
    outcome = convert_docx_native_restored(docx, out, native_export(2), restore=failing, retry_delays=NO_DELAYS)
    assert page_count(out) == 2  # native
    assert outcome.fell_back and outcome.report is None
    assert "part.docx" in outcome.warning
    assert leftovers(tmp_path) == []


def test_unexpected_restoration_exception_also_falls_back(tmp_path: Path, docx: Path) -> None:
    def boom(snapshot, native, out):
        raise MemoryError("big")

    out = tmp_path / "out.pdf"
    outcome = convert_docx_native_restored(docx, out, native_export(2), restore=boom, retry_delays=NO_DELAYS)
    assert outcome.fell_back and page_count(out) == 2


def test_restoration_receives_the_snapshot_taken_before_export(tmp_path: Path, docx: Path) -> None:
    seen: list[bytes] = []
    convert_docx_native_restored(
        docx, tmp_path / "out.pdf", native_export(), restore=restoring(seen=seen), retry_delays=NO_DELAYS
    )
    assert seen == [b"revision-1"]


def test_source_changed_during_export_is_redone_once(tmp_path: Path, docx: Path) -> None:
    calls = []
    seen: list[bytes] = []

    def export(_docx: Path, out: Path) -> None:
        calls.append(1)
        if len(calls) == 1:
            _docx.write_bytes(b"revision-2")  # operator saves mid-conversion
        make_pdf(out)

    outcome = convert_docx_native_restored(
        docx, tmp_path / "out.pdf", export, restore=restoring(seen=seen), retry_delays=NO_DELAYS
    )
    assert len(calls) == 2
    assert seen == [b"revision-2"]
    assert not outcome.fell_back


def test_source_changing_twice_keeps_native_and_warns(tmp_path: Path, docx: Path) -> None:
    calls = []

    def export(_docx: Path, out: Path) -> None:
        calls.append(1)
        _docx.write_bytes(f"revision-{len(calls) + 1}".encode())
        make_pdf(out, 2)

    seen: list[bytes] = []
    out = tmp_path / "out.pdf"
    outcome = convert_docx_native_restored(docx, out, export, restore=restoring(seen=seen), retry_delays=NO_DELAYS)
    assert len(calls) == 2
    assert seen == []  # restoration never ran on a mixed revision
    assert outcome.fell_back and "source changed during conversion" in outcome.warning
    assert page_count(out) == 2
    assert leftovers(tmp_path) == []


def test_export_without_file_recycles_word_and_retries_once(tmp_path: Path, docx: Path) -> None:
    calls = []
    recycled = []

    def export(_docx: Path, out: Path) -> None:
        calls.append(1)
        if len(calls) > 1:
            make_pdf(out)  # first call returns silently without a file

    outcome = convert_docx_native_restored(
        docx,
        tmp_path / "out.pdf",
        export,
        restore=restoring(),
        recycle=lambda: recycled.append(1),
        retry_delays=NO_DELAYS,
    )
    assert len(calls) == 2 and recycled == [1]
    assert not outcome.fell_back


def test_unopenable_export_counts_as_failure(tmp_path: Path, docx: Path) -> None:
    calls = []

    def export(_docx: Path, out: Path) -> None:
        calls.append(1)
        if len(calls) == 1:
            out.write_bytes(b"not a pdf")
        else:
            make_pdf(out)

    convert_docx_native_restored(
        docx, tmp_path / "out.pdf", export, restore=restoring(), retry_delays=NO_DELAYS
    )
    assert len(calls) == 2


def test_export_failing_twice_raises_and_leaves_no_temp(tmp_path: Path, docx: Path) -> None:
    def export(_docx: Path, out: Path) -> None:
        raise RuntimeError("com dead")

    with pytest.raises(RuntimeError, match="Word export failed"):
        convert_docx_native_restored(
            docx, tmp_path / "out.pdf", export, restore=restoring(), retry_delays=NO_DELAYS
        )
    assert leftovers(tmp_path) == []
    assert not (tmp_path / "out.pdf").exists()


def test_keyboard_interrupt_between_steps_cleans_temps(tmp_path: Path, docx: Path) -> None:
    def interrupted(snapshot, native, out):
        out.write_bytes(b"partial")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        convert_docx_native_restored(
            docx, tmp_path / "out.pdf", native_export(), restore=interrupted, retry_delays=NO_DELAYS
        )
    assert leftovers(tmp_path) == []


def test_each_conversion_uses_unique_temp_names(tmp_path: Path, docx: Path) -> None:
    names: list[str] = []

    def export(_docx: Path, out: Path) -> None:
        names.append(out.name)
        make_pdf(out)

    for _ in range(2):
        convert_docx_native_restored(
            docx, tmp_path / "out.pdf", export, restore=restoring(), retry_delays=NO_DELAYS
        )
    assert len(set(names)) == 2
    assert all(n.startswith(".tmp_native_") and n.endswith(".pdf") for n in names)


class _FakeWord:
    """Word stand-in whose documents export real PDFs."""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.print_calls = 0

    class Documents:  # replaced per instance below
        pass

    def make(self):
        word = self
        word.Documents = type("D", (), {})()

        def open_doc(path, *args):
            word.opened.append(path)
            return _FakeDoc(word)

        word.Documents.Open = open_doc
        return word


class _FakeDoc:
    def __init__(self, word: _FakeWord) -> None:
        self.word = word

    def ExportAsFixedFormat(self, OutputFileName, **kwargs):
        make_pdf(Path(OutputFileName))

    def PrintOut(self, *args, **kwargs):
        self.word.print_calls += 1

    def Close(self, SaveChanges=False):
        pass


def test_com_converter_never_prints_and_records_outcome(tmp_path: Path, docx: Path, monkeypatch) -> None:
    import src.postprocessing.image_restoration as ir

    monkeypatch.setattr(ir, "restore_source_images", lambda b, n, o: (make_pdf(o, 2), report(4))[1])
    word = _FakeWord().make()
    converter = ComDocumentConverter()
    out = tmp_path / "out.pdf"

    assert converter.convert_docx_to_pdf(docx, out, word_app=word) == out

    assert word.print_calls == 0
    assert page_count(out) == 2
    assert converter.last_conversion.report.restored == 4
    assert leftovers(tmp_path) == []


def test_fake_converter_exposes_configured_outcome(tmp_path: Path) -> None:
    converter = FakeDocumentConverter()
    docx = tmp_path / "a - Part 01.docx"
    docx.write_bytes(b"x")
    outcome = PartConversionOutcome(docx, report(7))
    converter.conversion_outcomes[docx.name] = outcome
    converter.convert_docx_to_pdf(docx, tmp_path / "a.pdf")
    assert converter.last_conversion is outcome


# ------------------------------------------------------------------ review round: #147 fixes


class _ScriptedWord:
    """Word stand-in: the first `fail_opens` Documents.Open calls raise; later ones export real PDFs."""

    def __init__(self, name: str, fail_opens: int = 0) -> None:
        self.name = name
        self.fail_opens = fail_opens
        self.opened: list[str] = []
        self.quit_calls = 0
        word = self

        class _Docs:
            def Open(self, path, *args):
                word.opened.append(Path(path).name)
                if word.fail_opens > 0:
                    word.fail_opens -= 1
                    raise RuntimeError("Word is dead")
                return _FakeDoc(word)

        self.Documents = _Docs()

    def Quit(self):
        self.quit_calls += 1


class _FakeSession:
    def __init__(self, word_app, replacement) -> None:
        self.word_app = word_app
        self.replacement = replacement
        self.restarts = 0

    def restart_word(self) -> bool:
        self.restarts += 1
        self.word_app = self.replacement
        return True


def test_session_recycle_swaps_word_and_next_part_uses_the_new_app(tmp_path: Path, monkeypatch) -> None:
    dead, fresh = _ScriptedWord("A", fail_opens=1), _ScriptedWord("B")
    session = _FakeSession(dead, fresh)
    converter = ComDocumentConverter()
    part1, part2 = tmp_path / "p1.docx", tmp_path / "p2.docx"
    part1.write_bytes(b"1")
    part2.write_bytes(b"2")

    converter.convert_docx_to_pdf(part1, tmp_path / "p1.pdf", word_app=dead, session=session)
    # the workflow still holds the stale `dead` handle it captured before the loop
    converter.convert_docx_to_pdf(part2, tmp_path / "p2.pdf", word_app=dead, session=session)

    assert session.restarts == 1  # no second, spurious restart
    assert dead.opened == ["p1.docx"]
    assert fresh.opened == ["p1.docx", "p2.docx"]


def test_owns_word_recycle_quits_the_dead_instance_and_starts_a_new_one(tmp_path: Path, monkeypatch) -> None:
    first, second = _ScriptedWord("A", fail_opens=1), _ScriptedWord("B")
    instances = iter([first, second])
    monkeypatch.setattr("win32com.client.DispatchEx", lambda prog_id: next(instances))
    monkeypatch.setattr("pythoncom.CoInitialize", lambda: None)
    monkeypatch.setattr("pythoncom.CoUninitialize", lambda: None)
    docx = tmp_path / "solo.docx"
    docx.write_bytes(b"x")

    ComDocumentConverter().convert_docx_to_pdf(docx, tmp_path / "solo.pdf")

    assert first.quit_calls == 1 and second.quit_calls == 1
    assert second.opened == ["solo.docx"]
    assert (tmp_path / "solo.pdf").exists()


def test_injected_word_without_session_is_not_recycled(tmp_path: Path, monkeypatch) -> None:
    word = _ScriptedWord("A", fail_opens=1)
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"x")
    ComDocumentConverter().convert_docx_to_pdf(docx, tmp_path / "x.pdf", word_app=word)
    assert word.quit_calls == 0 and word.opened == ["x.docx", "x.docx"]


def test_last_conversion_is_reset_before_each_conversion(tmp_path: Path, monkeypatch) -> None:
    converter = ComDocumentConverter()
    converter.last_conversion = PartConversionOutcome(tmp_path / "old.docx", report(9))
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"x")
    word = _ScriptedWord("A", fail_opens=2)  # both attempts fail -> conversion raises

    with pytest.raises(RuntimeError):
        converter.convert_docx_to_pdf(docx, tmp_path / "x.pdf", word_app=word)

    assert converter.last_conversion is None
    assert ComDocumentConverter().last_conversion is None  # per-instance, declared in __init__


def test_publish_failure_is_not_reported_as_restoration_failure(tmp_path: Path, docx: Path, monkeypatch) -> None:
    real = __import__("src.postprocessing.converters", fromlist=["x"]).safe_replace_with_retry

    def flaky(src, dst, *a, **k):
        if Path(src).name.startswith(".tmp_restore_"):
            return False
        return real(src, dst, *a, **k)

    monkeypatch.setattr("src.postprocessing.converters.safe_replace_with_retry", flaky)
    out = tmp_path / "out.pdf"
    outcome = convert_docx_native_restored(
        docx, out, native_export(2), restore=restoring(3), retry_delays=NO_DELAYS
    )
    assert outcome.fell_back and page_count(out) == 2
    assert "image restoration failed" not in outcome.warning
    assert "publish" in outcome.warning


def test_temp_names_are_short_and_independent_of_the_stem(tmp_path: Path, docx: Path) -> None:
    seen: list[str] = []
    long_out = tmp_path / ("A VERY LONG 33kV SUBSTATION STEM " * 4 + ".pdf")

    def export(_d: Path, out: Path) -> None:
        seen.append(out.name)
        make_pdf(out)

    def restore(snapshot, native, out):
        seen.append(out.name)
        make_pdf(out)
        return report()

    convert_docx_native_restored(docx, long_out, export, restore=restore, retry_delays=NO_DELAYS)
    import re

    assert re.fullmatch(r"\.tmp_native_[0-9a-f]{8}\.pdf", seen[0])
    assert re.fullmatch(r"\.tmp_restore_[0-9a-f]{8}\.pdf", seen[1])


def test_no_snapshot_or_hash_when_restoration_is_off(tmp_path: Path, docx: Path, monkeypatch) -> None:
    def forbidden(self):
        raise AssertionError("DOCX must not be read when restore_images=False")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    calls = []
    out = tmp_path / "out.pdf"
    outcome = convert_docx_native_restored(
        docx, out, native_export(2), restore=lambda *a: calls.append(1), restore_images=False, retry_delays=NO_DELAYS
    )
    assert calls == [] and page_count(out) == 2 and outcome.report is None and not outcome.fell_back
