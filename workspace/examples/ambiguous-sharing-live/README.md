# URL Shortener Service

Runnable FastAPI + SQLite demo with custom aliases, ready-to-share URLs, link metadata,
redirect analytics, and on-demand QR codes.

Requires Python 3.10 or newer.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs to explore the API. Run tests from this directory with
`python -m pytest`.

For deployments behind a proxy or using a public hostname, set `SHORTENER_BASE_URL` to
the public origin, for example:

```powershell
$env:SHORTENER_BASE_URL = "https://sho.rt"
```

When unset, the service uses the incoming request host to construct shareable URLs.
Configure trusted proxy handling before relying on forwarded host headers.

## API

- `POST /shorten` accepts `url` and optional `custom_alias`; returns `code`,
  `short_url`, and `original_url`.
- `GET /{code}` returns a 307 redirect and increments the click count.
- `GET /stats/{code}` returns the original URL, creation time, and clicks.
- `GET /metadata/{code}` returns link metadata without incrementing clicks.
- `GET /qr/{code}?format=png` returns a PNG QR code; `format=svg` returns SVG.
- `GET /health` checks service availability.

URLs must use HTTP or HTTPS. Custom aliases are 3–20 characters, use letters, numbers,
hyphens, or underscores, and cannot collide with reserved routes. Duplicate aliases
return HTTP 409.

This SQLite backend is for local evaluation, not horizontal scale. QR codes are generated
on demand; apply suitable rate limits before exposing the endpoint publicly. Optional
scale-out ideas are documented in `docs/URL_SHORTENER_SCALABILITY.md`.

## Agent run

This application is the output of the live ambiguous-sharing example. The root workflow
uses the Gemini API key only for analysis and generation; this service does not need that
key to run. To reproduce the workflow, configure `LLM_PROVIDER`, `GEMINI_MODEL`, and
`GEMINI_API_KEY` in the repository-root PowerShell session, then use a fresh workspace as
shown in the repository's `docs/EXAMPLE_SCENARIOS.md`. Do not copy the key into this folder.