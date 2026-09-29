"""Postgres persistence and detection queries for incidents. All methods take a Connection so the
detector can keep an incident change, its timeline event and its evidence in one transaction."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, text

from opspilot.services.detection import WindowStats

Row = dict[str, Any]


def _one(conn: Connection, sql: str, **params: Any) -> Row | None:
    r = conn.execute(text(sql), params).mappings().first()
    return dict(r) if r else None


# -- detection inputs -----------------------------------------------------------------------
def service_targets(conn: Connection) -> list[Row]:
    return [
        dict(r) for r in conn.execute(text("SELECT id, name, environment FROM services")).mappings()
    ]


def window_stats(conn: Connection, service_id: Any, start: datetime, end: datetime) -> WindowStats:
    r = _one(
        conn,
        "SELECT COALESCE(sum(request_count),0)::bigint AS req, COALESCE(sum(error_count),0)::bigint AS err, "
        "max(latency_p95_ms)::float AS p95 FROM service_metrics_1m "
        "WHERE service_id = :s AND bucket >= date_trunc('minute', CAST(:a AS timestamptz)) AND bucket <= :b",
        s=service_id,
        a=start,
        b=end,
    )
    assert r is not None
    return WindowStats(int(r["req"]), int(r["err"]), r["p95"])


def baseline(
    conn: Connection, service_id: Any, start: datetime, end: datetime
) -> tuple[float | None, float | None]:
    """Median per-minute error rate and p95 (median resists a short outage poisoning the baseline)."""
    r = _one(
        conn,
        "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY err::float / req) AS rate, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY p95) AS p95 FROM ("
        "  SELECT bucket, sum(request_count) AS req, sum(error_count) AS err, max(latency_p95_ms) AS p95 "
        "  FROM service_metrics_1m WHERE service_id = :s AND bucket >= :a AND bucket < :b "
        "  GROUP BY bucket HAVING sum(request_count) >= 5) m",
        s=service_id,
        a=start,
        b=end,
    )
    assert r is not None
    return r["rate"], r["p95"]


def pool_stats(
    conn: Connection, service_id: Any, start: datetime, end: datetime
) -> tuple[float | None, float | None, int]:
    """(avg connections in use, pool max, sample count) from the demo's pool gauges."""
    r = _one(
        conn,
        "SELECT (avg(value) FILTER (WHERE name = 'db.client.connection.count' "
        "                            AND attributes->>'state' = 'used'))::float AS used, "
        "       (max(value) FILTER (WHERE name = 'db.client.connection.max'))::float AS lim, "
        "       count(*) FILTER (WHERE name = 'db.client.connection.count' "
        "                         AND attributes->>'state' = 'used')::int AS n "
        "FROM metric_points WHERE service_id = :s AND time >= :a AND time <= :b "
        "AND name IN ('db.client.connection.count', 'db.client.connection.max')",
        s=service_id,
        a=start,
        b=end,
    )
    assert r is not None
    return r["used"], r["lim"], int(r["n"])


def onset_error_rate(
    conn: Connection, service_id: Any, since: datetime, threshold: float
) -> datetime | None:
    """Start of the current run of unhealthy minutes (after the latest healthy minute)."""
    r = _one(
        conn,
        "WITH m AS (SELECT bucket, sum(error_count)::float / sum(request_count) AS rate "
        "  FROM service_metrics_1m WHERE service_id = :s "
        "  AND bucket >= date_trunc('minute', CAST(:a AS timestamptz)) "
        "  GROUP BY bucket HAVING sum(request_count) >= 5) "
        "SELECT min(bucket) AS t FROM m WHERE rate >= :th AND bucket > "
        "  COALESCE((SELECT max(bucket) FROM m WHERE rate < :th), '-infinity'::timestamptz)",
        s=service_id,
        a=since,
        th=threshold,
    )
    return r["t"] if r else None


def correlate_deployment(
    conn: Connection, service_id: Any, environment: str, at: datetime, minutes: int
) -> Row | None:
    """Most recent deployment shortly before `at`, preferring the affected service itself."""
    return _one(
        conn,
        "SELECT d.id, d.version, d.commit_sha, d.started_at, s.name AS service, "
        "       (d.service_id = :sid) AS same_service "
        "FROM deployments d JOIN services s ON s.id = d.service_id "
        "WHERE s.environment = :env AND d.started_at <= :at AND d.started_at >= :at - make_interval(mins => :m) "
        "ORDER BY (d.service_id = :sid) DESC, d.started_at DESC LIMIT 1",
        sid=service_id,
        env=environment,
        at=at,
        m=minutes,
    )


# -- incidents ------------------------------------------------------------------------------
def find_open(conn: Connection, fingerprint: str) -> Row | None:
    return _one(
        conn,
        "SELECT * FROM incidents WHERE fingerprint = :f AND status NOT IN ('RESOLVED','CLOSED')",
        f=fingerprint,
    )


def latest_resolved(conn: Connection, fingerprint: str) -> Row | None:
    return _one(
        conn,
        "SELECT * FROM incidents WHERE fingerprint = :f AND status = 'RESOLVED' "
        "ORDER BY resolved_at DESC LIMIT 1",
        f=fingerprint,
    )


