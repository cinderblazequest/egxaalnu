"""Тесты consent + audit_log + alert subscriptions + forget_me + export."""

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


# --- consent (H8) -----------------------------------------------------


async def test_consent_default_false(storage: Storage) -> None:
    assert not await storage.has_consented(1)


async def test_consent_record_and_check(storage: Storage) -> None:
    await storage.record_consent(1, version="v1")
    assert await storage.has_consented(1)
    assert await storage.has_consented(1, version="v1")
    assert not await storage.has_consented(1, version="v2")


async def test_consent_revoke_resets_state(storage: Storage) -> None:
    await storage.record_consent(2, version="v1")
    await storage.revoke_consent(2)
    assert not await storage.has_consented(2)


async def test_consent_log_appends_each_action(storage: Storage) -> None:
    await storage.record_consent(3, version="v1")
    await storage.revoke_consent(3)
    await storage.record_consent(3, version="v2")
    cur = await storage.db.execute("SELECT action, version FROM consent_log WHERE user_id=3 ORDER BY id")
    rows = await cur.fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        ("accept", "v1"),
        ("revoke", None),
        ("accept", "v2"),
    ]


# --- forget_me (H3) ---------------------------------------------------


async def test_forget_user_deletes_everything(storage: Storage) -> None:
    uid = 42
    await storage.upsert_user(uid, "alice")
    await storage.log_event(uid, "start")
    await storage.save_xp(
        uid,
        xp=100,
        level=2,
        achievements=["first_aid"],
        streak_days=3,
        last_active="2026-01-01",
    )
    await storage.record_consent(uid, version="v1")
    await storage.add_alert_subscription(uid, "moscow")
    stats = await storage.forget_user(uid)
    assert stats["users"] == 1
    assert not await storage.has_consented(uid)
    cur = await storage.db.execute("SELECT 1 FROM events WHERE user_id=?", (uid,))
    assert await cur.fetchone() is None
    cur = await storage.db.execute("SELECT 1 FROM user_xp WHERE user_id=?", (uid,))
    assert await cur.fetchone() is None
    cur = await storage.db.execute("SELECT 1 FROM alert_subscriptions WHERE user_id=?", (uid,))
    assert await cur.fetchone() is None


# --- audit log (H1) ---------------------------------------------------


async def test_audit_log_records_action(storage: Storage) -> None:
    await storage.audit("admin_export", actor_id=1, target="users", details="rows=5")
    rows = await storage.list_audit(limit=10)
    assert len(rows) == 1
    assert rows[0]["action"] == "admin_export"
    assert rows[0]["target"] == "users"
    assert rows[0]["actor_id"] == 1


async def test_audit_log_orders_desc(storage: Storage) -> None:
    await storage.audit("a", actor_id=1)
    await storage.audit("b", actor_id=1)
    rows = await storage.list_audit(limit=10)
    assert rows[0]["action"] == "b"
    assert rows[1]["action"] == "a"


# --- alert subscriptions (C7) -----------------------------------------


async def test_alert_subscription_lifecycle(storage: Storage) -> None:
    assert await storage.add_alert_subscription(1, "Moscow")
    # duplicate fails silently
    assert not await storage.add_alert_subscription(1, "moscow")
    assert await storage.list_alert_subscriptions(1) == ["moscow"]
    assert 1 in await storage.subscribers_for_region("moscow")
    deleted = await storage.remove_alert_subscription(1)
    assert deleted == 1
    assert await storage.list_alert_subscriptions(1) == []


async def test_alert_seen_dedup(storage: Storage) -> None:
    assert not await storage.alert_seen("g1")
    await storage.mark_alert_seen("g1")
    assert await storage.alert_seen("g1")
    # Idempotent: marking twice doesn't blow up
    await storage.mark_alert_seen("g1")


# --- /admin_export (H4) -----------------------------------------------


async def test_export_table_returns_columns_and_rows(storage: Storage) -> None:
    await storage.upsert_user(1, "alice")
    cols, rows = await storage.export_table("users")
    assert "user_id" in cols
    assert any(r[cols.index("user_id")] == 1 for r in rows)


async def test_export_table_rejects_unknown(storage: Storage) -> None:
    with pytest.raises(ValueError):
        await storage.export_table("sqlite_master")
