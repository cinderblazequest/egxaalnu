"""SQLite-хранилище для аналитики и состояний."""

from __future__ import annotations

import datetime as dt
import json
import logging
import secrets
from typing import Any

import aiosqlite

from bot.migrations import run_migrations

log = logging.getLogger("spas.storage")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    region TEXT,
    age INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    name TEXT NOT NULL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_name ON events(name, ts);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    nps INTEGER,
    comment TEXT
);

CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    correct INTEGER NOT NULL,
    total INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS aed_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    city TEXT,
    name TEXT,
    note TEXT,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    photo_file_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_aed_status ON aed_submissions(status, ts);

CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    scenarios_completed INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_certificates_user ON certificates(user_id);
"""


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


class Storage:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        version = await run_migrations(self._db)
        log.info("Storage ready: %s (schema v%d)", self.path, version)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage not initialised")
        return self._db

    async def upsert_user(self, user_id: int, username: str | None) -> None:
        now = _now()
        await self.db.execute(
            """
            INSERT INTO users(user_id, username, first_seen, last_seen)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
              last_seen = excluded.last_seen,
              username  = excluded.username
            """,
            (user_id, username, now, now),
        )
        await self.db.commit()

    async def log_event(self, user_id: int, name: str, payload: str | None = None) -> None:
        await self.db.execute(
            "INSERT INTO events(user_id, ts, name, payload) VALUES(?,?,?,?)",
            (user_id, _now(), name, payload),
        )
        await self.db.commit()

    async def save_feedback(self, user_id: int, nps: int | None, comment: str | None) -> None:
        await self.db.execute(
            "INSERT INTO feedback(user_id, ts, nps, comment) VALUES(?,?,?,?)",
            (user_id, _now(), nps, comment),
        )
        await self.db.commit()

    async def save_test(self, user_id: int, scenario_id: str, phase: str, correct: int, total: int) -> None:
        await self.db.execute(
            "INSERT INTO test_results(user_id, ts, scenario_id, phase, correct, total) VALUES(?,?,?,?,?,?)",
            (user_id, _now(), scenario_id, phase, correct, total),
        )
        await self.db.commit()

    async def count_distinct_completed_scenarios(self, user_id: int) -> int:
        cur = await self.db.execute(
            """
            SELECT COUNT(DISTINCT payload) FROM events
            WHERE user_id = ? AND name = 'scenario_complete' AND payload IS NOT NULL
            """,
            (user_id,),
        )
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def save_certificate(
        self, user_id: int, code: str, full_name: str, scenarios_completed: int
    ) -> None:
        await self.db.execute(
            """
            INSERT OR REPLACE INTO certificates(user_id, ts, code, full_name, scenarios_completed)
            VALUES(?, ?, ?, ?, ?)
            """,
            (user_id, _now(), code, full_name, scenarios_completed),
        )
        await self.db.commit()

    async def insert_aed_submission(
        self,
        *,
        user_id: int,
        city: str | None,
        name: str | None,
        note: str | None,
        lat: float,
        lon: float,
        photo_file_id: str | None,
    ) -> int:
        cur = await self.db.execute(
            """
            INSERT INTO aed_submissions(user_id, ts, city, name, note, lat, lon, photo_file_id, status)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (user_id, _now(), city, name, note, lat, lon, photo_file_id),
        )
        await self.db.commit()
        return int(cur.lastrowid or 0)

    async def list_pending_aed(self, limit: int = 20) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            """
            SELECT id, user_id, ts, city, name, note, lat, lon, photo_file_id
            FROM aed_submissions WHERE status='pending' ORDER BY ts ASC LIMIT ?
            """,
            (limit,),
        )
        rows = await cur.fetchall()
        keys = ("id", "user_id", "ts", "city", "name", "note", "lat", "lon", "photo_file_id")
        return [dict(zip(keys, row, strict=False)) for row in rows]

    async def update_aed_status(self, submission_id: int, status: str) -> bool:
        if status not in ("pending", "approved", "rejected"):
            raise ValueError(f"invalid status: {status}")
        cur = await self.db.execute(
            "UPDATE aed_submissions SET status=? WHERE id=?",
            (status, submission_id),
        )
        await self.db.commit()
        return (cur.rowcount or 0) > 0

    # --- user settings (language, accessibility) -----------------------

    async def get_user_settings(self, user_id: int) -> dict[str, Any]:
        cur = await self.db.execute(
            "SELECT language, accessibility FROM user_settings WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return {"language": "ru", "accessibility": False}
        return {"language": row[0], "accessibility": bool(row[1])}

    async def set_user_setting(
        self, user_id: int, *, language: str | None = None, accessibility: bool | None = None
    ) -> None:
        cur = await self.db.execute(
            "SELECT language, accessibility FROM user_settings WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        new_lang = language if language is not None else (row[0] if row else "ru")
        new_a11y = int(accessibility) if accessibility is not None else (int(row[1]) if row else 0)
        now = _now()
        if row:
            await self.db.execute(
                "UPDATE user_settings SET language=?, accessibility=?, updated_at=? WHERE user_id=?",
                (new_lang, new_a11y, now, user_id),
            )
        else:
            await self.db.execute(
                "INSERT INTO user_settings(user_id, language, accessibility, updated_at) VALUES(?,?,?,?)",
                (user_id, new_lang, new_a11y, now),
            )
        await self.db.commit()

    # --- gamification (XP, level, achievements) ------------------------

    async def get_xp(self, user_id: int) -> dict[str, Any]:
        cur = await self.db.execute(
            "SELECT xp, level, achievements, streak_days, last_active FROM user_xp WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return {"xp": 0, "level": 1, "achievements": [], "streak_days": 0, "last_active": None}
        achievements: list[str] = []
        try:
            parsed = json.loads(row[2] or "[]")
            if isinstance(parsed, list):
                achievements = [str(item) for item in parsed]
        except json.JSONDecodeError:
            achievements = []
        return {
            "xp": int(row[0]),
            "level": int(row[1]),
            "achievements": achievements,
            "streak_days": int(row[3]),
            "last_active": row[4],
        }

    async def save_xp(
        self,
        user_id: int,
        *,
        xp: int,
        level: int,
        achievements: list[str],
        streak_days: int,
        last_active: str,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO user_xp(user_id, xp, level, achievements, streak_days, last_active)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              xp = excluded.xp,
              level = excluded.level,
              achievements = excluded.achievements,
              streak_days = excluded.streak_days,
              last_active = excluded.last_active
            """,
            (user_id, xp, level, json.dumps(achievements, ensure_ascii=False), streak_days, last_active),
        )
        await self.db.commit()

    async def leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            """
            SELECT u.user_id, COALESCE(u.username, ''), x.xp, x.level
            FROM user_xp x
            LEFT JOIN users u USING(user_id)
            ORDER BY x.xp DESC LIMIT ?
            """,
            (limit,),
        )
        rows = await cur.fetchall()
        return [{"user_id": r[0], "username": r[1], "xp": int(r[2]), "level": int(r[3])} for r in rows]

    # --- teacher / class -----------------------------------------------

    async def create_class(self, teacher_id: int, name: str) -> dict[str, Any]:
        code = secrets.token_urlsafe(6)[:8].upper().replace("-", "X").replace("_", "Y")
        cur = await self.db.execute(
            """
            INSERT INTO classes(teacher_id, name, invite_code, created_at)
            VALUES(?, ?, ?, ?)
            """,
            (teacher_id, name[:80], code, _now()),
        )
        await self.db.commit()
        return {"id": int(cur.lastrowid or 0), "name": name[:80], "invite_code": code}

    async def list_classes_by_teacher(self, teacher_id: int) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT id, name, invite_code, created_at FROM classes WHERE teacher_id=? ORDER BY id DESC",
            (teacher_id,),
        )
        rows = await cur.fetchall()
        return [{"id": r[0], "name": r[1], "invite_code": r[2], "created_at": r[3]} for r in rows]

    async def class_by_code(self, code: str) -> dict[str, Any] | None:
        cur = await self.db.execute(
            "SELECT id, teacher_id, name, invite_code, created_at FROM classes WHERE invite_code=?",
            (code,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "teacher_id": row[1],
            "name": row[2],
            "invite_code": row[3],
            "created_at": row[4],
        }

    async def join_class(self, class_id: int, user_id: int, nickname: str | None = None) -> bool:
        try:
            await self.db.execute(
                """
                INSERT INTO class_members(class_id, user_id, joined_at, nickname)
                VALUES(?, ?, ?, ?)
                """,
                (class_id, user_id, _now(), nickname[:40] if nickname else None),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def class_members(self, class_id: int) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            """
            SELECT user_id, joined_at, nickname FROM class_members WHERE class_id=?
            ORDER BY joined_at ASC
            """,
            (class_id,),
        )
        rows = await cur.fetchall()
        return [{"user_id": r[0], "joined_at": r[1], "nickname": r[2]} for r in rows]

    async def class_progress(self, class_id: int) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            """
            SELECT cm.user_id, cm.nickname,
                   COALESCE(x.xp, 0), COALESCE(x.level, 1),
                   (SELECT COUNT(DISTINCT payload) FROM events e
                    WHERE e.user_id = cm.user_id AND e.name='scenario_complete'
                      AND e.payload IS NOT NULL) AS completed
            FROM class_members cm
            LEFT JOIN user_xp x ON x.user_id = cm.user_id
            WHERE cm.class_id = ?
            ORDER BY completed DESC, x.xp DESC
            """,
            (class_id,),
        )
        rows = await cur.fetchall()
        return [
            {
                "user_id": r[0],
                "nickname": r[1] or f"user_{r[0]}",
                "xp": int(r[2]),
                "level": int(r[3]),
                "completed": int(r[4]),
            }
            for r in rows
        ]

    # --- SOS contacts --------------------------------------------------

    async def set_sos_contact(
        self,
        user_id: int,
        *,
        contact_chat_id: int | None,
        contact_username: str | None,
        display_name: str | None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO sos_contacts(user_id, contact_chat_id, contact_username, display_name, created_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              contact_chat_id = excluded.contact_chat_id,
              contact_username = excluded.contact_username,
              display_name = excluded.display_name,
              created_at = excluded.created_at
            """,
            (user_id, contact_chat_id, contact_username, display_name, _now()),
        )
        await self.db.commit()

    async def get_sos_contact(self, user_id: int) -> dict[str, Any] | None:
        cur = await self.db.execute(
            "SELECT contact_chat_id, contact_username, display_name FROM sos_contacts WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "contact_chat_id": row[0],
            "contact_username": row[1],
            "display_name": row[2],
        }

    async def delete_sos_contact(self, user_id: int) -> bool:
        cur = await self.db.execute("DELETE FROM sos_contacts WHERE user_id=?", (user_id,))
        await self.db.commit()
        return (cur.rowcount or 0) > 0

    # --- A/B assignment ------------------------------------------------

    async def assign_ab_variant(self, user_id: int, experiment: str, variant: str) -> str:
        cur = await self.db.execute(
            "SELECT variant FROM ab_assignments WHERE user_id=? AND experiment=?",
            (user_id, experiment),
        )
        row = await cur.fetchone()
        if row:
            return str(row[0])
        await self.db.execute(
            """
            INSERT INTO ab_assignments(user_id, experiment, variant, assigned_at)
            VALUES(?,?,?,?)
            """,
            (user_id, experiment, variant, _now()),
        )
        await self.db.commit()
        return variant

    # --- 152-ФЗ consent (H8) -------------------------------------------

    async def has_consented(self, user_id: int, *, version: str | None = None) -> bool:
        """Return True if the user has accepted the PDN consent.

        If ``version`` is given, returns True only if their stored consent
        matches that version; this lets us re-prompt when the policy changes.
        """
        cur = await self.db.execute(
            "SELECT consent_pdn_at, consent_pdn_version FROM user_settings WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        if not row or not row[0]:
            return False
        return not (version is not None and row[1] != version)

    async def record_consent(self, user_id: int, *, version: str, details: str | None = None) -> None:
        now = _now()
        cur = await self.db.execute(
            "SELECT user_id FROM user_settings WHERE user_id=?",
            (user_id,),
        )
        if await cur.fetchone():
            await self.db.execute(
                "UPDATE user_settings SET consent_pdn_at=?, consent_pdn_version=?, updated_at=? "
                "WHERE user_id=?",
                (now, version, now, user_id),
            )
        else:
            await self.db.execute(
                "INSERT INTO user_settings(user_id, language, accessibility, updated_at, "
                "consent_pdn_at, consent_pdn_version) VALUES(?, 'ru', 0, ?, ?, ?)",
                (user_id, now, now, version),
            )
        await self.db.execute(
            "INSERT INTO consent_log(user_id, ts, action, version, details) VALUES(?,?,?,?,?)",
            (user_id, now, "accept", version, details),
        )
        await self.db.commit()

    async def revoke_consent(self, user_id: int, *, details: str | None = None) -> None:
        now = _now()
        await self.db.execute(
            "UPDATE user_settings SET consent_pdn_at=NULL, consent_pdn_version=NULL, updated_at=? "
            "WHERE user_id=?",
            (now, user_id),
        )
        await self.db.execute(
            "INSERT INTO consent_log(user_id, ts, action, version, details) VALUES(?,?,?,?,?)",
            (user_id, now, "revoke", None, details),
        )
        await self.db.commit()

    # --- 152-ФЗ /forget_me (H3) ----------------------------------------

    async def forget_user(self, user_id: int) -> dict[str, int]:
        """Hard-delete all rows for a user across every table that stores PDn.

        Returns a dict ``{table: rows_deleted}`` for audit logging.
        """
        tables = (
            "events",
            "feedback",
            "test_results",
            "aed_submissions",
            "certificates",
            "user_settings",
            "user_xp",
            "class_members",
            "sos_contacts",
            "ab_assignments",
            "consent_log",
            "alert_subscriptions",
            "users",
        )
        result: dict[str, int] = {}
        for tbl in tables:
            cur = await self.db.execute(f"DELETE FROM {tbl} WHERE user_id=?", (user_id,))
            result[tbl] = cur.rowcount or 0
        await self.db.commit()
        return result

    # --- audit log (H1) ------------------------------------------------

    async def audit(
        self,
        action: str,
        *,
        actor_id: int | None = None,
        target: str | None = None,
        details: str | None = None,
    ) -> None:
        await self.db.execute(
            "INSERT INTO audit_log(ts, actor_id, action, target, details) VALUES(?,?,?,?,?)",
            (_now(), actor_id, action, target, details),
        )
        await self.db.commit()

    async def list_audit(self, *, limit: int = 200) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT id, ts, actor_id, action, target, details FROM audit_log " "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [
            {"id": r[0], "ts": r[1], "actor_id": r[2], "action": r[3], "target": r[4], "details": r[5]}
            for r in rows
        ]

    # --- МЧС alert subscriptions (C7) ----------------------------------

    async def add_alert_subscription(self, user_id: int, region: str) -> bool:
        try:
            await self.db.execute(
                "INSERT INTO alert_subscriptions(user_id, region, created_at) VALUES(?,?,?)",
                (user_id, region.strip().lower(), _now()),
            )
            await self.db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def remove_alert_subscription(self, user_id: int, region: str | None = None) -> int:
        if region is None:
            cur = await self.db.execute("DELETE FROM alert_subscriptions WHERE user_id=?", (user_id,))
        else:
            cur = await self.db.execute(
                "DELETE FROM alert_subscriptions WHERE user_id=? AND region=?",
                (user_id, region.strip().lower()),
            )
        await self.db.commit()
        return cur.rowcount or 0

    async def list_alert_subscriptions(self, user_id: int) -> list[str]:
        cur = await self.db.execute(
            "SELECT region FROM alert_subscriptions WHERE user_id=? ORDER BY created_at",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [str(r[0]) for r in rows]

    async def subscribers_for_region(self, region: str) -> list[int]:
        cur = await self.db.execute(
            "SELECT user_id FROM alert_subscriptions WHERE region=?",
            (region.strip().lower(),),
        )
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows]

    async def alert_seen(self, guid: str) -> bool:
        cur = await self.db.execute("SELECT 1 FROM alerts_seen WHERE guid=?", (guid,))
        return await cur.fetchone() is not None

    async def mark_alert_seen(self, guid: str) -> None:
        try:
            await self.db.execute("INSERT INTO alerts_seen(guid, ts) VALUES(?,?)", (guid, _now()))
            await self.db.commit()
        except aiosqlite.IntegrityError:
            pass

    # --- /admin_export (H4) --------------------------------------------

    async def export_table(self, table: str) -> tuple[list[str], list[tuple[Any, ...]]]:
        """Return (columns, rows) for the given table. Whitelisted to known tables."""
        whitelist = {
            "users",
            "events",
            "feedback",
            "test_results",
            "aed_submissions",
            "certificates",
            "user_settings",
            "user_xp",
            "classes",
            "class_members",
            "sos_contacts",
            "ab_assignments",
            "consent_log",
            "audit_log",
            "alert_subscriptions",
        }
        if table not in whitelist:
            raise ValueError(f"unknown table: {table}")
        cur = await self.db.execute(f"SELECT * FROM {table}")
        rows = await cur.fetchall()
        cols = [d[0] for d in (cur.description or [])]
        return cols, list(rows)

    async def metrics(self) -> dict[str, Any]:
        cur = await self.db.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]

        cur = await self.db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM events WHERE ts > datetime('now','-1 day')"
        )
        dau = (await cur.fetchone())[0]

        cur = await self.db.execute("SELECT COUNT(*) FROM events WHERE name='scenario_complete'")
        completions = (await cur.fetchone())[0]

        cur = await self.db.execute("SELECT AVG(nps) FROM feedback WHERE nps IS NOT NULL")
        avg_nps = (await cur.fetchone())[0] or 0

        cur = await self.db.execute(
            """
            SELECT phase, AVG(1.0 * correct / total) FROM test_results
            GROUP BY phase
            """
        )
        rows = await cur.fetchall()
        phase_scores = {row[0]: float(row[1]) for row in rows}

        return {
            "users_total": users,
            "dau": dau,
            "scenarios_completed": completions,
            "avg_nps": float(avg_nps),
            "pre_score_avg": phase_scores.get("pre"),
            "post_score_avg": phase_scores.get("post"),
        }
