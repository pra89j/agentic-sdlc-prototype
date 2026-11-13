import os
import sqlite3
from datetime import datetime, timezone

def get_db_path() -> str:
    return os.getenv('SHORTENER_DB_PATH', 'url_shortener.db')

def init_db() -> None:
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS urls (code TEXT PRIMARY KEY, original_url TEXT NOT NULL, created_at TEXT NOT NULL, clicks INTEGER NOT NULL DEFAULT 0)')
        conn.commit()

def save_url(code: str, original_url: str) -> bool:
    init_db()
    try:
        with sqlite3.connect(get_db_path()) as conn:
            conn.execute('INSERT INTO urls (code, original_url, created_at, clicks) VALUES (?, ?, ?, 0)', (code, original_url, datetime.now(timezone.utc).isoformat()))
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_url_and_increment(code: str) -> str | None:
    init_db()
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute('SELECT original_url FROM urls WHERE code = ?', (code,)).fetchone()
        if not row:
            return None
        conn.execute('UPDATE urls SET clicks = clicks + 1 WHERE code = ?', (code,))
        conn.commit()
        return row[0]

def get_stats(code: str) -> dict | None:
    init_db()
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute('SELECT code, original_url, created_at, clicks FROM urls WHERE code = ?', (code,)).fetchone()
        if not row:
            return None
        return {'code': row[0], 'original_url': row[1], 'created_at': row[2], 'clicks': row[3]}
