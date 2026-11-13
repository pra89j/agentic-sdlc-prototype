import pytest
from app import service
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / 'test_urls.db'
    monkeypatch.setenv('SHORTENER_DB_PATH', str(db_file))

client = TestClient(app)

def test_health_check():
    res = client.get('/health')
    assert res.status_code == 200
    assert res.json() == {'status': 'ok'}

def test_shorten_redirect_and_analytics():
    create_res = client.post('/shorten', json={'url': 'https://example.com'})
    assert create_res.status_code == 201
    code = create_res.json()['code']
    redirect_res = client.get(f'/{code}', follow_redirects=False)
    assert redirect_res.status_code == 307
    assert redirect_res.headers['location'] == 'https://example.com/'
    stats_res = client.get(f'/stats/{code}')
    assert stats_res.status_code == 200
    assert stats_res.json()['original_url'] == 'https://example.com/'
    assert stats_res.json()['created_at']
    assert stats_res.json()['clicks'] == 1

def test_create_short_url_retries_code_collisions(monkeypatch):
    generated_codes = iter(['duplicate', 'available'])
    saved_codes = []
    monkeypatch.setattr(service, 'generate_code', lambda: next(generated_codes))
    monkeypatch.setattr(service, 'save_url', lambda code, url: saved_codes.append(code) or code == 'available')
    assert service.create_short_url('https://example.com/') == 'available'
    assert saved_codes == ['duplicate', 'available']

def test_custom_alias_conflict():
    res1 = client.post('/shorten', json={'url': 'https://example.com', 'custom_alias': 'my-link'})
    assert res1.status_code == 201
    res2 = client.post('/shorten', json={'url': 'https://example.com', 'custom_alias': 'my-link'})
    assert res2.status_code == 409

def test_invalid_url_rejected():
    res = client.post('/shorten', json={'url': 'not-a-valid-url'})
    assert res.status_code == 422
