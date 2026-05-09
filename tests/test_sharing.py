"""Tests for family share text generation."""

from __future__ import annotations

from bot.sharing import share_certificate_text, share_progress_text, telegram_share_url


def test_share_progress_text_includes_xp_and_bot() -> None:
    state = {
        "xp": 200,
        "level": 4,
        "streak_days": 5,
        "achievements": ["first_step", "five_in_one"],
    }
    text = share_progress_text(full_name="Аня Петрова", xp_state=state, bot_username="spasai_bot")
    assert "Аня Петрова" in text
    assert "200" in text
    assert "spasai_bot" in text
    assert "ачивок" in text
    assert "серия" in text


def test_share_progress_text_no_streak_when_short() -> None:
    state = {"xp": 30, "streak_days": 1, "achievements": []}
    text = share_progress_text(full_name=None, xp_state=state, bot_username="b")
    assert "серия" not in text


def test_share_certificate_text_includes_code() -> None:
    text = share_certificate_text(full_name="Иван Иванов", code="ABCDEF", bot_username="spasai_bot")
    assert "ABCDEF" in text
    assert "Иван Иванов" in text
    assert "spasai_bot" in text


def test_telegram_share_url_format() -> None:
    url = telegram_share_url("привет")
    assert url.startswith("https://t.me/share/url?url=")
