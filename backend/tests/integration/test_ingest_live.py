"""Ingest -> Postgres -> rollup, against a real database. Needs INTEGRATION=1 and Postgres."""

import gzip
import os
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from opspilot.config import get_settings
from opspilot.db.engine import get_engine
from tests.otlp_builders import logs_request, metrics_request, trace_request

pytestmark = pytest.mark.skipif(
    not os.environ.get("INTEGRATION"), reason="set INTEGRATION=1 with Postgres and Redis running"
)
AUTH = {"Authorization": "Bearer test-token"}
PB = {"Content-Type": "application/x-protobuf"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ["OPSPILOT_INGEST_TOKEN"] = "test-token"
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    from opspilot.main import create_app

    return TestClient(create_app())


def count(sql: str) -> int:
    with get_engine().connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


def test_ingest_requires_token(client: TestClient) -> None:
    r = client.post("/v1/otlp/v1/traces", content=b"", headers=PB)
    assert r.status_code == 401
    r = client.post(
        "/v1/otlp/v1/traces", content=b"", headers={**PB, "Authorization": "Bearer nope"}
    )
    assert r.status_code == 401


def test_rejects_wrong_content_type_and_garbage(client: TestClient) -> None:
    assert client.post("/v1/otlp/v1/traces", content=b"{}", headers=AUTH).status_code == 415
    r = client.post("/v1/otlp/v1/traces", content=b"\xff\xff\xff", headers={**AUTH, **PB})
    assert r.status_code == 400


def test_full_ingest_and_rollup(client: TestClient) -> None:
    h = {**AUTH, **PB}
    ok = trace_request(trace_byte=1, duration_ms=100)
    bad = trace_request(trace_byte=2, error=True, duration_ms=900)
    assert (
        client.post("/v1/otlp/v1/traces", content=ok.SerializeToString(), headers=h).status_code
        == 200
    )
    # gzip is what the collector sends by default
    gz = gzip.compress(bad.SerializeToString())
    r = client.post("/v1/otlp/v1/traces", content=gz, headers={**h, "Content-Encoding": "gzip"})
    assert r.status_code == 200
    assert (
        client.post(
            "/v1/otlp/v1/logs", content=logs_request(trace_byte=2).SerializeToString(), headers=h
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/v1/otlp/v1/metrics", content=metrics_request().SerializeToString(), headers=h
        ).status_code
        == 200
    )

    assert count("SELECT count(*) FROM spans") == 2
    assert count("SELECT count(*) FROM log_records WHERE trace_id = repeat('02', 16)") == 1
    assert count("SELECT count(*) FROM metric_points") == 3
    assert count("SELECT count(*) FROM services WHERE name = 'checkout'") == 1
    # deployment version/commit from resource attributes are stored on every row
    assert (
        count(
            "SELECT count(*) FROM spans WHERE deployment_version = '1.0.0' AND commit_sha = 'abc1234'"
        )
        == 2
    )

    # duplicate delivery of the same span is idempotent
    client.post("/v1/otlp/v1/traces", content=ok.SerializeToString(), headers=h)
    assert count("SELECT count(*) FROM spans") == 2

    from opspilot.adapters.postgres_store import PostgresStore

    assert PostgresStore(get_engine()).rollup_service_metrics() >= 1
    (svc,) = [s for s in client.get("/v1/services").json() if s["name"] == "checkout"]
    assert svc["request_count"] == 2 and svc["error_count"] == 1
    assert svc["error_rate"] == 0.5
    assert svc["latency_p95_ms"] > 800
    stats = client.get("/v1/telemetry/stats").json()
    assert stats["spans"] == 2 and stats["log_records"] == 1


def test_old_and_future_timestamps_are_dropped(client: TestClient) -> None:
    before = count("SELECT count(*) FROM spans")
    req = trace_request(trace_byte=9)
    span = req.resource_spans[0].scope_spans[0].spans[0]
    old = int((datetime.now(UTC) - timedelta(days=30)).timestamp() * 1e9)
    span.start_time_unix_nano, span.end_time_unix_nano = old, old + 1
    client.post("/v1/otlp/v1/traces", content=req.SerializeToString(), headers={**AUTH, **PB})
    assert count("SELECT count(*) FROM spans") == before


def test_deployments_api(client: TestClient) -> None:
    body = {
        "service": "checkout",
        "environment": "demo",
        "version": "1.1.0",
        "commit_sha": "3fa9c1e",
        "started_at": datetime.now(UTC).isoformat(),
    }
    assert client.post("/v1/deployments", json=body).status_code == 401
    r = client.post("/v1/deployments", json=body, headers=AUTH)
    assert r.status_code == 201, r.text
    assert (
        client.post(
            "/v1/deployments", json={**body, "commit_sha": "not-hex!"}, headers=AUTH
        ).status_code
        == 422
    )
    rows = client.get("/v1/deployments", params={"service": "checkout"}).json()
    assert rows[0]["version"] == "1.1.0" and rows[0]["commit_sha"] == "3fa9c1e"
    second = client.post(
        "/v1/deployments",
        json={
            **body,
            "version": "1.2.0",
            "started_at": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        },
        headers=AUTH,
    ).json()
    assert second["previous_deployment_id"] == r.json()["id"]
    (svc,) = [s for s in client.get("/v1/services").json() if s["name"] == "checkout"]
    assert svc["latest_version"] == "1.2.0"


def test_partition_retention() -> None:
    from opspilot.adapters.postgres_store import PostgresStore

    store = PostgresStore(get_engine(), retention_days=7)
    today = datetime.now(UTC).date()
    with get_engine().begin() as conn:
        from opspilot.db.partitions import ensure_partition

        ensure_partition(conn, "spans", today - timedelta(days=20))
    dropped = store.maintain_partitions(today)
    assert any(name.startswith("spans_") for name in dropped)
    assert (
        count(
            "SELECT count(*) FROM pg_class WHERE relname = 'spans_' || to_char(now() + interval '1 day', 'YYYYMMDD')"
        )
        == 1
    )
