from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from app.service import (
    AliasConflictError,
    InvalidInputError,
    create_short_link,
    fetch_url_stats,
    generate_qr_code,
    get_link_metadata,
    resolve_short_url,
)
from app.storage import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title='Agent-Generated URL Shortener', version='1.0.0', lifespan=lifespan)


class ShortenRequest(BaseModel):
    url: str
    custom_alias: str | None = None


class ShortenResponse(BaseModel):
    code: str
    short_url: str
    original_url: str


class LinkMetadataResponse(BaseModel):
    code: str
    original_url: str
    short_url: str
    created_at: str
    clicks: int


@app.get('/health')
def health() -> dict:
    return {'status': 'ok'}


@app.post('/shorten', response_model=ShortenResponse, status_code=201)
def shorten_url(payload: ShortenRequest, request: Request) -> ShortenResponse:
    base = str(request.base_url).rstrip('/')
    try:
        result = create_short_link(
            payload.url,
            custom_alias=payload.custom_alias,
            base_url=base,
        )
    except InvalidInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AliasConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ShortenResponse(**result)


@app.get('/stats/{code}')
def url_stats(code: str) -> dict:
    stats = fetch_url_stats(code)
    if not stats:
        raise HTTPException(status_code=404, detail='Short URL not found')
    return stats


@app.get('/metadata/{code}', response_model=LinkMetadataResponse)
def link_metadata(code: str, request: Request) -> LinkMetadataResponse:
    base = str(request.base_url).rstrip('/')
    metadata = get_link_metadata(code, base_url=base)
    if not metadata:
        raise HTTPException(status_code=404, detail='Short URL not found')
    return LinkMetadataResponse(**metadata)


@app.get('/qr/{code}')
def link_qr_code(code: str, request: Request, format: str = 'png') -> Response:
    base = str(request.base_url).rstrip('/')
    try:
        qr_result = generate_qr_code(code, base_url=base, image_format=format)
    except InvalidInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not qr_result:
        raise HTTPException(status_code=404, detail='Short URL not found')
    qr_bytes, media_type = qr_result
    return Response(content=qr_bytes, media_type=media_type)


@app.get('/{code}')
def redirect_url(code: str) -> RedirectResponse:
    original_url = resolve_short_url(code)
    if not original_url:
        raise HTTPException(status_code=404, detail='Short URL not found')
    return RedirectResponse(url=original_url, status_code=307)
