"""Tests for i18n string lookup."""

from __future__ import annotations

from bot.i18n import normalize_lang, t


def test_normalize_lang_default() -> None:
    assert normalize_lang(None) == "ru"
    assert normalize_lang("") == "ru"


def test_normalize_lang_known() -> None:
    assert normalize_lang("ru") == "ru"
    assert normalize_lang("en") == "en"
    assert normalize_lang("RU") == "ru"
    assert normalize_lang("en-US") == "en"


def test_normalize_lang_unknown_falls_back_to_ru() -> None:
    assert normalize_lang("fr") == "ru"


def test_t_returns_translation_for_known_key() -> None:
    assert "Уровень" in t("profile.level", "ru")
    assert "Level" in t("profile.level", "en")


def test_t_falls_back_to_default_lang() -> None:
    # "fr" not supported, expect ru string
    assert "Уровень" in t("profile.level", "fr")


def test_t_falls_back_to_key_when_unknown() -> None:
    assert t("nonexistent.key", "ru") == "nonexistent.key"


def test_t_format_substitution() -> None:
    out = t("teacher.created", "ru", name="9-А", code="ABC123")
    assert "9-А" in out
    assert "ABC123" in out
