import io
import os
import re
import secrets
import string
import segno
from urllib.parse import urlparse
from app.storage import get_stats, get_url_and_increment, get_url_metadata, save_url

ALPHABET = string.ascii_letters + string.digits
ALIAS_MIN_LENGTH = 3
ALIAS_MAX_LENGTH = 20
ALIAS_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
ALLOWED_URL_SCHEMES = frozenset({'http', 'https'})
DEFAULT_BASE_URL = 'http://localhost:8000'
RESERVED_ALIASES = frozenset({
    'health',
    'shorten',
    'stats',
    'qr',
    'metadata',
    'meta',
    'links',
    'info',
    'api',
    'docs',
    'redoc',
    'openapi.json',
    'favicon.ico',
    'robots.txt',
})

class InvalidInputError(ValueError):
    pass


class AliasConflictError(ValueError):
    pass


def generate_code(length: int = 6) -> str:
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))


def validate_target_url(url: str) -> str:
    if not isinstance(url, str):
        raise InvalidInputError('URL must be a string.')
    cleaned = url.strip()
    if not cleaned:
        raise InvalidInputError('URL must not be empty.')
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        raise InvalidInputError('URL contains invalid control characters.')
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        raise InvalidInputError('URL scheme must be http or https.')
    if not parsed.netloc or not parsed.hostname:
        raise InvalidInputError('URL must include a valid host.')
    return cleaned


def validate_custom_alias(alias: str) -> str:
    if not isinstance(alias, str):
        raise InvalidInputError('Custom alias must be a string.')
    if not (ALIAS_MIN_LENGTH <= len(alias) <= ALIAS_MAX_LENGTH):
        raise InvalidInputError(
            f'Custom alias must be between {ALIAS_MIN_LENGTH} and {ALIAS_MAX_LENGTH} characters.'
        )
    if not ALIAS_PATTERN.fullmatch(alias):
        raise InvalidInputError(
            'Custom alias may only contain letters, numbers, hyphens, and underscores.'
        )
    if alias.lower() in RESERVED_ALIASES:
        raise InvalidInputError('Custom alias uses a reserved route name.')
    return alias


def get_base_url(fallback_base_url: str | None = None) -> str:
    configured = (os.getenv('SHORTENER_BASE_URL') or os.getenv('BASE_URL') or '').strip()
    if configured:
        return configured.rstrip('/')
    if fallback_base_url and fallback_base_url.strip():
        return fallback_base_url.strip().rstrip('/')
    return DEFAULT_BASE_URL


def format_shareable_url(code: str, base_url: str | None = None) -> str:
    clean_code = code.lstrip('/')
    resolved_base = get_base_url(base_url)
    return f'{resolved_base}/{clean_code}'


def create_short_url(original_url: str, custom_alias: str | None = None) -> str:
    validated_url = validate_target_url(original_url)
    if custom_alias is not None:
        validated_alias = validate_custom_alias(custom_alias)
        if not save_url(validated_alias, validated_url):
            raise AliasConflictError('Custom alias already exists.')
        return validated_alias
    for _ in range(5):
        code = generate_code()
        if code.lower() in RESERVED_ALIASES:
            continue
        if save_url(code, validated_url):
            return code
    raise RuntimeError('Failed to generate unique short code.')


def create_short_link(
    original_url: str,
    custom_alias: str | None = None,
    base_url: str | None = None,
) -> dict:
    validated_url = validate_target_url(original_url)
    code = create_short_url(validated_url, custom_alias)
    return {
        'code': code,
        'short_url': format_shareable_url(code, base_url),
        'original_url': validated_url,
    }


def resolve_short_url(code: str) -> str | None:
    if not code:
        return None
    return get_url_and_increment(code)


def fetch_url_stats(code: str) -> dict | None:
    return get_stats(code)


def get_link_metadata(code: str, base_url: str | None = None) -> dict | None:
    if not code:
        return None
    metadata = get_url_metadata(code)
    if not metadata:
        return None
    return {
        'code': metadata['code'],
        'original_url': metadata['original_url'],
        'short_url': format_shareable_url(metadata['code'], base_url),
        'created_at': metadata['created_at'],
        'clicks': metadata['clicks'],
    }


def render_qr_bytes(data: str, image_format: str = 'png') -> bytes:
    fmt = image_format.lower().strip()
    if fmt not in {'png', 'svg'}:
        raise InvalidInputError("Unsupported QR code format. Use 'png' or 'svg'.")
    buf = io.BytesIO()
    qr = segno.make(data, error='m')
    if fmt == 'svg':
        qr.save(buf, kind='svg', xmldecl=False, scale=5)
    else:
        qr.save(buf, kind='png', scale=5, border=2)
    return buf.getvalue()


def generate_qr_code(
    code: str,
    base_url: str | None = None,
    image_format: str = 'png',
) -> tuple[bytes, str] | None:
    fmt = image_format.lower().strip()
    if fmt not in {'png', 'svg'}:
        raise InvalidInputError("Unsupported QR code format. Use 'png' or 'svg'.")
    metadata = get_link_metadata(code, base_url=base_url)
    if not metadata:
        return None
    qr_bytes = render_qr_bytes(metadata['short_url'], image_format=fmt)
    media_type = 'image/svg+xml' if fmt == 'svg' else 'image/png'
    return qr_bytes, media_type
