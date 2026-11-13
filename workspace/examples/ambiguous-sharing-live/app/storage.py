import os
import sqlite3
from datetime import datetime, timezone


def get_db_path() -> str:
    return os.getenv('SHORTENER_DB_PATH', 'url_shortener.db')


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(get_db_path(), timeout=30.0)


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                'CREATE TABLE IF NOT EXISTS urls ('
                'code TEXT PRIMARY KEY, '
                'original_url TEXT NOT NULL, '
                'created_at TEXT NOT NULL, '
                'clicks INTEGER NOT NULL DEFAULT 0)'
            )
    finally:
        conn.close()


def code_exists(code: str) -> bool:
    if not code:
        return False
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            'SELECT 1 FROM urls WHERE code = ? LIMIT 1',
            (code,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def save_url(code: str, original_url: str) -> bool:
    if not code or not original_url:
        return False
    init_db()
    conn = _connect()
    try:
        with conn:
            conn.execute(
                'INSERT INTO urls (code, original_url, created_at, clicks) VALUES (?, ?, ?, 0)',
                (code, original_url, datetime.now(timezone.utc).isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_url_and_increment(code: str) -> str | None:
    if not code:
        return None
    init_db()
    conn = _connect()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                'SELECT original_url FROM urls WHERE code = ?',
                (code,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                'UPDATE urls SET clicks = clicks + 1 WHERE code = ?',
                (code,),
            )
            return row[0]
    finally:
        conn.close()


def get_url_metadata(code: str) -> dict | None:
    if not code:
        return None
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            'SELECT code, original_url, created_at, clicks FROM urls WHERE code = ?',
            (code,),
        ).fetchone()
        if not row:
            return None
        return {
            'code': row[0],
            'original_url': row[1],
            'created_at': row[2],
            'clicks': row[3],
        }
    finally:
        conn.close()


def get_stats(code: str) -> dict | None:
    return get_url_metadata(code)
