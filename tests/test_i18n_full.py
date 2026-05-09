"""Тесты расширенного i18n (UZ/KZ + новые ключи)."""

from __future__ import annotations

from bot.i18n import SUPPORTED, normalize_lang, t


def test_supported_includes_uz_kk() -> None:
    assert "uz" in SUPPORTED
    assert "kk" in SUPPORTED


def test_kz_alias_maps_to_kk() -> None:
    assert normalize_lang("kz") == "kk"
    assert normalize_lang("KZ") == "kk"


def test_uzbek_consent_translation_present() -> None:
    out = t("consent.intro", "uz")
    assert "Shaxsiy ma'lumotlarni" in out


def test_kazakh_consent_translation_present() -> None:
    out = t("consent.intro", "kk")
    assert "Жеке деректер" in out


def test_forget_translations_have_buttons() -> None:
    for lang in ("ru", "en", "uz", "kk"):
        assert t("forget.btn_yes", lang)
        assert t("forget.btn_no", lang)
        assert t("forget.confirm", lang)


def test_alerts_keys_present_for_all_langs() -> None:
    for lang in ("ru", "en", "uz", "kk"):
        assert "{region}" in t("alerts.subscribed", lang) or "region" in t("alerts.subscribed", lang)
        assert t("alerts.list_empty", lang)


def test_format_substitution_in_uz() -> None:
    out = t("alerts.subscribed", "uz", region="moscow")
    assert "moscow" in out
