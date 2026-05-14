"""Многостраничный PDF-методичка СПАС.

Запуск: ``python tools/generate_methodology_pdf.py``.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

try:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except ModuleNotFoundError:  # pragma: no cover
    print("reportlab не установлен. Запусти `pip install -r requirements-dev.txt`.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "build"
OUT_PATH = OUT_DIR / "spas_methodology.pdf"

PAGE_W, PAGE_H = A4
MARGIN = 56
ACCENT = HexColor("#FF3B30")
DARK = HexColor("#0B0D10")
MUTED = HexColor("#5C6470")


SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Назначение",
        [
            "СПАС — справочно-обучающий Telegram-бот по первой помощи, "
            "ориентированный на подростков 14–17 лет. Цель — закрыть пробел между "
            "школьным курсом ОБЖ и реальной готовностью действовать.",
            "Бот не ставит диагнозов и не заменяет 112/103. Это всегда первое "
            "действие в опасной ситуации.",
        ],
    ),
    (
        "2. Источники",
        [
            "Российский Национальный Совет по реанимации (НСР), методические " "указания базовой СЛР.",
            "European Resuscitation Council Guidelines 2021 (ERC).",
            "Открытые материалы Минздрава РФ и Российского Красного Креста.",
            "Все спорные шаги перед публикацией проходят медицинскую вычитку.",
        ],
    ),
    (
        "3. Структура контента",
        [
            "30 сценариев в трёх категориях: критические, срочные, лёгкие.",
            "Каждый сценарий — иконка, краткая сводка, шаги, телефон, метроном "
            "(если применимо), pre-test и post-test.",
            "Pre-test замеряет исходный уровень, post-test — приобретённое знание; "
            "разница даёт прирост компетенции (учётная метрика для жюри).",
        ],
    ),
    (
        "4. Дополнительные модули",
        [
            "Panic-режим: дыхание 6/мин, упражнение 5-4-3-2-1, быстрый triage.",
            "Чек-лист «Что сказать диспетчеру 112».",
            "Краудсорс АНД (/add_aed) с модерацией.",
            "Цифровой сертификат после ≥3 завершённых сценариев.",
            "LLM-слой для свободных вопросов (GigaChat / YandexGPT) с жёстким "
            "промптом «не диагностируй, всегда напоминай о 112».",
        ],
    ),
    (
        "5. Метрики пилота",
        [
            "DAU/MAU, completion rate (цель ≥70%), время до первого ответа.",
            "Pre→Post score (цель: с ≤30% до ≥80%).",
            "NPS (цель ≥+40), географическое покрытие (≥5 регионов).",
            "Анкета пилота: subjectively-rated готовность до и после, " "качественные комментарии.",
        ],
    ),
    (
        "6. Лицензии",
        [
            "Код: Apache License 2.0 (LICENSE).",
            "Контент (сценарии, методичка, лендинг-тексты, инфографика): "
            "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 "
            "(LICENSE-CONTENT).",
            "Любая школа или СОНКО может развернуть свой форк за час: см. "
            "README.md, секция «Деплой за 30 минут».",
        ],
    ),
    (
        "7. Ограничения",
        [
            "СПАС — справочный сервис. Не ставит диагнозов, не заменяет скорую.",
            "В каждом сценарии телефон 112 — кнопка с tel: deep link.",
            "Бот не собирает медицинских ПДн. Для аналитики хранится "
            "user_id, имя пользователя, регион (если указан), события клика и "
            "результаты тестов.",
            "Все скриншоты и фото пользователей публикуются только с согласия.",
        ],
    ),
    (
        "8. План масштабирования",
        [
            "До 31.05.2026: 200+ пользователей, 5+ регионов, 4+ письма поддержки.",
            "До 31.12.2026: 5 000+ пользователей, региональные методички, "
            "3 публикации, 2 партнёрства с региональными СОНКО.",
            "В перспективе — мобильное PWA, открытие AED-карты на лендинге, "
            "интеграция с Движением Первых.",
        ],
    ),
]


def draw_header(c: canvas.Canvas, page_n: int) -> None:
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, PAGE_H - MARGIN + 18, "СПАС — методичка")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN + 18, f"стр. {page_n}")


def draw_footer(c: canvas.Canvas) -> None:
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN, MARGIN - 24, "При опасности — 112. Это справочный сервис.")
    c.drawRightString(
        PAGE_W - MARGIN,
        MARGIN - 24,
        "github.com/desirewarlockstaple/spas-ai · CC BY-NC-SA 4.0",
    )


def draw_cover(c: canvas.Canvas) -> None:
    c.setFillColor(ACCENT)
    c.rect(0, PAGE_H - 220, PAGE_W, 220, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 56)
    c.drawString(MARGIN, PAGE_H - 130, "СПАС")
    c.setFont("Helvetica", 18)
    c.drawString(MARGIN, PAGE_H - 165, "AI-помощник первой помощи")
    c.drawString(MARGIN, PAGE_H - 195, "Методичка проекта · версия 0.2.0 · 2026")

    c.setFillColor(DARK)
    c.setFont("Helvetica", 12)
    intro = (
        "Эта методичка — внутренний документ пилота для конкурса "
        "«Моя страна — Моя Россия» 2026 (номинация «Моё здоровье»). "
        "Документ описывает источники, структуру контента, метрики и план "
        "масштабирования."
    )
    y = PAGE_H - 280
    for chunk in textwrap.wrap(intro, width=92):
        c.drawString(MARGIN, y, chunk)
        y -= 18

    c.setFillColor(MUTED)
    c.setFont("Helvetica-Oblique", 11)
    c.drawString(MARGIN, MARGIN + 40, "Контент распространяется по CC BY-NC-SA 4.0, код — Apache 2.0.")


def draw_section(c: canvas.Canvas, title: str, paragraphs: list[str]) -> None:
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 18)
    y = PAGE_H - MARGIN - 8
    c.drawString(MARGIN, y, title)
    y -= 28
    c.setFont("Helvetica", 11)
    for para in paragraphs:
        for chunk in textwrap.wrap(para, width=92):
            if y < MARGIN + 60:
                return
            c.drawString(MARGIN, y, chunk)
            y -= 16
        y -= 8


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT_PATH), pagesize=A4)

    draw_cover(c)
    draw_footer(c)
    c.showPage()

    for i, (title, paragraphs) in enumerate(SECTIONS, start=2):
        draw_header(c, i)
        draw_section(c, title, paragraphs)
        draw_footer(c)
        c.showPage()

    c.save()
    print(f"OK: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
