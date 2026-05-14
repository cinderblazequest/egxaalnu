"""Generate ``docs/finance_model.xlsx`` from ``docs/finance_model.md``.

Парсит первую обнаруженную таблицу markdown и кладёт её в xlsx —
это позволяет жюри открыть финмодель в Excel без необходимости
«перебивать данные руками». Используется ``openpyxl`` (стандартная
зависимость для xlsx) либо встроенный csv → xlsx через pandas.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "docs" / "finance_model.md"
DEFAULT_OUT = ROOT / "docs" / "finance_model.xlsx"


def _parse_markdown_tables(md_text: str) -> list[list[list[str]]]:
    """Return a list of tables; each table is a list of rows; row is list of cells."""
    tables: list[list[list[str]]] = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and line.endswith("|") and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            # Header separator looks like |---|---| with optional :
            if re.fullmatch(r"\|[\s:|-]+\|", sep):
                rows: list[list[str]] = [_split_row(line)]
                j = i + 2
                while j < len(lines) and lines[j].strip().startswith("|"):
                    rows.append(_split_row(lines[j].strip()))
                    j += 1
                tables.append(rows)
                i = j
                continue
        i += 1
    return tables


def _split_row(line: str) -> list[str]:
    parts = [c.strip() for c in line.strip("|").split("|")]
    return parts


def to_xlsx(src: Path = DEFAULT_SRC, out: Path = DEFAULT_OUT) -> Path:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover — handled at runtime
        raise SystemExit(
            "openpyxl is required. Install with `pip install openpyxl` " "or use requirements-dev.txt."
        ) from exc

    md_text = src.read_text(encoding="utf-8")
    tables = _parse_markdown_tables(md_text)
    if not tables:
        raise SystemExit(f"No markdown tables found in {src}")

    wb = Workbook()
    # Drop the default empty sheet
    if wb.active is not None:
        wb.remove(wb.active)

    for idx, table in enumerate(tables, start=1):
        sheet_name = f"Таблица_{idx}"
        ws = wb.create_sheet(title=sheet_name[:31])
        for row in table:
            ws.append(row)
        # Bold header row
        for cell in ws[1]:
            cell.font = cell.font.copy(bold=True)
        # Auto-width estimate
        for col in ws.columns:
            length = max((len(str(c.value or "")) for c in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(40, length + 2)

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert finance_model.md tables to xlsx")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = to_xlsx(args.src, args.out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
