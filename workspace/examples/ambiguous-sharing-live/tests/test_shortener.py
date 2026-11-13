from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, service, storage
from app.main import app

@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "test_urls.db"
    for env_var in ("SHORTENER_DB_PATH", "DB_PATH", "DATABASE_PATH", "SQLITE_DB_PATH"):
        monkeypatch.setenv(env_var, str(db_file))
    for env_var in ("SHORTENER_BASE_URL", "BASE_URL", "APP_BASE_URL", "PUBLIC_BASE_URL"):
        monkeypatch.delenv(env_var, raising=False)
    for attr in ("DB_PATH", "DATABASE_PATH", "DEFAULT_DB_PATH", "SQLITE_DB_PATH"):
        if hasattr(storage, attr):
            current = getattr(storage, attr)
            monkeypatch.setattr(storage, attr, db_file if isinstance(current, Path) else str(db_file))
    if hasattr(storage, "init_db"):
        storage.init_db()
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_shorten_redirect_and_stats_backward_compatibility(client: TestClient):
    target_url = "https://example.com/docs?ref=home#top"
    create_res = client.post("/shorten", json={"url": target_url})
    assert create_res.status_code == 201

    payload = create_res.json()
    code = payload["code"]
    assert len(code) >= 3
    assert payload["original_url"] == target_url
    assert payload["short_url"] == f"http://testserver/{code}"

    stats_before = client.get(f"/stats/{code}")
    assert stats_before.status_code == 200
    assert stats_before.json()["code"] == code
    assert stats_before.json()["original_url"] == target_url
    assert stats_before.json()["clicks"] == 0

    redirect_res = client.get(f"/{code}", follow_redirects=False)
    assert redirect_res.status_code == 307
    assert redirect_res.headers["location"] == target_url

    stats_after = client.get(f"/stats/{code}")
    assert stats_after.status_code == 200
    assert stats_after.json()["clicks"] == 1


def test_missing_code_returns_404(client: TestClient):
    assert client.get("/doesnotexist").status_code == 404
    assert client.get("/stats/doesnotexist").status_code == 404
    assert client.get("/metadata/doesnotexist").status_code == 404
    assert client.get("/qr/doesnotexist").status_code == 404


@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        "   ",
        "not-a-url",
        "ftp://example.com/file",
        "javascript:alert(1)",
        "https://",
        "https://example.com/bad\npath",
    ],
)
def test_invalid_target_url_returns_400(client: TestClient, bad_url: str):
    res = client.post("/shorten", json={"url": bad_url})
    assert res.status_code == 400


@pytest.mark.parametrize(
    "alias",
    [
        "abc",
        "launch-2025",
        "Team_Docs_1",
        "a" * 20,
    ],
)
def test_valid_custom_alias_creation_and_redirect(client: TestClient, alias: str):
    target_url = "https://example.com/product"
    create_res = client.post(
        "/shorten",
        json={"url": target_url, "custom_alias": alias},
    )
    assert create_res.status_code == 201

    body = create_res.json()
    assert body["code"] == alias
    assert body["original_url"] == target_url
    assert body["short_url"] == f"http://testserver/{alias}"

    redirect_res = client.get(f"/{alias}", follow_redirects=False)
    assert redirect_res.status_code == 307
    assert redirect_res.headers["location"] == target_url


@pytest.mark.parametrize(
    "bad_alias",
    [
        "",
        "ab",
        "a" * 21,
        "bad alias",
        "bad/alias",
        "bad?alias",
        "bad.alias",
        "emoji!@#",
    ],
)
def test_invalid_custom_alias_returns_400(client: TestClient, bad_alias: str):
    res = client.post(
        "/shorten",
        json={"url": "https://example.com", "custom_alias": bad_alias},
    )
    assert res.status_code == 400


