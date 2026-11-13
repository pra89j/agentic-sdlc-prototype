import os
import sqlite3
from datetime import datetime, timezone

def get_db_path() -> str:
    return os.getenv("SHORTENER_DB_PATH", "url_shortener.db")

def init_db() -> None:
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS urls ("
            "code TEXT PRIMARY KEY, original_url TEXT NOT NULL, "
            "created_at TEXT NOT NULL, clicks INTEGER NOT NULL DEFAULT 0, "
            "expires_at TEXT)"
        )
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(urls)").fetchall()
        }
        if "expires_at" not in columns:
            conn.execute("ALTER TABLE urls ADD COLUMN expires_at TEXT")
        conn.commit()

def save_url(
    code: str, original_url: str, expires_at: str | None = None
) -> bool:
    init_db()
    try:
        with sqlite3.connect(get_db_path()) as conn:
            conn.execute(
                "INSERT INTO urls "
                "(code, original_url, created_at, clicks, expires_at) "
                "VALUES (?, ?, ?, 0, ?)",
                (
                    code,
                    original_url,
                    datetime.now(timezone.utc).isoformat(),
                    expires_at,
                ),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_url_state_and_increment(
    code: str, now: datetime | None = None
) -> tuple[str | None, bool]:
    init_db()
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)

    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute(
            "SELECT original_url, expires_at FROM urls WHERE code = ?", (code,)
        ).fetchone()
        if not row:
            return None, False

        if row[1]:
            expires_at = datetime.fromisoformat(row[1])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at.astimezone(timezone.utc) <= current_time:
                return None, True

        conn.execute("UPDATE urls SET clicks = clicks + 1 WHERE code = ?", (code,))
        conn.commit()
        return row[0], False

def get_url_and_increment(code: str) -> str | None:
    url, _ = get_url_state_and_increment(code)
    return url

def get_stats(code: str) -> dict | None:
    init_db()
    with sqlite3.connect(get_db_path()) as conn:
        row = conn.execute(
            "SELECT code, original_url, created_at, clicks, expires_at "
            "FROM urls WHERE code = ?",
            (code,),
        ).fetchone()
        if not row:
            return None
        return {
            "code": row[0],
            "original_url": row[1],
            "created_at": row[2],
            "clicks": row[3],
            "expires_at": row[4],
        }
