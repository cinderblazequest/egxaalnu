"""Чек-лист «Что сказать диспетчеру 112»."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DispatcherQuestion:
    id: str
    label: str
    examples: tuple[str, ...]
    hint: str


@dataclass(frozen=True)
class DispatcherChecklist:
    intro: str
    questions: tuple[DispatcherQuestion, ...]
    summary_template: str
    after_call_tips: tuple[str, ...]


def load_dispatcher_checklist(content_dir: Path) -> DispatcherChecklist:
    raw = json.loads((content_dir / "dispatcher_checklist.json").read_text(encoding="utf-8"))
    questions = tuple(
        DispatcherQuestion(
            id=q["id"],
            label=q["label"],
            examples=tuple(q.get("examples", ())),
            hint=q.get("hint", ""),
        )
        for q in raw["questions"]
    )
    return DispatcherChecklist(
        intro=raw["intro"],
        questions=questions,
        summary_template=raw["summary_template"],
        after_call_tips=tuple(raw.get("after_call_tips", ())),
    )


def render_summary(checklist: DispatcherChecklist, answers: dict[str, str]) -> str:
    """Подставить ответы в шаблон. Пропуски заменяются на «—»."""
    fields = {q.id: answers.get(q.id, "—") or "—" for q in checklist.questions}
    body = checklist.summary_template.format(**fields)
    if checklist.after_call_tips:
        tips = "\n".join(f"• {tip}" for tip in checklist.after_call_tips)
        body = f"{body}\n\n<b>Подсказки на время разговора:</b>\n{tips}"
    return body


def question_index(checklist: DispatcherChecklist, qid: str) -> int:
    for i, q in enumerate(checklist.questions):
        if q.id == qid:
            return i
    return -1
