"""Генератор PNG-сертификатов «СПАС: я знаю первую помощь»."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("spas.certificate")


CERT_W, CERT_H = 1240, 1754  # A4 portrait @ 150 dpi
PADDING = 96
ACCENT = (255, 59, 48)
DARK = (11, 13, 16)
MUTED = (170, 178, 188)
BG = (244, 246, 248)


@dataclass(frozen=True)
class CertificatePayload:
    user_id: int
    full_name: str
    scenarios_completed: int
    issued_at: dt.datetime
    code: str
    bot_url: str = "https://t.me/spas_first_aid_bot"


def build_certificate_code(user_id: int, scenarios_completed: int, issued_at: dt.datetime) -> str:
    """Короткий публичный код вида ``SPAS-2026-000123-A1B2``.

    Стабильно зависит от user_id + день выдачи + количество сценариев — поэтому
    повторная генерация в тот же день вернёт тот же код, а в следующий день
    другой (так пилот может выдавать «обновлённые» сертификаты).

    Использует SHA-256, чтобы код был детерминированным между перезапусками
    бота (Python ``hash()`` рандомизирует строки через PYTHONHASHSEED).
    """
    seed = f"{user_id}:{scenarios_completed}:{issued_at.strftime('%Y%m%d')}"
    digest = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big")
    suffix = format(digest % (36**4), "X").rjust(4, "0")[:4]
    serial = format(digest // (36**4) % 1_000_000, "06d")
    return f"SPAS-{issued_at.year}-{serial}-{suffix}"


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size=size)
    return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, y: int, text: str, font: ImageFont.ImageFont, fill) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((CERT_W - w) // 2, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def render_certificate(payload: CertificatePayload) -> Image.Image:
    img = Image.new("RGB", (CERT_W, CERT_H), BG)
    d = ImageDraw.Draw(img)

    d.rectangle(
        (PADDING - 16, PADDING - 16, CERT_W - PADDING + 16, CERT_H - PADDING + 16), outline=ACCENT, width=6
    )

    title_font = _load_font(72)
    sub_font = _load_font(44)
    name_font = _load_font(64)
    body_font = _load_font(36)
    small_font = _load_font(28)
    code_font = _load_font(24)

    y = PADDING + 60
    y += _draw_centered(d, y, "СПАС", title_font, ACCENT) + 28
    y += _draw_centered(d, y, "AI-помощник первой помощи", sub_font, DARK) + 80

    y += _draw_centered(d, y, "Сертификат участника пилота", body_font, MUTED) + 60
    y += _draw_centered(d, y, payload.full_name, name_font, DARK) + 40

    body_lines = [
        f"прошёл(ла) {payload.scenarios_completed} сценариев первой помощи",
        f"в проекте СПАС, {payload.issued_at.strftime('%d.%m.%Y')}.",
        "",
        "Этот сертификат — внутренний знак участия в",
        "пилотном тестировании, не является официальным",
        "медицинским документом и не заменяет очное обучение.",
    ]
    for line in body_lines:
        y += _draw_centered(d, y, line, body_font, DARK if line else DARK) + 18

    y += 60

    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(f"{payload.bot_url}?start=cert_{payload.code}")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color=BG).convert("RGB")
    qr_size = 280
    qr_img = qr_img.resize((qr_size, qr_size))
    img.paste(qr_img, ((CERT_W - qr_size) // 2, y))
    y += qr_size + 12

    _draw_centered(d, y, f"Код: {payload.code}", code_font, MUTED)
    y += 60

    footer_y = CERT_H - PADDING - 80
    _draw_centered(
        d,
        footer_y,
        "Подписано: автор проекта СПАС · Открытый код Apache 2.0",
        small_font,
        MUTED,
    )
    _draw_centered(
        d,
        footer_y + 38,
        "При опасности — 112. Это справочный сервис.",
        small_font,
        ACCENT,
    )

    return img


def save_certificate_png(payload: CertificatePayload) -> bytes:
    img = render_certificate(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
