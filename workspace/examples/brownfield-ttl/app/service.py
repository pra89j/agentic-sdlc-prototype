import secrets
import string
from datetime import datetime, timedelta, timezone
from app.storage import (
    get_stats,
    get_url_state_and_increment,
    save_url,
)

ALPHABET = string.ascii_letters + string.digits

def generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))

def create_short_url(
    original_url: str,
    custom_alias: str | None = None,
    ttl_seconds: int | None = None,
) -> str:
    if ttl_seconds is not None and ttl_seconds <= 0:
        raise ValueError("TTL must be a positive number of seconds.")
    expires_at = None
    if ttl_seconds is not None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).isoformat()

    if custom_alias:
        if not save_url(custom_alias, original_url, expires_at):
            raise ValueError("Custom alias already exists.")
        return custom_alias
    for _ in range(5):
        code = generate_code()
        if save_url(code, original_url, expires_at):
            return code
    raise RuntimeError("Failed to generate unique short code.")

def resolve_short_url_state(code: str) -> tuple[str | None, bool]:
    return get_url_state_and_increment(code)

def resolve_short_url(code: str) -> str | None:
    url, _ = resolve_short_url_state(code)
    return url

def fetch_url_stats(code: str) -> dict | None:
    return get_stats(code)
