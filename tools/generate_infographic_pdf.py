"""Одностраничная PDF-инфографика для жюри (A4 landscape).

Запуск: ``python tools/generate_infographic_pdf.py`` →
``docs/build/spas_infographic.pdf``.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
except ModuleNotFoundError:  # pragma: no cover
    print("reportlab не установлен. Запусти `pip install -r requirements-dev.txt`.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "build"
OUT_PATH = OUT_DIR / "spas_infographic.pdf"


PAGE_W, PAGE_H = landscape(A4)
ACCENT = HexColor("#FF3B30")
DARK = HexColor("#0B0D10")
MUTED = HexColor("#7A8390")
BG_BLOCK = HexColor("#F4F6F8")


def draw(c: canvas.Canvas) -> None:
    c.setFillColor(BG_BLOCK)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 44)
    c.drawString(36, PAGE_H - 70, "SPAS — first aid AI assistant")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 18)
    c.drawString(36, PAGE_H - 95, "30 scenarios | CPR metronome | AED map | 112 dispatcher checklist")

    box_y = PAGE_H - 280
    block_w = (PAGE_W - 96) / 2

    # Problem block
    c.setFillColor(HexColor("#FFF1EE"))
    c.roundRect(36, box_y, block_w, 160, 16, fill=1, stroke=0)
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(56, box_y + 122, "Проблема")
    c.setFillColor(DARK)
    c.setFont("Helvetica", 14)
    for i, line in enumerate(
        [
            "200–300 тыс. внезапных остановок сердца в РФ ежегодно (НСР).",
            "Выживаемость: 5–7 % vs 50–60 % в странах с подготовкой.",
            "Подростки 14–17 лет: 41 % боятся подойти, 67 % не помнят шаги ОБЖ.",
            "Никаких массовых учебных решений в Telegram, где они уже сидят.",
        ]
    ):
        c.drawString(56, box_y + 90 - i * 22, f"• {line}")

    # Solution block
    c.setFillColor(HexColor("#EAF7EE"))
    c.roundRect(60 + block_w, box_y, block_w, 160, 16, fill=1, stroke=0)
    c.setFillColor(HexColor("#34C759"))
    c.setFont("Helvetica-Bold", 28)
    c.drawString(80 + block_w, box_y + 122, "Решение")
    c.setFillColor(DARK)
    c.setFont("Helvetica", 14)
    for i, line in enumerate(
        [
            "Telegram-бот @spas_first_aid_bot — без установки приложения.",
            "30 сценариев + pre/post-test, голосовой метроном 110 BPM.",
            "Карта АНД + краудсорс, чек-лист «что сказать диспетчеру 112».",
            "Panic-режим, цифровой сертификат, открытый код Apache 2.0.",
        ]
    ):
        c.drawString(80 + block_w, box_y + 90 - i * 22, f"• {line}")

    # Numbers row
    metrics_y = 140
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(36, metrics_y + 70, "Метрики пилота (цели на 31.05.2026)")

    metrics = [
        ("200+", "уникальных пользователей"),
        ("≥70%", "completion rate сценариев"),
        ("≥+40", "NPS"),
        ("5+", "регионов"),
        ("4+", "писем поддержки"),
    ]
    metric_w = (PAGE_W - 96) / len(metrics)
    for i, (num, label) in enumerate(metrics):
        x = 36 + i * metric_w
        c.setFillColor(ACCENT)
        c.setFont("Helvetica-Bold", 36)
        c.drawString(x + 10, metrics_y + 30, num)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 12)
        c.drawString(x + 10, metrics_y + 12, label)

    # Footer
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10)
    c.drawString(
        36,
        24,
        "spas-ai · github.com/desirewarlockstaple/spas-ai · CC BY-NC-SA 4.0 (контент) + Apache 2.0 (код)",
    )
    c.setFillColor(ACCENT)
    c.drawRightString(PAGE_W - 36, 24, "При опасности — 112. Сервис справочный.")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT_PATH), pagesize=landscape(A4))
    draw(c)
    c.showPage()
    c.save()
    print(f"OK: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
