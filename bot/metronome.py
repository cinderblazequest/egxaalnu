"""
Голосовой метроном для СЛР.
Здесь — асинхронный отправитель «текстового метронома»: бот шлёт
последовательно сообщения «жми / жми / жми» в темпе 110 BPM в течение
30 секунд. Это безопасный запасной вариант, если у бота нет аудио.

В продакшене мы дополнительно прикрепляем заранее сгенерированный mp3
с голосовой дорожкой 110 BPM длительностью 60 секунд (см. README.md
о том, как сгенерировать с помощью FFmpeg).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

log = logging.getLogger("spas.metronome")

AUDIO_DIR = Path(__file__).resolve().parents[1] / "audio"


async def send_audio_metronome(bot: Bot, chat_id: int, bpm: int = 110) -> bool:
    """Если есть mp3-файл audio/metronome_{bpm}.mp3 — отправляем его."""
    file_path = AUDIO_DIR / f"metronome_{bpm}.mp3"
    if not file_path.exists():
        return False
    await bot.send_audio(
        chat_id=chat_id,
        audio=FSInputFile(file_path),
        caption=f"🥁 Метроном {bpm} ударов/мин — для СЛР. Жмите в этом темпе.",
    )
    return True


async def send_text_metronome(bot: Bot, chat_id: int, bpm: int = 110, seconds: int = 30) -> None:
    """Текстовый метроном: пульсирующее сообщение."""
    interval = 60.0 / bpm
    total_beats = int(seconds * bpm / 60)
    msg = await bot.send_message(chat_id, f"🥁 Темп {bpm}/мин — нажми, нажми, нажми…")
    try:
        for i in range(total_beats):
            await asyncio.sleep(interval)
            if i % 4 == 0:
                with contextlib.suppress(Exception):
                    await msg.edit_text(f"🥁 Темп {bpm}/мин\nУдар {i + 1} из {total_beats}")
        await msg.edit_text("✅ Метроном завершён. Продолжай в этом темпе сам(а).")
    except asyncio.CancelledError:
        pass