def create_incident(conn: Connection, **v: Any) -> Row:
    row = _one(
        conn,
        "INSERT INTO incidents (short_id, title, status, severity, service_id, deployment_id, environment, "
        "rule, fingerprint, started_at, detected_at, last_breach_at) VALUES "
        "('INC-' || lpad(nextval('incident_seq')::text, 4, '0'), :title, 'DETECTED', :severity, :service_id, "
        ":deployment_id, :environment, :rule, :fingerprint, :started_at, :detected_at, :detected_at) RETURNING *",
        **v,
    )
    assert row is not None
    return row


def update_incident(conn: Connection, incident_id: Any, **fields: Any) -> None:
    allowed = {
        "status",
        "severity",
        "last_breach_at",
        "healthy_since",
        "resolved_at",
        "outcome",
        "title",
    }
    assert set(fields) <= allowed, set(fields) - allowed
    sets = ", ".join(
        f"{k} = {'CAST(:' + k + ' AS jsonb)' if k == 'outcome' else ':' + k}" for k in fields
    )
    params = {
        k: (json.dumps(v) if k == "outcome" and v is not None else v) for k, v in fields.items()
    }
    conn.execute(
        text(f"UPDATE incidents SET {sets}, updated_at = now() WHERE id = :id"),
        {**params, "id": incident_id},
    )


def add_event(
    conn: Connection,
    incident_id: Any,
    at: datetime,
    kind: str,
    source: str,
    summary: str,
    level: str = "OBSERVATION",
    ref: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO incident_events (incident_id, occurred_at, kind, source, summary, level, ref) "
            "VALUES (:i, :at, :k, :src, :sum, :lvl, CAST(:ref AS jsonb))"
        ),
        {
            "i": incident_id,
            "at": at,
            "k": kind,
            "src": source,
            "sum": summary,
            "lvl": level,
            "ref": json.dumps(ref or {}, default=str),
        },
    )


def add_evidence(
    conn: Connection,
    incident_id: Any,
    type_: str,
    summary: str,
    ref: dict[str, Any],
    captured_query: str | None = None,
    created_by: str = "detector",
    level: str = "OBSERVATION",
) -> Any:
    return conn.execute(
        text(
            "INSERT INTO evidence (incident_id, level, type, summary, ref, captured_query, created_by) "
            "VALUES (:i, :lvl, :t, :s, CAST(:ref AS jsonb), :q, :by) RETURNING id"
        ),
        {
            "lvl": level,
            "i": incident_id,
            "t": type_,
            "s": summary,
            "ref": json.dumps(ref, default=str),
            "q": captured_query,
            "by": created_by,
        },
    ).scalar_one()


# -- reads for the API ----------------------------------------------------------------------
_INCIDENT_SELECT = (
    "SELECT i.id, i.short_id, i.title, i.status, i.severity, s.name AS service, i.environment, i.rule, "
    "i.started_at, i.detected_at, i.resolved_at, i.confidence, i.outcome, "
    "CASE WHEN d.id IS NULL THEN NULL ELSE jsonb_build_object('id', d.id, 'version', d.version, "
    "'commit_sha', d.commit_sha, 'started_at', d.started_at) END AS deployment "
    "FROM incidents i JOIN services s ON s.id = i.service_id LEFT JOIN deployments d ON d.id = i.deployment_id "
)


def list_incidents(conn: Connection, open_only: bool, limit: int) -> list[Row]:
    where = "WHERE i.status NOT IN ('RESOLVED','CLOSED') " if open_only else ""
    return [
        dict(r)
        for r in conn.execute(
            text(_INCIDENT_SELECT + where + "ORDER BY i.detected_at DESC LIMIT :n"), {"n": limit}
        ).mappings()
    ]


def get_incident(conn: Connection, ident: str) -> Row | None:
    inc = _one(conn, _INCIDENT_SELECT + "WHERE i.short_id = :x OR i.id::text = :x", x=ident)
    if inc is None:
        return None
    inc["timeline"] = [
        dict(r)
        for r in conn.execute(
            text(
                "SELECT occurred_at, kind, source, level, summary, ref FROM incident_events "
                "WHERE incident_id = :i ORDER BY occurred_at, id"
            ),
            {"i": inc["id"]},
        ).mappings()
    ]
    sha = (inc["deployment"] or {}).get("commit_sha")
    inc["commit"] = None
    inc["ci_runs"] = []
    if sha:
        c = (
            conn.execute(
                text(
                    "SELECT repo, sha, message, author, committed_at, url, files, owners FROM commits "
                    "WHERE sha = :s ORDER BY fetched_at DESC LIMIT 1"
                ),
                {"s": sha},
            )
            .mappings()
            .first()
        )
        inc["commit"] = dict(c) if c else None
        inc["ci_runs"] = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT name, status, conclusion, html_url, updated_at FROM ci_runs "
                    "WHERE head_sha = :s ORDER BY updated_at DESC LIMIT 10"
                ),
                {"s": sha},
            ).mappings()
        ]
    inc["investigations"] = [
        dict(r)
        for r in conn.execute(
            text(
                "SELECT id, status, model, error, result, started_at, finished_at FROM investigations "
                "WHERE incident_id = :i ORDER BY started_at"
            ),
            {"i": inc["id"]},
        ).mappings()
    ]
    inc["evidence"] = [
        dict(r)
        for r in conn.execute(
            text(
                "SELECT id, level, type, summary, ref, captured_query, created_by, created_at "
                "FROM evidence WHERE incident_id = :i ORDER BY created_at"
            ),
            {"i": inc["id"]},
        ).mappings()
    ]
    return inc
