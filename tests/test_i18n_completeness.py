"""Регрессионный тест: новые i18n-ключи присутствуют во всех языках.

Если кто-то добавит новый ключ в "ru" и забудет про "en"/"uz"/"kk",
этот тест зафиксирует пропуск (фоллбек на DEFAULT всё ещё работает,
но визуально это будет ru-текст в кк-интерфейсе — нежелательно).
"""

from __future__ import annotations

import pytest

from bot.i18n import _STRINGS, t

REQUIRED_KEYS = (
    "nav.back",
    "nav.cancel",
    "cat.critical",
    "cat.urgent",
    "cat.minor",
    "sos.text",
    "panic.btn_breathe",
    "panic.btn_ground",
    "panic.btn_triage",
    "panic.btn_panic_menu",
    "panic.btn_main_menu",
    "panic.cycle_label",
    "panic.completed",
    "disp.cancel",
    "disp.tips_header",
)


@pytest.mark.parametrize("lang", ["ru", "en", "uz", "kk"])
@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_required_keys_present(lang: str, key: str) -> None:
    assert key in _STRINGS[lang], f"missing {key} in {lang}"
    value = _STRINGS[lang][key]
    assert isinstance(value, str)
    assert value.strip(), f"{key} in {lang} must be non-empty"


@pytest.mark.parametrize("lang", ["ru", "en", "uz", "kk"])
def test_panic_cycle_label_supports_format(lang: str) -> None:
    rendered = t("panic.cycle_label", lang, idx=2, total=10)
    assert "2" in rendered
    assert "10" in rendered


def test_unknown_lang_falls_back_to_ru() -> None:
    assert t("nav.back", "fr") == _STRINGS["ru"]["nav.back"]
