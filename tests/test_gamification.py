"""Unit tests for gamification: XP, levels, streaks, achievements."""

from __future__ import annotations

from bot.gamification import (
    ACHIEVEMENTS,
    LEVEL_THRESHOLDS,
    evaluate_event,
    level_for_xp,
    next_level_target,
    render_profile,
    update_streak,
)


def test_level_for_xp_table_is_monotonic() -> None:
    last_xp = -1
    for level, xp_threshold, _label in LEVEL_THRESHOLDS:
        assert xp_threshold > last_xp, f"Level {level} threshold {xp_threshold} must increase"
        last_xp = xp_threshold


def test_level_for_xp_basic() -> None:
    assert level_for_xp(0) == (1, "Новичок")
    assert level_for_xp(29) == (1, "Новичок")
    assert level_for_xp(30)[0] == 2
    assert level_for_xp(10_000)[0] == LEVEL_THRESHOLDS[-1][0]


def test_next_level_target_at_max() -> None:
    assert next_level_target(LEVEL_THRESHOLDS[-1][1]) is None


def test_update_streak_first_time() -> None:
    assert update_streak(None) == 1


def test_update_streak_consecutive() -> None:
    assert update_streak("2025-01-01T10:00:00", today="2025-01-02") == 1


def test_update_streak_break() -> None:
    assert update_streak("2025-01-01T10:00:00", today="2025-01-04") == -1


def test_update_streak_same_day() -> None:
    assert update_streak("2025-01-02T10:00:00", today="2025-01-02") == 0


def test_evaluate_event_scenario_complete_first_time() -> None:
    state = {"xp": 0, "level": 1, "achievements": [], "streak_days": 0, "last_active": None}
    delta = evaluate_event(
        state=state, event="scenario_complete", completed_scenarios={"a"}, perfect_post=True
    )
    assert delta.xp_gained > 0
    titles = {a.code for a in delta.new_achievements}
    assert "first_step" in titles
    assert "perfect_post" in titles


def test_evaluate_event_five_scenarios_unlocks_milestone() -> None:
    state = {
        "xp": 100,
        "level": 2,
        "achievements": ["first_step"],
        "streak_days": 0,
        "last_active": None,
    }
    delta = evaluate_event(
        state=state,
        event="scenario_complete",
        completed_scenarios={f"s{i}" for i in range(5)},
    )
    codes = {a.code for a in delta.new_achievements}
    assert "five_in_one" in codes


def test_evaluate_event_panic_breathe_unlocks_calmed() -> None:
    state = {"xp": 0, "level": 1, "achievements": [], "streak_days": 0, "last_active": None}
    delta = evaluate_event(state=state, event="panic_breathe")
    codes = {a.code for a in delta.new_achievements}
    assert "panic_calmed" in codes


def test_evaluate_event_dispatcher_done_unlocks_pro() -> None:
    state = {"xp": 0, "level": 1, "achievements": [], "streak_days": 0, "last_active": None}
    delta = evaluate_event(state=state, event="dispatcher_done")
    codes = {a.code for a in delta.new_achievements}
    assert "dispatcher_pro" in codes


def test_evaluate_event_same_day_no_double_streak() -> None:
    today = "2025-06-01T08:00:00"
    state1 = {
        "xp": 0,
        "level": 1,
        "achievements": [],
        "streak_days": 1,
        "last_active": today,
    }
    delta = evaluate_event(state=state1, event="panic_breathe", today="2025-06-01")
    assert delta.streak_days == 1


def test_render_profile_includes_level_and_xp() -> None:
    state = {
        "xp": 50,
        "level": 2,
        "achievements": ["first_step"],
        "streak_days": 3,
    }
    out = render_profile(state)
    assert "Уровень" in out
    assert "XP" in out
    assert ACHIEVEMENTS["first_step"].title in out


def test_render_profile_empty_state() -> None:
    state: dict = {}
    out = render_profile(state)
    assert "Уровень" in out
    assert "Ачивки появятся" in out
