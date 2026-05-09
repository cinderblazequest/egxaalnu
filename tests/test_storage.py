"""Тесты хранилища (SQLite)."""

from __future__ import annotations

import pytest

from bot.storage import Storage


@pytest.fixture
async def storage(tmp_path) -> Storage:
    s = Storage(str(tmp_path / "test.db"))
    await s.init()
    try:
        yield s
    finally:
        await s.close()


async def test_log_event_persists(storage: Storage) -> None:
    await storage.upsert_user(1, "alice")
    await storage.log_event(1, "start", None)
    await storage.log_event(1, "scenario_open", "cardiac_arrest_adult")
    metrics = await storage.metrics()
    assert metrics["users_total"] == 1


async def test_count_distinct_completed_scenarios(storage: Storage) -> None:
    await storage.upsert_user(7, "bob")
    for sid in ("a", "a", "b", "c"):
        await storage.log_event(7, "scenario_complete", sid)
    assert await storage.count_distinct_completed_scenarios(7) == 3


async def test_save_test_results_aggregate(storage: Storage) -> None:
    await storage.upsert_user(2, "carol")
    await storage.save_test(2, "x", "pre", correct=1, total=3)
    await storage.save_test(2, "x", "post", correct=3, total=3)
    metrics = await storage.metrics()
    assert metrics["pre_score_avg"] == pytest.approx(1 / 3, abs=0.01)
    assert metrics["post_score_avg"] == pytest.approx(1.0, abs=0.01)


async def test_aed_submissions_lifecycle(storage: Storage) -> None:
    sub_id = await storage.insert_aed_submission(
        user_id=10,
        city="Москва",
        name="ТРЦ",
        note=None,
        lat=55.7,
        lon=37.6,
        photo_file_id=None,
    )
    pending = await storage.list_pending_aed()
    assert any(p["id"] == sub_id for p in pending)
    assert await storage.update_aed_status(sub_id, "approved")
    pending = await storage.list_pending_aed()
    assert all(p["id"] != sub_id for p in pending)


async def test_invalid_aed_status_rejected(storage: Storage) -> None:
    sub_id = await storage.insert_aed_submission(
        user_id=11,
        city=None,
        name=None,
        note=None,
        lat=55.7,
        lon=37.6,
        photo_file_id=None,
    )
    with pytest.raises(ValueError):
        await storage.update_aed_status(sub_id, "ohnoes")


async def test_save_certificate(storage: Storage) -> None:
    await storage.save_certificate(42, "SPAS-2026-000001-AAAA", "Иван Петров", 5)
    # second call with same code should not raise (replace semantics)
    await storage.save_certificate(42, "SPAS-2026-000001-AAAA", "Иван Петров", 6)
