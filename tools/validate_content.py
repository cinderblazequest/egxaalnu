"""Валидатор JSON-контента: scenarios.json, aed_locations.json, panic, dispatcher.

Запуск: ``python -m tools.validate_content``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

REQUIRED_SCENARIO_FIELDS = {"id", "title", "category", "summary", "steps"}
ALLOWED_CATEGORIES = {"critical", "urgent", "minor"}


def _err(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def validate_scenarios() -> list[str]:
    errs: list[str] = []
    blob = json.loads((CONTENT / "scenarios.json").read_text(encoding="utf-8"))
    scenarios = blob.get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        errs.append("scenarios.json: empty or invalid scenarios array")
        return errs
    seen_ids: set[str] = set()
    for idx, raw in enumerate(scenarios):
        loc = f"scenario #{idx}"
        for f in REQUIRED_SCENARIO_FIELDS:
            if f not in raw:
                errs.append(f"{loc}: missing field '{f}'")
        sid = raw.get("id", "")
        if sid in seen_ids:
            errs.append(f"{loc}: duplicate id '{sid}'")
        seen_ids.add(sid)
        if raw.get("category") not in ALLOWED_CATEGORIES:
            errs.append(f"{loc} ({sid}): bad category '{raw.get('category')}'")
        steps = raw.get("steps", [])
        if not isinstance(steps, list) or not steps:
            errs.append(f"{loc} ({sid}): steps must be a non-empty list")
        else:
            for j, step in enumerate(steps):
                if not isinstance(step, dict) or not isinstance(step.get("text"), str):
                    errs.append(f"{loc} ({sid}): step #{j} must be {{'text': str}}")
        for tn in ("post_test", "pre_test"):
            for j, q in enumerate(raw.get(tn, [])):
                if not isinstance(q, dict):
                    errs.append(f"{loc} ({sid}).{tn}[{j}]: must be object")
                    continue
                if not isinstance(q.get("q"), str):
                    errs.append(f"{loc} ({sid}).{tn}[{j}]: 'q' must be string")
                opts = q.get("options")
                if not isinstance(opts, list) or len(opts) < 2:
                    errs.append(f"{loc} ({sid}).{tn}[{j}]: 'options' must have >=2")
                correct = q.get("correct")
                if not isinstance(correct, int) or not (0 <= correct < len(opts or [])):
                    errs.append(f"{loc} ({sid}).{tn}[{j}]: 'correct' out of range")
    return errs


def validate_aed() -> list[str]:
    errs: list[str] = []
    blob = json.loads((CONTENT / "aed_locations.json").read_text(encoding="utf-8"))
    locs = blob.get("locations", [])
    if not isinstance(locs, list):
        errs.append("aed_locations.json: 'locations' must be list")
        return errs
    for idx, loc in enumerate(locs):
        prefix = f"aed[{idx}]"
        for f in ("city", "name", "lat", "lon"):
            if f not in loc:
                errs.append(f"{prefix}: missing '{f}'")
        try:
            lat = float(loc["lat"])
            lon = float(loc["lon"])
            if not (-90 <= lat <= 90):
                errs.append(f"{prefix}: lat out of range")
            if not (-180 <= lon <= 180):
                errs.append(f"{prefix}: lon out of range")
        except (KeyError, ValueError, TypeError):
            errs.append(f"{prefix}: lat/lon must be numeric")
    return errs


def validate_panic() -> list[str]:
    errs: list[str] = []
    blob = json.loads((CONTENT / "panic_protocol.json").read_text(encoding="utf-8"))
    for f in ("intro", "breathing", "grounding", "triage"):
        if f not in blob:
            errs.append(f"panic_protocol.json: missing '{f}'")
    triage = blob.get("triage", [])
    if not isinstance(triage, list) or len(triage) < 3:
        errs.append("panic_protocol.json.triage: need at least 3 options")
    for idx, t in enumerate(triage or []):
        if "id" not in t or "label" not in t or "message" not in t:
            errs.append(f"panic.triage[{idx}]: missing id/label/message")
    return errs


def validate_dispatcher() -> list[str]:
    errs: list[str] = []
    blob = json.loads((CONTENT / "dispatcher_checklist.json").read_text(encoding="utf-8"))
    for f in ("intro", "questions", "summary_template"):
        if f not in blob:
            errs.append(f"dispatcher_checklist.json: missing '{f}'")
    qs = blob.get("questions", [])
    if not isinstance(qs, list) or len(qs) < 3:
        errs.append("dispatcher.questions: need at least 3")
    template = blob.get("summary_template", "")
    for q in qs or []:
        qid = q.get("id", "")
        if "{" + qid + "}" not in template:
            errs.append(f"dispatcher.summary_template: missing placeholder {{{qid}}}")
    return errs


def main() -> int:
    all_errs: list[str] = []
    all_errs += validate_scenarios()
    all_errs += validate_aed()
    all_errs += validate_panic()
    all_errs += validate_dispatcher()
    if all_errs:
        for e in all_errs:
            _err(e)
        print(f"\n{len(all_errs)} error(s).", file=sys.stderr)
        return 1
    print("OK: scenarios.json, aed_locations.json, panic, dispatcher")
    return 0


if __name__ == "__main__":
    sys.exit(main())
