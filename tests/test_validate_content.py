"""Контентный валидатор должен находить наш content/ как корректный."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_validate_content_passes() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "tools.validate_content"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr or r.stdout
    assert "OK" in r.stdout
