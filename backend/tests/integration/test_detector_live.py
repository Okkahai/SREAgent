"""Detector lifecycle against a real Postgres with seeded rollups. Time is injected via `now`."""

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from opspilot.db.engine import get_engine
from opspilot.db.partitions import ensure_partition
from opspilot.services.detection import DetectionConfig
from opspilot.services.detector import Detector

pytestmark = pytest.mark.skipif(
    not os.environ.get("INTEGRATION"), reason="set INTEGRATION=1 with Postgres and Redis running"
)
T = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=2)
CFG = DetectionConfig(recovery_minutes=1)


def m(minutes: int) -> datetime:
    return T + timedelta(minutes=minutes)


@pytest.fixture()
def db() -> Any:
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = get_engine()
    with engine.begin() as conn:
        sid = conn.execute(
            text(
                "INSERT INTO services (name, environment) VALUES ('checkout', 'demo') RETURNING id"
            )
        ).scalar_one()
    return engine, sid


def seed(
    engine: Any, sid: Any, start: int, end: int, requests: int, errors: int, p95: float = 50.0
) -> None:
    with engine.begin() as conn:
        for i in range(start, end):
            conn.execute(
                text(
                    "INSERT INTO service_metrics_1m (bucket, service_id, route, request_count, error_count, "
                    "latency_p95_ms) VALUES (:b, :s, '/checkout', :r, :e, :p) "
                    "ON CONFLICT (service_id, route, bucket) DO UPDATE SET request_count = :r, error_count = :e"
                ),
                {"b": m(i), "s": sid, "r": requests, "e": errors, "p": p95},
            )


def deploy(engine: Any, sid: Any, minute: int, version: str) -> Any:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO deployments (service_id, version, commit_sha, status, started_at) "
                "VALUES (:s, :v, '3fa9c1e', 'SUCCEEDED', :t) RETURNING id"
            ),
            {"s": sid, "v": version, "t": m(minute)},
        ).scalar_one()


def incidents(engine: Any) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(text("SELECT * FROM incidents ORDER BY detected_at")).mappings()
        ]


def test_full_lifecycle_detect_link_recover_reopen(db: Any) -> None:
    engine, sid = db
    det = Detector(engine, CFG)

    # healthy baseline: 1% errors for an hour -> no incident (A1)
    seed(engine, sid, -62, 3, 100, 1)
    det.evaluate(m(2))
    assert incidents(engine) == []

    # deployment, then errors jump to 30%
    dep = deploy(engine, sid, 1, "1.1.0")
    seed(engine, sid, 3, 6, 100, 30)
    det.evaluate(m(5))
    (inc,) = incidents(engine)
    assert inc["status"] == "DETECTED" and inc["severity"] == "HIGH"
    assert inc["short_id"] == "INC-0001" and inc["rule"] == "error_rate"
    assert inc["deployment_id"] == dep, (
        "incident must be correlated with the deployment before onset"
    )
    assert inc["started_at"] <= inc["detected_at"]

    with engine.connect() as conn:
        kinds = [
            r[0]
            for r in conn.execute(text("SELECT kind FROM incident_events ORDER BY occurred_at, id"))
        ]
        n_evidence = conn.execute(
            text("SELECT count(*) FROM evidence WHERE level = 'OBSERVATION'")
        ).scalar_one()
    assert kinds == ["DEPLOYMENT", "METRIC_ANOMALY", "STATE_CHANGE"] and n_evidence == 1

    # still breaching: deduplicated, no second incident
    det.evaluate(m(5))
    assert len(incidents(engine)) == 1

    # recovery -> MONITORING -> RESOLVED with outcome metrics
    seed(engine, sid, 6, 12, 100, 0)
    det.evaluate(m(8))
    assert incidents(engine)[0]["status"] == "MONITORING"
    det.evaluate(m(10))
    (inc,) = incidents(engine)
    assert inc["status"] == "RESOLVED" and inc["resolved_at"] == m(8)
    assert inc["outcome"]["result"] == "RECOVERED_SELF" and inc["outcome"]["mttr_s"] > 0

    # relapse shortly after, same deployment context -> reopened, not duplicated
    seed(engine, sid, 12, 15, 100, 40)
    det.evaluate(m(14))
    (inc,) = incidents(engine)
    assert inc["status"] == "DETECTED" and inc["resolved_at"] is None


def test_new_deployment_context_opens_new_incident(db: Any) -> None:
    engine, sid = db
    det = Detector(engine, CFG)
    seed(engine, sid, -62, 3, 100, 1)
    deploy(engine, sid, 1, "1.1.0")
    seed(engine, sid, 3, 6, 100, 30)
    det.evaluate(m(5))
    seed(engine, sid, 6, 12, 100, 0)
    det.evaluate(m(8))
    det.evaluate(m(10))
    assert incidents(engine)[0]["status"] == "RESOLVED"

    dep2 = deploy(engine, sid, 12, "1.2.0")
    seed(engine, sid, 13, 16, 100, 50)
    det.evaluate(m(15))
    old, new = incidents(engine)
    assert old["status"] == "RESOLVED" and new["status"] == "DETECTED"
    assert new["deployment_id"] == dep2 and new["short_id"] == "INC-0002"


def test_no_traffic_never_resolves_or_opens(db: Any) -> None:
    engine, sid = db
    det = Detector(engine, CFG)
    seed(engine, sid, 3, 6, 100, 30)
    det.evaluate(m(5))
    assert len(incidents(engine)) == 1
    det.evaluate(m(30))  # no data in the window: unknown, not healthy
    assert incidents(engine)[0]["status"] == "DETECTED"


def test_pool_saturation_incident(db: Any) -> None:
    engine, sid = db
    with engine.begin() as conn:
        ensure_partition(conn, "metric_points", m(0).date())
        for i in range(6):
            for name, state, value in (
                ("db.client.connection.count", "used", 2),
                ("db.client.connection.max", "max", 2),
            ):
                conn.execute(
                    text(
                        "INSERT INTO metric_points (time, service_id, name, value, attributes) "
                        "VALUES (:t, :s, :n, :v, CAST(:a AS jsonb))"
                    ),
                    {
                        "t": m(3) + timedelta(seconds=15 * i),
                        "s": sid,
                        "n": name,
                        "v": value,
                        "a": json.dumps({"state": state}),
                    },
                )
    Detector(engine, CFG).evaluate(m(4))
    (inc,) = incidents(engine)
    assert inc["rule"] == "saturation" and inc["severity"] == "HIGH"
