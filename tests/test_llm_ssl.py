"""Smoke tests for the GigaChat SSL bootstrap.

These tests do not hit the network — they only verify that the Russian
Trusted CA bundle ships with the repo, can be parsed by Python's
:mod:`ssl` module, and that the helper in :mod:`bot.llm` returns a usable
SSL context.
"""

from __future__ import annotations

import ssl

from bot.llm import _RUSSIAN_CA_BUNDLE, _gigachat_ssl_context


def test_russian_ca_bundle_present() -> None:
    assert _RUSSIAN_CA_BUNDLE.is_file(), (
        f"Russian Trusted CA bundle is missing at {_RUSSIAN_CA_BUNDLE}. "
        "Re-run `make ssl` or download "
        "https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer "
        "and `..._sub_ca.cer` into ssl/."
    )


def test_russian_ca_bundle_loads_into_ssl_context() -> None:
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(_RUSSIAN_CA_BUNDLE))


def test_gigachat_ssl_context_returns_context() -> None:
    ctx = _gigachat_ssl_context()
    assert ctx is not None
    assert isinstance(ctx, ssl.SSLContext)
