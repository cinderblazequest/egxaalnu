"""Тесты для tools.backup_db: snapshot, шифрование и сборка ключа."""

from __future__ import annotations

import datetime as dt
import secrets
import sqlite3
from pathlib import Path

import pytest

from tools import backup_db


def test_make_snapshot_round_trips(tmp_path: Path) -> None:
    src = tmp_path / "live.db"
    dst = tmp_path / "snap.db"
    with sqlite3.connect(str(src)) as conn:
        conn.execute("CREATE TABLE x (id INTEGER PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO x(val) VALUES (?), (?)", ("a", "b"))
    backup_db.make_snapshot(src, dst)
    assert dst.exists()
    with sqlite3.connect(str(dst)) as conn:
        rows = list(conn.execute("SELECT val FROM x ORDER BY id"))
    assert rows == [("a",), ("b",)]


def test_encrypt_decrypt_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    plain = tmp_path / "plain.bin"
    enc = tmp_path / "enc.bin"
    plain.write_bytes(b"hello world" * 100)
    key_hex = secrets.token_hex(32)
    backup_db.encrypt_file(plain, enc, key_hex)
    blob = enc.read_bytes()
    # Контейнер: версия (1B) + nonce (12B) + ciphertext+tag.
    assert blob[:1] == backup_db.VERSION_TAG
    assert len(blob) > len(plain.read_bytes())
    out = tmp_path / "decoded.bin"
    backup_db.decrypt_file(enc, out, key_hex)
    assert out.read_bytes() == plain.read_bytes()


def test_encrypt_rejects_short_key(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    src = tmp_path / "x.bin"
    src.write_bytes(b"\x00")
    with pytest.raises(ValueError):
        backup_db.encrypt_file(src, tmp_path / "y.bin", "00" * 8)


def test_build_backup_key_includes_prefix() -> None:
    when = dt.datetime(2026, 5, 31, 12, 30, 45)
    key = backup_db.build_backup_key("spas-backups", when=when)
    assert key == "spas-backups/spas-2026-05-31_12-30-45.db.enc"
    key2 = backup_db.build_backup_key("nested/dir/", when=when)
    assert key2 == "nested/dir/spas-2026-05-31_12-30-45.db.enc"


def test_run_dry_run_creates_local_file(tmp_path: Path) -> None:
    """``run(upload=False)`` должен вернуть локальный snapshot без обращения к S3."""
    src = tmp_path / "live.db"
    with sqlite3.connect(str(src)) as conn:
        conn.execute("CREATE TABLE t (a INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
    out = backup_db.run(db_path=src, upload=False, key_hex=None)
    assert out.exists()
    assert out.stat().st_size > 0
