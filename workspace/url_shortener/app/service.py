import secrets
import string
from app.storage import get_stats, get_url_and_increment, save_url

ALPHABET = string.ascii_letters + string.digits

def generate_code(length: int = 6) -> str:
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))

def create_short_url(original_url: str, custom_alias: str | None = None) -> str:
    if custom_alias:
        if not save_url(custom_alias, original_url):
            raise ValueError('Custom alias already exists.')
        return custom_alias
    for _ in range(5):
        code = generate_code()
        if save_url(code, original_url):
            return code
    raise RuntimeError('Failed to generate unique short code.')

def resolve_short_url(code: str) -> str | None:
    return get_url_and_increment(code)

def fetch_url_stats(code: str) -> dict | None:
    return get_stats(code)
