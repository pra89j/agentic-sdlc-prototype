import sqlite3

import pytest
from app import service
from app.main import app
from app.storage import get_stats, init_db, save_url
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_urls.db"
    monkeypatch.setenv("SHORTENER_DB_PATH", str(db_file))

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_shorten_redirect_and_analytics():
    create_response = client.post(
        "/shorten", json={"url": "https://example.com"}
    )
    assert create_response.status_code == 201
    code = create_response.json()["code"]
    redirect_response = client.get(f"/{code}", follow_redirects=False)
    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == "https://example.com/"
    stats_response = client.get(f"/stats/{code}")
    assert stats_response.status_code == 200
    assert stats_response.json()["original_url"] == "https://example.com/"
    assert stats_response.json()["created_at"]
    assert stats_response.json()["clicks"] == 1

def test_create_short_url_retries_code_collisions(monkeypatch):
    generated_codes = iter(["duplicate", "available"])
    saved_codes = []
    monkeypatch.setattr(
        service, "generate_code", lambda: next(generated_codes)
    )
    monkeypatch.setattr(
        service,
        "save_url",
        lambda code, url, expires_at=None: saved_codes.append(code)
        or code == "available",
    )
    assert service.create_short_url("https://example.com/") == "available"
    assert saved_codes == ["duplicate", "available"]

def test_custom_alias_conflict():
    first = client.post(
        "/shorten",
        json={"url": "https://example.com", "custom_alias": "my-link"},
    )
    assert first.status_code == 201
    second = client.post(
        "/shorten",
        json={"url": "https://example.com", "custom_alias": "my-link"},
    )
    assert second.status_code == 409

def test_invalid_url_rejected():
    response = client.post("/shorten", json={"url": "not-a-valid-url"})
    assert response.status_code == 422

def test_ttl_is_optional_and_persisted():
    response = client.post(
        "/shorten",
        json={"url": "https://example.com", "ttl_seconds": 3600},
    )
    assert response.status_code == 201
    stats = client.get(f"/stats/{response.json()['code']}").json()
    assert stats["expires_at"]

def test_non_positive_ttl_is_rejected():
    response = client.post(
        "/shorten",
        json={"url": "https://example.com", "ttl_seconds": 0},
    )
    assert response.status_code == 422

def test_expired_link_returns_410_without_incrementing_clicks():
    assert save_url(
        "expired", "https://example.com/", "2000-01-01T00:00:00+00:00"
    )
    response = client.get("/expired", follow_redirects=False)
    assert response.status_code == 410
    assert get_stats("expired")["clicks"] == 0

def test_unknown_link_remains_404():
    response = client.get("/unknown", follow_redirects=False)
    assert response.status_code == 404

def test_legacy_database_schema_is_migrated(tmp_path, monkeypatch):
    db_file = tmp_path / "legacy.db"
    monkeypatch.setenv("SHORTENER_DB_PATH", str(db_file))
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "CREATE TABLE urls (code TEXT PRIMARY KEY, "
            "original_url TEXT NOT NULL, created_at TEXT NOT NULL, "
            "clicks INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO urls VALUES (?, ?, ?, ?)",
            ("legacy", "https://example.com/", "2025-01-01T00:00:00+00:00", 3),
        )
    init_db()
    stats = get_stats("legacy")
    assert stats["clicks"] == 3
    assert stats["expires_at"] is None
