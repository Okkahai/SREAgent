"""Runs against real Postgres/Redis (CI services or `make up`). Skipped if unreachable."""

import os

import pytest
from fastapi.testclient import TestClient

from opspilot.config import get_settings
from opspilot.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("INTEGRATION"), reason="set INTEGRATION=1 with Postgres and Redis running"
)


def test_readyz_ok() -> None:
    get_settings.cache_clear()
    r = TestClient(app).get("/readyz")
    assert r.status_code == 200, r.text
    assert r.json()["checks"] == {"postgres": "ok", "redis": "ok"}
