"""Tests for accessibility plain-text rendering."""

from __future__ import annotations

from bot.accessibility import plain_text, render


def test_plain_text_strips_html() -> None:
    assert plain_text("<b>hi</b>") == "hi"
    assert "<" not in plain_text('<a href="x">link</a>')


def test_plain_text_strips_emoji() -> None:
    out = plain_text("🚑 hello 🆘")
    assert "🚑" not in out
    assert "🆘" not in out
    assert "hello" in out


def test_plain_text_collapses_whitespace() -> None:
    assert plain_text("a\n\n\n\nb") == "a\n\nb"
    assert plain_text("a    b") == "a b"


def test_render_passthrough_when_disabled() -> None:
    html = "<b>hi</b> 🚑"
    assert render(html, accessibility=False) == html


def test_render_strips_when_enabled() -> None:
    html = "<b>hi</b> 🚑"
    out = render(html, accessibility=True)
    assert "🚑" not in out
    assert "<b>" not in out
    assert "hi" in out


def test_plain_text_decodes_html_entities() -> None:
    assert "<" in plain_text("&lt;script&gt;")
    assert ">" in plain_text("&lt;script&gt;")
