"""Регрессионный тест: код сертификата детерминирован между процессами.

Python `hash()` рандомизирует строки между процессами через PYTHONHASHSEED,
поэтому ранее повторный запуск бота возвращал бы РАЗНЫЕ коды для одного и
того же пользователя/дня. После перехода на SHA-256 значение должно быть
ВОСПРОИЗВОДИМО в произвольном процессе.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys

from bot.certificate import build_certificate_code

ISSUED = dt.datetime(2026, 5, 31, 12, 0, tzinfo=dt.UTC)


def test_code_is_deterministic_in_same_process() -> None:
    a = build_certificate_code(123456, 5, ISSUED)
    b = build_certificate_code(123456, 5, ISSUED)
    assert a == b


def test_code_is_deterministic_across_processes() -> None:
    """С разным PYTHONHASHSEED значение должно остаться тем же."""
    expected = build_certificate_code(123456, 5, ISSUED)
    code = """
import datetime as dt
from bot.certificate import build_certificate_code
print(build_certificate_code(123456, 5, dt.datetime(2026, 5, 31, 12, 0, tzinfo=dt.UTC)))
""".strip()
    out_a = (
        subprocess.check_output(
            [sys.executable, "-c", code],
            env={"PYTHONHASHSEED": "1"},
            cwd=__import__("os").getcwd(),
        )
        .decode()
        .strip()
    )
    out_b = (
        subprocess.check_output(
            [sys.executable, "-c", code],
            env={"PYTHONHASHSEED": "999"},
            cwd=__import__("os").getcwd(),
        )
        .decode()
        .strip()
    )
    assert out_a == expected
    assert out_b == expected


def test_code_changes_with_day() -> None:
    a = build_certificate_code(7, 3, dt.datetime(2026, 5, 31, tzinfo=dt.UTC))
    b = build_certificate_code(7, 3, dt.datetime(2026, 6, 1, tzinfo=dt.UTC))
    assert a != b
