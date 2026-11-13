# URL Shortener Service

Runnable FastAPI + SQLite demo with short-link creation, redirects, click stats,
and optional link expiration.

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs. Run tests with `python -m pytest`.

## API

- `POST /shorten` accepts `url`, optional `custom_alias`, and optional positive
  `ttl_seconds`.
- `GET /{code}` returns a 307 redirect, increments clicks for active links,
  returns 410 for expired links, and 404 for unknown links.
- `GET /stats/{code}` returns the original URL, creation time, click count,
  and optional `expires_at`.
- `GET /health` checks service availability.

Existing SQLite databases are migrated additively; links without an expiration
remain active indefinitely.