@pytest.mark.parametrize(
    "reserved_alias",
    [
        "health",
        "HEALTH",
        "shorten",
        "stats",
        "Stats",
        "qr",
        "metadata",
        "docs",
        "openapi.json",
    ],
)
def test_reserved_route_alias_returns_400(client: TestClient, reserved_alias: str):
    res = client.post(
        "/shorten",
        json={"url": "https://example.com", "custom_alias": reserved_alias},
    )
    assert res.status_code == 400


def test_duplicate_custom_alias_returns_409(client: TestClient):
    first = client.post(
        "/shorten",
        json={"url": "https://example.com/one", "custom_alias": "promo-2025"},
    )
    assert first.status_code == 201

    duplicate = client.post(
        "/shorten",
        json={"url": "https://example.com/two", "custom_alias": "promo-2025"},
    )
    assert duplicate.status_code == 409

    redirect_res = client.get("/promo-2025", follow_redirects=False)
    assert redirect_res.status_code == 307
    assert redirect_res.headers["location"] == "https://example.com/one"


def test_custom_alias_conflicts_with_existing_auto_generated_code(client: TestClient):
    auto_res = client.post("/shorten", json={"url": "https://example.com/auto"})
    assert auto_res.status_code == 201
    generated_code = auto_res.json()["code"]

    conflict_res = client.post(
        "/shorten",
        json={"url": "https://example.com/override", "custom_alias": generated_code},
    )
    assert conflict_res.status_code == 409


def test_configured_base_url_for_shareable_links(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    for env_var in ("SHORTENER_BASE_URL", "BASE_URL", "APP_BASE_URL", "PUBLIC_BASE_URL"):
        monkeypatch.setenv(env_var, "https://sho.rt")
    for module in (main, service):
        for attr in ("BASE_URL", "SHORTENER_BASE_URL"):
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, "https://sho.rt")

    create_res = client.post(
        "/shorten",
        json={"url": "https://example.com/share", "custom_alias": "share-me"},
    )
    assert create_res.status_code == 201
    assert create_res.json()["short_url"] == "https://sho.rt/share-me"

    meta_res = client.get("/metadata/share-me")
    assert meta_res.status_code == 200
    assert meta_res.json()["short_url"] == "https://sho.rt/share-me"


def test_metadata_retrieval_does_not_increment_clicks(client: TestClient):
    create_res = client.post(
        "/shorten",
        json={"url": "https://example.com/guide", "custom_alias": "inspect-me"},
    )
    assert create_res.status_code == 201

    meta_res = client.get("/metadata/inspect-me")
    assert meta_res.status_code == 200
    meta_payload = meta_res.json()
    assert meta_payload["code"] == "inspect-me"
    assert meta_payload["original_url"] == "https://example.com/guide"
    assert meta_payload["short_url"] == "http://testserver/inspect-me"

    stats_before = client.get("/stats/inspect-me")
    assert stats_before.status_code == 200
    assert stats_before.json()["clicks"] == 0

    redirect_res = client.get("/inspect-me", follow_redirects=False)
    assert redirect_res.status_code == 307

    stats_after = client.get("/stats/inspect-me")
    assert stats_after.status_code == 200
    assert stats_after.json()["clicks"] == 1


def test_qr_code_generation_png_and_svg(
    client: TestClient
):
    create_res = client.post(
        "/shorten",
        json={"url": "https://example.com/event", "custom_alias": "event-2025"},
    )
    assert create_res.status_code == 201

    png_res = client.get("/qr/event-2025")
    assert png_res.status_code == 200
    assert png_res.headers["content-type"].startswith("image/png")
    assert png_res.content.startswith(b"\x89PNG\r\n\x1a\n")

    svg_res = client.get("/qr/event-2025?format=svg")
    assert svg_res.status_code == 200
    assert svg_res.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in svg_res.content


def test_qr_code_invalid_format_returns_400(client: TestClient):
    create_res = client.post(
        "/shorten",
        json={"url": "https://example.com/qr", "custom_alias": "qr-bad-fmt"},
    )
    assert create_res.status_code == 201

    bad_res = client.get("/qr/qr-bad-fmt?format=bmp")
    assert bad_res.status_code == 400
