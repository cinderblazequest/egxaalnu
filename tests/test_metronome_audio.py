"""Проверка наличия mp3-метрономов и контракта `send_audio_metronome`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bot.metronome import AUDIO_DIR, send_audio_metronome


def test_audio_directory_contains_all_required_bpms() -> None:
    """Без mp3-файлов бот скатится в текстовый метроном — недопустимо для prod."""
    for bpm in (100, 110, 120):
        path = AUDIO_DIR / f"metronome_{bpm}.mp3"
        assert path.exists(), f"Нет аудио-файла {path}"
        # минимальный sanity check: файл не пустой и больше 50 КБ
        assert path.stat().st_size > 50_000, f"Файл {path} слишком маленький"


@pytest.mark.asyncio
async def test_send_audio_metronome_uses_existing_file(tmp_path: Path) -> None:
    """`send_audio_metronome` отдаёт `True` и вызывает send_audio, когда файл есть."""
    bot = AsyncMock()
    sent = await send_audio_metronome(bot, chat_id=42, bpm=110)
    assert sent is True
    bot.send_audio.assert_awaited_once()
    kwargs = bot.send_audio.await_args.kwargs
    assert kwargs["chat_id"] == 42
    assert "110" in kwargs["caption"]


@pytest.mark.asyncio
async def test_send_audio_metronome_returns_false_when_missing() -> None:
    """Если BPM нет в наличии — функция возвращает `False`, без вызова API."""
    bot = AsyncMock()
    sent = await send_audio_metronome(bot, chat_id=42, bpm=999)
    assert sent is False
    bot.send_audio.assert_not_awaited()
