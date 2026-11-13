from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from app.service import (
    create_short_url,
    fetch_url_stats,
    resolve_short_url_state,
)
from app.storage import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Agent-Generated URL Shortener",
    version="1.0.0",
    lifespan=lifespan,
)

class ShortenRequest(BaseModel):
    url: HttpUrl
    custom_alias: str | None = Field(
        default=None, min_length=3, max_length=20, pattern="^[a-zA-Z0-9_-]+$"
    )
    ttl_seconds: int | None = Field(default=None, gt=0)

class ShortenResponse(BaseModel):
    code: str
    short_url: str
    original_url: str

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.post("/shorten", response_model=ShortenResponse, status_code=201)
def shorten_url(payload: ShortenRequest, request: Request) -> ShortenResponse:
    try:
        code = create_short_url(
            str(payload.url), payload.custom_alias, payload.ttl_seconds
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    base = str(request.base_url).rstrip("/")
    return ShortenResponse(
        code=code,
        short_url=f"{base}/{code}",
        original_url=str(payload.url),
    )

@app.get("/stats/{code}")
def url_stats(code: str) -> dict:
    stats = fetch_url_stats(code)
    if not stats:
        raise HTTPException(status_code=404, detail="Short URL not found")
    return stats

@app.get("/{code}")
def redirect_url(code: str) -> RedirectResponse:
    original_url, expired = resolve_short_url_state(code)
    if expired:
        raise HTTPException(status_code=410, detail="Short URL has expired")
    if not original_url:
        raise HTTPException(status_code=404, detail="Short URL not found")
    return RedirectResponse(url=original_url, status_code=307)
