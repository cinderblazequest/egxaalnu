"""Тесты чек-листа диспетчера."""

from __future__ import annotations

from pathlib import Path

from bot.dispatcher import load_dispatcher_checklist, question_index, render_summary

CONTENT = Path(__file__).resolve().parents[1] / "content"


def test_load_returns_5_questions() -> None:
    d = load_dispatcher_checklist(CONTENT)
    assert len(d.questions) == 5
    assert {q.id for q in d.questions} == {"what", "where", "who", "condition", "what_doing"}
    for q in d.questions:
        assert len(q.examples) >= 2


def test_render_summary_fills_known_answers() -> None:
    d = load_dispatcher_checklist(CONTENT)
    answers = {
        "what": "ДТП",
        "where": "Тверская 1",
        "who": "взрослый",
        "condition": "без сознания",
        "what_doing": "СЛР",
    }
    text = render_summary(d, answers)
    assert "ДТП" in text
    assert "Тверская" in text
    assert "СЛР" in text
    assert "—" not in text.splitlines()[2]  # «Что: ДТП», не пусто


def test_render_summary_handles_missing_answers() -> None:
    d = load_dispatcher_checklist(CONTENT)
    text = render_summary(d, {})
    assert text.count("—") >= 5


def test_question_index() -> None:
    d = load_dispatcher_checklist(CONTENT)
    assert question_index(d, "what") == 0
    assert question_index(d, "what_doing") == 4
    assert question_index(d, "missing") == -1
