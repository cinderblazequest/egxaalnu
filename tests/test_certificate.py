"""Тесты генератора сертификата."""

from __future__ import annotations

import datetime as dt

from bot.certificate import (
    CertificatePayload,
    build_certificate_code,
    save_certificate_png,
)


def test_code_format_is_stable() -> None:
    issued = dt.datetime(2026, 5, 31, 12, 0, tzinfo=dt.UTC)
    a = build_certificate_code(123, 5, issued)
    b = build_certificate_code(123, 5, issued)
    assert a == b
    assert a.startswith("SPAS-2026-")
    assert len(a.split("-")) == 4


def test_code_changes_with_user() -> None:
    issued = dt.datetime(2026, 5, 31, tzinfo=dt.UTC)
    assert build_certificate_code(1, 3, issued) != build_certificate_code(2, 3, issued)


def test_render_returns_png_bytes() -> None:
    payload = CertificatePayload(
        user_id=42,
        full_name="Иван Петров",
        scenarios_completed=5,
        issued_at=dt.datetime(2026, 5, 31, tzinfo=dt.UTC),
        code="SPAS-2026-000001-ABCD",
    )
    blob = save_certificate_png(payload)
    assert isinstance(blob, bytes)
    assert blob.startswith(b"\x89PNG"), "должен быть валидный PNG"
    assert len(blob) > 1024
