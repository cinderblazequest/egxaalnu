"""Vision (C2): rate limit и enabled-flag (без сети)."""

from __future__ import annotations

from bot import vision


def test_vision_disabled_without_key(monkeypatch) -> None:
    monkeypatch.delenv("GIGACHAT_API_KEY", raising=False)
    assert not vision.vision_enabled()


def test_vision_enabled_when_key_set(monkeypatch) -> None:
    monkeypatch.setenv("GIGACHAT_API_KEY", "x")
    assert vision.vision_enabled()


def test_rate_limit_blocks_after_threshold() -> None:
    # Reset history for the test user
    vision._user_history[999].clear()
    for _ in range(vision._VISION_RATE):
        assert not vision._hit_rate_limit(999)
    assert vision._hit_rate_limit(999)


def test_release_rate_slot_decreases_count() -> None:
    vision._user_history[1000].clear()
    vision._hit_rate_limit(1000)
    assert len(vision._user_history[1000]) == 1
    vision._release_rate_slot(1000)
    assert len(vision._user_history[1000]) == 0
