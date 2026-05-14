"""Зашифрованный backup SQLite-БД в S3-совместимое хранилище.

Использует:
- ``sqlite3.Connection.backup`` — атомарный snapshot БД, безопасно к live-боту;
- ``cryptography.AESGCM`` — аутентифицированное шифрование;
- любого S3-совместимого провайдера (Selectel, Yandex Object Storage, MinIO,
  AWS S3) через ``boto3``.

Запуск (из cron / Fly cron / systemd timer):

    python -m tools.backup_db --upload

Запуск без выгрузки (smoke test):

    python -m tools.backup_db --dry-run

Конфигурация — через ``.env`` (см. ``.env.example``):

    DB_PATH                   путь к live-БД (по умолчанию spas.db)
    BACKUP_S3_ENDPOINT        URL S3 endpoint (для Selectel: https://s3.ru-1.storage.selcloud.ru)
    BACKUP_S3_BUCKET          имя бакета
    BACKUP_S3_PREFIX          префикс ключа (по умолчанию ``spas-backups/``)
    BACKUP_S3_ACCESS_KEY      access key
    BACKUP_S3_SECRET_KEY      secret key
    BACKUP_ENCRYPTION_KEY     32 байта в hex (64 hex-символа)

Формат файла бэкапа: ``spas-YYYY-MM-DD_HH-MM-SS.db.enc``.
Структура: ``[1 байт версии][12 байт nonce][N байт AES-GCM(ciphertext+tag)]``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sqlite3
import tempfile
from pathlib import Path

log = logging.getLogger("spas.backup")

VERSION_TAG = b"\x01"  # версия формата контейнера


def make_snapshot(src: Path, dst: Path) -> None:
    """Сделать atomic snapshot SQLite БД через ``sqlite3.Connection.backup``."""
    if not src.exists():
        raise FileNotFoundError(src)
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def encrypt_file(src: Path, dst: Path, key_hex: str) -> None:
    """Зашифровать файл алгоритмом AES-256-GCM.

    ``key_hex`` — 64 hex-символа (= 32 байта). Контейнер: 1 байт версии,
    12 байт nonce, далее ciphertext+tag.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        raise ValueError("BACKUP_ENCRYPTION_KEY: ожидается 32 байта (64 hex-символа)")
    aes = AESGCM(key)
    nonce = os.urandom(12)
    plaintext = src.read_bytes()
    ciphertext = aes.encrypt(nonce, plaintext, None)
    dst.write_bytes(VERSION_TAG + nonce + ciphertext)


def decrypt_file(src: Path, dst: Path, key_hex: str) -> None:
    """Расшифровать backup. Используется для verify / восстановления."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = src.read_bytes()
    if len(blob) < 13 or blob[:1] != VERSION_TAG:
        raise ValueError("Неожиданный формат backup-файла")
    nonce, ciphertext = blob[1:13], blob[13:]
    aes = AESGCM(bytes.fromhex(key_hex))
    plaintext = aes.decrypt(nonce, ciphertext, None)
    dst.write_bytes(plaintext)


def _s3_client(endpoint: str, access_key: str, secret_key: str):  # type: ignore[no-untyped-def]
    """Создать boto3-клиент S3. Импорт boto3 локальный — чтобы не тащить SDK при простом dry-run."""
    import boto3  # type: ignore[import-untyped]

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def upload_to_s3(local_path: Path, key: str) -> None:
    """Загрузить локальный файл в S3-совместимое хранилище.

    Все параметры читаются из переменных окружения. Падает с осмысленной
    ошибкой, если что-то не задано.
    """
    endpoint = os.getenv("BACKUP_S3_ENDPOINT")
    bucket = os.getenv("BACKUP_S3_BUCKET")
    access_key = os.getenv("BACKUP_S3_ACCESS_KEY")
    secret_key = os.getenv("BACKUP_S3_SECRET_KEY")
    if not (endpoint and bucket and access_key and secret_key):
        raise RuntimeError("Для upload требуются BACKUP_S3_ENDPOINT/BUCKET/ACCESS_KEY/SECRET_KEY")
    client = _s3_client(endpoint, access_key, secret_key)
    client.upload_file(str(local_path), bucket, key)
    log.info("Загружен backup: s3://%s/%s (%d байт)", bucket, key, local_path.stat().st_size)


def build_backup_key(prefix: str, when: dt.datetime | None = None) -> str:
    """Имя ключа в S3: ``{prefix}spas-YYYY-MM-DD_HH-MM-SS.db.enc``."""
    now = (when or dt.datetime.utcnow()).strftime("%Y-%m-%d_%H-%M-%S")
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"
    return f"{prefix}spas-{now}.db.enc"


def run(*, db_path: Path, upload: bool, key_hex: str | None) -> Path:
    """Сделать snapshot, опционально зашифровать и выгрузить.

    Возвращает локальный путь к финальному файлу (который можно удалить
    после выгрузки).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        snapshot = tmp / "snapshot.db"
        make_snapshot(db_path, snapshot)
        if key_hex:
            final = tmp / "snapshot.db.enc"
            encrypt_file(snapshot, final, key_hex)
        else:
            final = snapshot
        if upload:
            prefix = os.getenv("BACKUP_S3_PREFIX", "spas-backups/")
            key = build_backup_key(prefix)
            upload_to_s3(final, key)
            return Path(key)
        # dry-run: переложить в /tmp на чтение, чтобы можно было проверить.
        out = Path(tempfile.gettempdir()) / final.name
        out.write_bytes(final.read_bytes())
        return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backup СПАС SQLite в S3.")
    parser.add_argument("--db-path", default=os.getenv("DB_PATH", "spas.db"))
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Загрузить в S3 (иначе dry-run в /tmp).",
    )
    parser.add_argument(
        "--no-encrypt",
        action="store_true",
        help="Не шифровать (для тестов/локального бэкапа).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    key_hex = None if args.no_encrypt else os.getenv("BACKUP_ENCRYPTION_KEY", "").strip() or None
    if not key_hex and not args.no_encrypt:
        log.warning(
            "BACKUP_ENCRYPTION_KEY не задан — backup будет НЕ зашифрован. "
            'Сгенерируй ключ: python -c "import secrets;print(secrets.token_hex(32))"'
        )

    out = run(db_path=Path(args.db_path), upload=args.upload, key_hex=key_hex)
    log.info("Готово: %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
