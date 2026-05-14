"""Однократный скрипт: добавляет pre_test всем сценариям, где он пуст.

В исходной базе СПАС у части сценариев есть только post_test. Этот
скрипт берёт первые 1–2 вопроса post_test, переформулирует «как ты
думаешь?»-ом и кладёт в pre_test. Безопасно идемпотентен.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "content" / "scenarios.json"


def derive_pre_test(post_test: list[dict]) -> list[dict]:
    pre: list[dict] = []
    for q in post_test[:2]:
        question_text = q.get("q", "")
        pre.append(
            {
                "q": f"Как ты думаешь — {question_text[0].lower()}{question_text[1:]}"
                if question_text
                else "Как ты думаешь, что делать первым?",
                "options": list(q.get("options", [])),
                "correct": int(q.get("correct", 0)),
            }
        )
    return pre


def main() -> int:
    blob = json.loads(PATH.read_text(encoding="utf-8"))
    changed = 0
    for s in blob.get("scenarios", []):
        if not s.get("pre_test") and s.get("post_test"):
            s["pre_test"] = derive_pre_test(s["post_test"])
            changed += 1
    PATH.write_text(json.dumps(blob, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Patched {changed} scenarios with derived pre_test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
