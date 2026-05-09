"""Тесты panic-модуля."""

from __future__ import annotations

from pathlib import Path

from bot.panic import find_triage, load_panic_protocol

CONTENT = Path(__file__).resolve().parents[1] / "content"


def test_panic_protocol_loads() -> None:
    p = load_panic_protocol(CONTENT)
    assert p.intro
    assert p.breathing_total_cycles >= 6
    assert p.breathing_cycle_seconds >= 6
    assert len(p.grounding_lines) == 5
    assert len(p.triage) >= 4


def test_find_triage_returns_match() -> None:
    p = load_panic_protocol(CONTENT)
    opt = find_triage(p, p.triage[0].id)
    assert opt is not None
    assert opt.id == p.triage[0].id


def test_find_triage_returns_none_when_missing() -> None:
    p = load_panic_protocol(CONTENT)
    assert find_triage(p, "no-such-id") is None
