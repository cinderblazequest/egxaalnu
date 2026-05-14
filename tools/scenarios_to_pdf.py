"""Export 30 first-aid scenarios to a printable PDF (для школ без интернета).

Использует ``reportlab`` (уже в requirements-dev.txt). Запуск::

    python -m tools.scenarios_to_pdf  # → docs/spas_scenarios.pdf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_PATH = ROOT / "content" / "scenarios.json"
DEFAULT_OUT = ROOT / "docs" / "spas_scenarios.pdf"


def _register_cyrillic_font() -> str:
    """Register a Cyrillic-capable font with reportlab and return its name."""
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold"),
    ]
    registered = []
    for path, name in candidates:
        if Path(path).is_file():
            pdfmetrics.registerFont(TTFont(name, path))
            registered.append(name)
    if not registered:
        return "Helvetica"
    return registered[0]


def _styles(font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName=font.replace("Sans", "Sans-Bold") if "DejaVu" in font else font,
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1D3557"),
            spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName=font.replace("Sans", "Sans-Bold") if "DejaVu" in font else font,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#9B0E1A"),
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName=font,
            fontSize=11,
            leading=14,
        ),
        "step": ParagraphStyle(
            "step",
            parent=base["Normal"],
            fontName=font,
            fontSize=11,
            leading=14,
            leftIndent=12,
        ),
        "muted": ParagraphStyle(
            "muted",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            textColor=colors.HexColor("#6C757D"),
            leading=11,
        ),
    }


def _scenario_block(scenario: dict, styles: dict[str, ParagraphStyle]) -> list:
    flow: list = []
    title = f"{scenario.get('icon', '')} {scenario['title']}"
    flow.append(Paragraph(title, styles["h2"]))
    if scenario.get("phone"):
        flow.append(Paragraph(f"📞 Экстренный: {scenario['phone']}", styles["muted"]))
    if scenario.get("summary"):
        flow.append(Paragraph(scenario["summary"], styles["body"]))
    flow.append(Spacer(1, 4))
    for i, step in enumerate(scenario.get("steps", []), start=1):
        flow.append(Paragraph(f"<b>{i}.</b> {step}", styles["step"]))
    flow.append(Spacer(1, 4))
    flow.append(HRFlowable(width="100%", color=colors.HexColor("#A8DADC")))
    flow.append(Spacer(1, 8))
    return flow


def build_pdf(out_path: Path = DEFAULT_OUT, scenarios_path: Path = SCENARIOS_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    font = _register_cyrillic_font()
    styles = _styles(font)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title="СПАС: 30 сценариев первой помощи",
        author="SPAS team",
    )
    flow: list = []
    flow.append(Paragraph("СПАС — 30 сценариев первой помощи", styles["h1"]))
    flow.append(
        Paragraph(
            "Печатное издание для школ без интернета. Каждая страница — "
            "одна ситуация. Не заменяет звонок 112/103.",
            styles["muted"],
        )
    )
    flow.append(Spacer(1, 16))

    data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    scenarios = data.get("scenarios") if isinstance(data, dict) else data
    if not isinstance(scenarios, list):
        raise ValueError("scenarios.json must be a list or {scenarios: [...]}")
    for scenario in scenarios:
        flow.append(KeepTogether(_scenario_block(scenario, styles)))
    flow.append(PageBreak())
    flow.append(Paragraph("Дисклеймер", styles["h2"]))
    flow.append(
        Paragraph(
            "Этот документ — справочный. В реальной чрезвычайной ситуации "
            "сначала оцени безопасность места, потом звони 112 (или 103). "
            "Если не уверен в шаге — НЕ ВЫПОЛНЯЙ его. Лучше дать диспетчеру "
            "довести тебя по телефону.",
            styles["body"],
        )
    )
    doc.build(flow)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render scenarios.json to a printable PDF")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source", type=Path, default=SCENARIOS_PATH)
    args = parser.parse_args()
    out = build_pdf(args.out, args.source)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
