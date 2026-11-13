# URL Shortener Service

Runnable FastAPI + SQLite demo with short-link creation, redirects, and click stats.

Requires Python 3.10 or newer.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs. Run tests from this directory with `python -m pytest`.

## API

- `POST /shorten` with `{"url":"https://example.com"}` creates a short link.
- `GET /{code}` returns a 307 redirect and increments the click count.
- `GET /stats/{code}` returns the original URL, creation time, and clicks.
- `GET /health` checks service availability.

This SQLite backend is for local evaluation. Optional future scale-out notes in `docs/URL_SHORTENER_SCALABILITY.md` describe possible evolution, not a requirement for running this demo.