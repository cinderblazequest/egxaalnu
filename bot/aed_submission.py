"""Краудсорс точек АНД через бот: /add_aed."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiosqlite

log = logging.getLogger("spas.aed_submission")


SCHEMA = """
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
"""


@dataclass(frozen=True)
class AedSubmission:
    id: int
    user_id: int
    ts: str
    city: str | None
    name: str | None
    note: str | None
    lat: float
    lon: float
    photo_file_id: str | None
    status: str


VALID_STATUSES = ("pending", "approved", "rejected")


async def ensure_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript(SCHEMA)
    await conn.commit()


async def insert_submission(
    conn: aiosqlite.Connection,
    *,
    user_id: int,
    ts: str,
    city: str | None,
    name: str | None,
    note: str | None,
    lat: float,
    lon: float,
    photo_file_id: str | None,
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO aed_submissions(user_id, ts, city, name, note, lat, lon, photo_file_id, status)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (user_id, ts, city, name, note, lat, lon, photo_file_id),
    )
    await conn.commit()
    return int(cur.lastrowid or 0)


async def list_pending(conn: aiosqlite.Connection, limit: int = 20) -> list[AedSubmission]:
    cur = await conn.execute(
        """
        SELECT id, user_id, ts, city, name, note, lat, lon, photo_file_id, status
        FROM aed_submissions
        WHERE status = 'pending'
        ORDER BY ts ASC
        LIMIT ?
        """,
        (limit,),
    )
    rows = await cur.fetchall()
    return [
        AedSubmission(
            id=row[0],
            user_id=row[1],
            ts=row[2],
            city=row[3],
            name=row[4],
            note=row[5],
            lat=row[6],
            lon=row[7],
            photo_file_id=row[8],
            status=row[9],
        )
        for row in rows
    ]


async def update_status(conn: aiosqlite.Connection, submission_id: int, status: str) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    cur = await conn.execute("UPDATE aed_submissions SET status = ? WHERE id = ?", (status, submission_id))
    await conn.commit()
    return (cur.rowcount or 0) > 0


async def count_by_status(conn: aiosqlite.Connection) -> dict[str, int]:
    cur = await conn.execute("SELECT status, COUNT(*) FROM aed_submissions GROUP BY status")
    rows = await cur.fetchall()
    return {row[0]: int(row[1]) for row in rows}
