"""Generate PWA icons (192x192, 512x512) from a base palette.

Без зависимости от svg-рендеров (cairosvg тяжёлый и нестабилен на CI):
рисуем PIL-овским ImageDraw простой плюс с градиентом — внешне
совпадает с logo.svg. Для масштабирования и maskable PWA-иконки
этого достаточно.

Запуск::

    python -m tools.generate_icons
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "landing" / "icons"

RED_TOP = (230, 57, 70, 255)
RED_BOTTOM = (155, 14, 26, 255)
WHITE = (255, 255, 255, 255)
PAPER = (241, 250, 238, 255)


def _gradient_bg(size: int, top: tuple[int, int, int, int], bottom: tuple[int, int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (size, size), top)
    for y in range(size):
        ratio = y / max(1, size - 1)
        r = int(top[0] * (1 - ratio) + bottom[0] * ratio)
        g = int(top[1] * (1 - ratio) + bottom[1] * ratio)
        b = int(top[2] * (1 - ratio) + bottom[2] * ratio)
        for x in range(size):
            img.putpixel((x, y), (r, g, b, 255))
    return img


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size, size), radius=radius, fill=255)
    return mask


def _draw_cross(img: Image.Image, *, padding: float = 0.18, bar: float = 0.18) -> None:
    w, h = img.size
    d = ImageDraw.Draw(img)
    pad = int(w * padding)
    bar_w = int(w * bar)
    # vertical
    cx = w // 2
    cy = h // 2
    d.rounded_rectangle(
        (cx - bar_w // 2, pad, cx + bar_w // 2, h - pad),
        radius=int(bar_w * 0.18),
        fill=WHITE,
    )
    # horizontal
    d.rounded_rectangle(
        (pad, cy - bar_w // 2, w - pad, cy + bar_w // 2),
        radius=int(bar_w * 0.18),
        fill=WHITE,
    )


def _draw_brand(img: Image.Image, text: str = "СПАС") -> None:
    # Try to use Inter; fall back to default. Hidden caption only at 512px.
    if img.size[0] < 256:
        return
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", img.size[0] // 12)
    except OSError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (img.size[0] - text_w) // 2
    y = img.size[1] - text_h - img.size[1] // 12
    d.text((x, y), text, fill=WHITE, font=font)


def make_icon(size: int) -> Image.Image:
    bg = _gradient_bg(size, RED_TOP, RED_BOTTOM)
    radius = int(size * 0.22)
    mask = _rounded_mask(size, radius)
    # Composite onto a transparent base via mask so corners are alpha
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base.paste(bg, (0, 0), mask)
    # Soft shadow under the cross
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    _draw_cross(shadow)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=size // 80))
    base = Image.alpha_composite(base, shadow)
    cross = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    _draw_cross(cross)
    base = Image.alpha_composite(base, cross)
    _draw_brand(base)
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Render PWA icons from gradient + cross")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png"), (512, "icon-maskable-512.png")):
        img = make_icon(size)
        img.save(args.out / name, format="PNG", optimize=True)
        print(f"wrote {args.out / name}")
    # apple-touch-icon: 180x180
    img = make_icon(180)
    img.save(args.out / "apple-touch-icon.png", format="PNG", optimize=True)
    print(f"wrote {args.out / 'apple-touch-icon.png'}")


if __name__ == "__main__":
    main()
