"""Allow-list для имён таблиц в dashboard.py — защита от SQL-инъекции."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_dashboard_module():
    """Загрузить dashboard.py без запуска streamlit."""
    pytest.importorskip("streamlit")
    pytest.importorskip("pandas")
    path = Path(__file__).resolve().parents[1] / "dashboard.py"
    spec = importlib.util.spec_from_file_location("dashboard_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_allowed_tables_contains_known_names() -> None:
    dashboard = _load_dashboard_module()
    assert "users" in dashboard.ALLOWED_TABLES
    assert "events" in dashboard.ALLOWED_TABLES
    assert "feedback" in dashboard.ALLOWED_TABLES


def test_arbitrary_table_name_is_rejected() -> None:
    dashboard = _load_dashboard_module()
    with pytest.raises(ValueError):
        dashboard.load_table("users; DROP TABLE users;--")
    with pytest.raises(ValueError):
        dashboard.load_table("not_a_real_table")
