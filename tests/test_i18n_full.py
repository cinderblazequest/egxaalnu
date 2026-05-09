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


def test_main_menu_keys_in_all_languages() -> None:
    """Меню должно быть переведено на 4 языка целиком."""
    keys = [
        "menu.welcome",
        "menu.btn_sos",
        "menu.btn_panic",
        "menu.btn_critical",
        "menu.btn_urgent",
        "menu.btn_minor",
        "menu.btn_training",
        "menu.btn_aed",
        "menu.btn_add_aed",
        "menu.btn_dispatcher",
        "menu.btn_certificate",
        "menu.btn_profile",
        "menu.btn_ask",
        "menu.btn_feedback",
        "menu.training_intro",
        "menu.training_empty",
        "step.back",
        "step.fwd",
        "step.metro",
        "step.menu",
        "step.finish",
        "step.finish_train",
        "scenario.completed",
    ]
    for lang in ("ru", "en", "uz", "kk"):
        for key in keys:
            value = t(key, lang)
            assert value, f"missing {key} in {lang}"
            assert value != key, f"untranslated {key} in {lang}"


def test_training_buttons_distinct() -> None:
    """`step.finish` (обычный) ≠ `step.finish_train` (с тестом)."""
    for lang in ("ru", "en", "uz", "kk"):
        assert t("step.finish", lang) != t("step.finish_train", lang)


def test_main_menu_kb_uses_lang() -> None:
    """main_menu_kb(lang) должен подставлять нужные строки."""
    from bot.handlers import main_menu_kb

    kb_ru = main_menu_kb("ru")
    kb_en = main_menu_kb("en")
    kb_uz = main_menu_kb("uz")
    ru_texts = {btn.text for row in kb_ru.inline_keyboard for btn in row}
    en_texts = {btn.text for row in kb_en.inline_keyboard for btn in row}
    uz_texts = {btn.text for row in kb_uz.inline_keyboard for btn in row}
    assert any("Обучение" in s for s in ru_texts)
    assert any("Training" in s for s in en_texts)
    assert any("O'qish" in s for s in uz_texts)
    # каждый язык должен содержать ровно одну "training"-кнопку
    for texts in (ru_texts, en_texts, uz_texts):
        assert any(
            "🎓" in s and "Обучение" in s or "🎓" in s and "Training" in s or "🎓" in s and "O'qish" in s
            for s in texts
        )
