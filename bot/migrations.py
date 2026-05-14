"""Lightweight schema migrations for the SQLite store.

We don't need full Alembic for a single-file SQLite DB. Each migration is
a Python coroutine that takes an ``aiosqlite.Connection`` and a sequence
number; the framework records what's been applied in a ``schema_version``
table and runs anything new in order. New migrations should APPEND to
``MIGRATIONS`` and never edit existing ones.

Idempotent on every boot: if all migrations are applied, this is a no-op.
"""

from __future__ import annotations

import datetime as _dt
import logging
from collections.abc import Awaitable, Callable

import aiosqlite

log = logging.getLogger("spas.migrations")

Migration = Callable[[aiosqlite.Connection], Awaitable[None]]


async def _ensure_schema_version(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        """
    )
    await conn.commit()


async def _current_version(conn: aiosqlite.Connection) -> int:
    cur = await conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    row = await cur.fetchone()
    return int(row[0] if row else 0)


async def _record_version(conn: aiosqlite.Connection, version: int) -> None:
    await conn.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES(?, ?)",
        (version, _dt.datetime.now(_dt.UTC).isoformat()),
    )
    await conn.commit()


# --- migrations -------------------------------------------------------


async def _m001_user_settings(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            language TEXT NOT NULL DEFAULT 'ru',
            accessibility INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """
    )
    await conn.commit()


async def _m002_xp(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_xp (
            user_id INTEGER PRIMARY KEY,
            xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 1,
            achievements TEXT NOT NULL DEFAULT '[]',
            streak_days INTEGER NOT NULL DEFAULT 0,
            last_active TEXT
        );
        """
    )
    await conn.commit()


async def _m003_classes(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            invite_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_classes_teacher ON classes(teacher_id);

        CREATE TABLE IF NOT EXISTS class_members (
            class_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            nickname TEXT,
            PRIMARY KEY (class_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_members_user ON class_members(user_id);
        """
    )
    await conn.commit()


async def _m004_sos_contacts(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sos_contacts (
            user_id INTEGER PRIMARY KEY,
            contact_chat_id INTEGER,
            contact_username TEXT,
            display_name TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    await conn.commit()


async def _m005_ab_assignments(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ab_assignments (
            user_id INTEGER NOT NULL,
            experiment TEXT NOT NULL,
            variant TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY (user_id, experiment)
        );
        """
    )
    await conn.commit()


async def _m006_consent(conn: aiosqlite.Connection) -> None:
    """152-ФЗ: журнал согласий на обработку ПДн.

    Поле ``consent_pdn_at`` в ``user_settings`` хранит время последнего согласия,
    но мы также ведём append-only журнал событий согласия и отзыва — это нужно
    для аудита по 152-ФЗ.
    """
    await conn.executescript(
        """
        ALTER TABLE user_settings ADD COLUMN consent_pdn_at TEXT;
        ALTER TABLE user_settings ADD COLUMN consent_pdn_version TEXT;

        CREATE TABLE IF NOT EXISTS consent_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            version TEXT,
            details TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_consent_user ON consent_log(user_id, ts);
        """
    )
    await conn.commit()


async def _m007_audit_log(conn: aiosqlite.Connection) -> None:
    """Audit log для административных и privileged-действий (H1)."""
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            actor_id INTEGER,
            action TEXT NOT NULL,
            target TEXT,
            details TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id, ts);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, ts);
        """
    )
    await conn.commit()


async def _m008_alert_subscriptions(conn: aiosqlite.Connection) -> None:
    """Подписки на алерты МЧС по регионам (C7)."""
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS alert_subscriptions (
            user_id INTEGER NOT NULL,
            region TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, region)
        );
        CREATE INDEX IF NOT EXISTS idx_alert_region ON alert_subscriptions(region);

        CREATE TABLE IF NOT EXISTS alerts_seen (
            guid TEXT PRIMARY KEY,
            ts TEXT NOT NULL
        );
        """
    )
    await conn.commit()


async def _m009_max_user_state(conn: aiosqlite.Connection) -> None:
    """Состояние Max-бота: текущий шаг сценария, флаг platform у users.

    ``users.platform`` отличает пользователей Telegram (по умолчанию) от Max.
    Это нужно для аналитики и для разделения лидерборда, если вдруг
    понадобится в будущем.

    ``max_user_state`` хранит, на каком шаге сценария находится конкретный
    Max-пользователь — чтобы прохождение переживало рестарт бота.
    """
    cur = await conn.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in await cur.fetchall()}
    if "platform" not in cols:
        await conn.execute("ALTER TABLE users ADD COLUMN platform TEXT NOT NULL DEFAULT 'telegram'")
    await conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_users_platform ON users(platform);

        CREATE TABLE IF NOT EXISTS max_user_state (
            user_id INTEGER PRIMARY KEY,
            scenario_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            step_idx INTEGER NOT NULL DEFAULT 0,
            q_idx INTEGER NOT NULL DEFAULT 0,
            pre_correct INTEGER NOT NULL DEFAULT 0,
            pre_total INTEGER NOT NULL DEFAULT 0,
            post_correct INTEGER NOT NULL DEFAULT 0,
            post_total INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """
    )
    await conn.commit()


MIGRATIONS: list[tuple[int, Migration]] = [
    (1, _m001_user_settings),
    (2, _m002_xp),
    (3, _m003_classes),
    (4, _m004_sos_contacts),
    (5, _m005_ab_assignments),
    (6, _m006_consent),
    (7, _m007_audit_log),
    (8, _m008_alert_subscriptions),
    (9, _m009_max_user_state),
]


async def run_migrations(conn: aiosqlite.Connection) -> int:
    """Apply any pending migrations. Returns the new schema version."""
    await _ensure_schema_version(conn)
    current = await _current_version(conn)
    applied = 0
    for version, migrate in MIGRATIONS:
        if version <= current:
            continue
        log.info("applying migration %d", version)
        await migrate(conn)
        await _record_version(conn, version)
        applied += 1
    if applied:
        log.info("applied %d migration(s); now at version %d", applied, current + applied)
    return current + applied
