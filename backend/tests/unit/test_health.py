from fastapi.testclient import TestClient

from opspilot.main import app

client = TestClient(app)


def test_healthz() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readyz_degraded_without_dependencies(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    from opspilot.config import get_settings

    get_settings.cache_clear()
    try:
        r = client.get("/readyz")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"
    finally:
        get_settings.cache_clear()
