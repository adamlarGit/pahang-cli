"""Pure-function tests for the ADR 0009 acceptance harness (no Word, no project data)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import adr0009_acceptance_gate as gate  # noqa: E402


def test_select_11kv_takes_reports_093_to_102_only() -> None:
    assert gate._select("11kv", "093. CHAN KAM HONG (IR+VI)")
    assert gate._select("11kv", "102. TANG SUNG YUIM (VI)")
    assert not gate._select("11kv", "092. SOMEONE (VI)")
    assert not gate._select("11kv", "103. SOMEONE (VI)")
    assert not gate._select("11kv", "no number")


def test_select_33kv_takes_ppu_apmm_only() -> None:
    assert gate._select("33kv", "01. PPU APMM 3311kV")
    assert not gate._select("33kv", "03. SSU LYNAS 33kV")


def test_git_state_reports_head_and_dirtiness() -> None:
    state = gate._git_state(Path(__file__).resolve().parent.parent)
    assert len(state["head"]) == 40
    assert isinstance(state["dirty"], bool)
    assert len(state["diff_head_sha256"]) == 64


def test_own_memory_readings_are_positive() -> None:
    assert gate._own_peak_mb() > 0
    assert gate._own_now_mb() > 0
