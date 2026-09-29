"""Load check: >= 1k log records/s through the real ingest path with no loss."""

import gzip
import os
import time

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from opspilot.config import get_settings
from opspilot.db.engine import get_engine
from tests.otlp_builders import logs_request

pytestmark = pytest.mark.skipif(
    not os.environ.get("INTEGRATION"), reason="set INTEGRATION=1 with Postgres and Redis running"
)
BATCH, REQUESTS, MIN_RATE = 500, 20, 1000


def test_ingest_sustains_1k_logs_per_second() -> None:
    os.environ["OPSPILOT_INGEST_TOKEN"] = "test-token"
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    from opspilot.main import create_app

    client = TestClient(create_app())
    headers = {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/x-protobuf",
        "Content-Encoding": "gzip",
    }
    req = logs_request("load test line")
    rl = req.resource_logs[0].scope_logs[0]
    for _ in range(BATCH - 1):
        rl.log_records.add().CopyFrom(rl.log_records[0])
    payload = gzip.compress(req.SerializeToString())

    start = time.perf_counter()
    for _ in range(REQUESTS):
        assert client.post("/v1/otlp/v1/logs", content=payload, headers=headers).status_code == 200
    elapsed = time.perf_counter() - start

    with get_engine().connect() as conn:
        stored = conn.execute(text("SELECT count(*) FROM log_records")).scalar_one()
    rate = BATCH * REQUESTS / elapsed
    print(f"ingested {stored} logs in {elapsed:.2f}s = {rate:.0f}/s")
    assert stored == BATCH * REQUESTS  # no loss
    assert rate >= MIN_RATE
