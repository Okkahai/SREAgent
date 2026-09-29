"""PostgreSQL implementation of telemetry storage, service registry, rollups and deployments."""

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Engine, text

from opspilot.db.partitions import drop_old_partitions, ensure_partition
from opspilot.services.otlp import LogRow, MetricRow, ResourceInfo, SpanRow

MAX_FUTURE = timedelta(hours=1)


class PostgresStore:
    def __init__(self, engine: Engine, retention_days: int = 7) -> None:
        self.engine = engine
        self.retention_days = retention_days

    # -- helpers ---------------------------------------------------------------------------
    def _service_ids(
        self, conn: Connection, resources: Iterable[ResourceInfo]
    ) -> dict[tuple[str, str], str]:
        ids: dict[tuple[str, str], str] = {}
        for r in {(r.service, r.environment) for r in resources}:
            ids[r] = conn.execute(
                text(
                    "INSERT INTO services (name, environment) VALUES (:n, :e) "
                    "ON CONFLICT (name, environment) DO UPDATE SET name = EXCLUDED.name "
                    "RETURNING id"
                ),
                {"n": r[0], "e": r[1]},
            ).scalar_one()
        return ids

    def _acceptable(self, t: datetime, now: datetime) -> bool:
        return now - timedelta(days=self.retention_days) <= t <= now + MAX_FUTURE

    def _ensure(self, conn: Connection, table: str, times: Iterable[datetime]) -> None:
        for day in sorted({t.astimezone(UTC).date() for t in times}):
            ensure_partition(conn, table, day)

    # -- writes ----------------------------------------------------------------------------
    def insert_spans(self, rows: Sequence[SpanRow]) -> int:
        now = datetime.now(UTC)
        rows = [r for r in rows if self._acceptable(r.start_time, now)]
        if not rows:
            return 0
        with self.engine.begin() as conn:
            ids = self._service_ids(conn, (r.resource for r in rows))
            self._ensure(conn, "spans", (r.start_time for r in rows))
            conn.execute(
                text(
                    "INSERT INTO spans (trace_id, span_id, parent_span_id, service_id, name, kind, "
                    "start_time, duration_ns, status_code, status_message, deployment_version, "
                    "commit_sha, attributes) VALUES (:trace_id, :span_id, :parent, :sid, :name, "
                    ":kind, :start, :dur, :sc, :sm, :ver, :commit, CAST(:attrs AS jsonb)) "
                    "ON CONFLICT DO NOTHING"
                ),
                [
                    {
                        "trace_id": r.trace_id,
                        "span_id": r.span_id,
                        "parent": r.parent_span_id,
                        "sid": ids[(r.resource.service, r.resource.environment)],
                        "name": r.name,
                        "kind": r.kind,
                        "start": r.start_time,
                        "dur": r.duration_ns,
                        "sc": r.status_code,
                        "sm": r.status_message,
                        "ver": r.resource.version,
                        "commit": r.resource.commit,
                        "attrs": json.dumps(r.attributes),
                    }
                    for r in rows
                ],
            )
        return len(rows)

    def insert_logs(self, rows: Sequence[LogRow]) -> int:
        now = datetime.now(UTC)
        rows = [r for r in rows if self._acceptable(r.time, now)]
        if not rows:
            return 0
        with self.engine.begin() as conn:
            ids = self._service_ids(conn, (r.resource for r in rows))
            self._ensure(conn, "log_records", (r.time for r in rows))
            conn.execute(
                text(
                    "INSERT INTO log_records (time, service_id, environment, severity_number, body, "
                    "trace_id, span_id, deployment_version, commit_sha, attributes) VALUES "
                    "(:time, :sid, :env, :sev, :body, :trace_id, :span_id, :ver, :commit, "
                    "CAST(:attrs AS jsonb))"
                ),
                [
                    {
                        "time": r.time,
                        "sid": ids[(r.resource.service, r.resource.environment)],
                        "env": r.resource.environment,
                        "sev": r.severity_number,
                        "body": r.body,
                        "trace_id": r.trace_id,
                        "span_id": r.span_id,
                        "ver": r.resource.version,
                        "commit": r.resource.commit,
                        "attrs": json.dumps(r.attributes),
                    }
                    for r in rows
                ],
            )
        return len(rows)

    def insert_metrics(self, rows: Sequence[MetricRow]) -> int:
        now = datetime.now(UTC)
        rows = [r for r in rows if self._acceptable(r.time, now)]
        if not rows:
            return 0
        with self.engine.begin() as conn:
            ids = self._service_ids(conn, (r.resource for r in rows))
            self._ensure(conn, "metric_points", (r.time for r in rows))
            conn.execute(
                text(
                    "INSERT INTO metric_points (time, service_id, name, value, attributes, "
                    "deployment_version) VALUES (:time, :sid, :name, :value, CAST(:attrs AS jsonb), :ver)"
                ),
                [
                    {
                        "time": r.time,
                        "sid": ids[(r.resource.service, r.resource.environment)],
                        "name": r.name,
                        "value": r.value,
                        "attrs": json.dumps(r.attributes),
                        "ver": r.resource.version,
                    }
                    for r in rows
                ],
            )
        return len(rows)

    # -- maintenance -----------------------------------------------------------------------
    def rollup_service_metrics(self, window_minutes: int = 10) -> int:
        """Recompute per-minute RED metrics for the recent window from server spans (kind=2)."""
        sql = """
        INSERT INTO service_metrics_1m
          (bucket, service_id, route, request_count, error_count,
           latency_p50_ms, latency_p95_ms, latency_p99_ms)
        SELECT bucket, service_id, route, count(*), count(*) FILTER (WHERE is_error),
               percentile_cont(0.50) WITHIN GROUP (ORDER BY ms),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY ms),
               percentile_cont(0.99) WITHIN GROUP (ORDER BY ms)
        FROM (
          SELECT date_trunc('minute', start_time) AS bucket, service_id,
                 COALESCE(attributes->>'http.route', name) AS route,
                 duration_ns / 1e6 AS ms,
                 (status_code = 2
                  OR COALESCE(attributes->>'http.response.status_code',
                              attributes->>'http.status_code', '0') ~ '^5[0-9][0-9]$') AS is_error
          FROM spans
          WHERE kind = 2 AND start_time >= now() - make_interval(mins => :w)
        ) s
        GROUP BY bucket, service_id, route
        ON CONFLICT (service_id, route, bucket) DO UPDATE SET
          request_count = EXCLUDED.request_count, error_count = EXCLUDED.error_count,
          latency_p50_ms = EXCLUDED.latency_p50_ms, latency_p95_ms = EXCLUDED.latency_p95_ms,
          latency_p99_ms = EXCLUDED.latency_p99_ms
        """
        with self.engine.begin() as conn:
            return int(conn.execute(text(sql), {"w": window_minutes}).rowcount)

    def maintain_partitions(self, today: date | None = None) -> list[str]:
        today = today or datetime.now(UTC).date()
        with self.engine.begin() as conn:
            for offset in range(0, 3):
                for table in ("log_records", "spans", "metric_points"):
                    ensure_partition(conn, table, today + timedelta(days=offset))
            return drop_old_partitions(conn, self.retention_days, today)

    # -- deployments -----------------------------------------------------------------------
    def record_deployment(self, d: dict[str, Any]) -> dict[str, Any]:
        with self.engine.begin() as conn:
            sid = self._service_ids(
                conn, [ResourceInfo(d["service"], d["environment"], None, None)]
            )[(d["service"], d["environment"])]
            prev = conn.execute(
                text(
                    "SELECT id FROM deployments WHERE service_id = :s AND started_at <= :t "
                    "ORDER BY started_at DESC LIMIT 1"
                ),
                {"s": sid, "t": d["started_at"]},
            ).scalar()
            row: Any = conn.execute(
                text(
                    "INSERT INTO deployments (service_id, version, commit_sha, previous_deployment_id, "
                    "status, started_at, finished_at, ci_run_url, metadata) VALUES (:s, :v, :c, :p, "
                    ":st, :sa, :fa, :ci, CAST(:m AS jsonb)) RETURNING id"
                ),
                {
                    "s": sid,
                    "v": d["version"],
                    "c": d.get("commit_sha"),
                    "p": prev,
                    "st": d["status"],
                    "sa": d["started_at"],
                    "fa": d.get("finished_at"),
                    "ci": d.get("ci_run_url"),
                    "m": json.dumps(d.get("metadata") or {}),
                },
            ).scalar_one()
        return {"id": str(row), "previous_deployment_id": str(prev) if prev else None}

    def list_deployments(self, service: str | None, limit: int) -> list[dict[str, Any]]:
        sql = (
            "SELECT d.id, s.name AS service, s.environment, d.version, d.commit_sha, d.status, "
            "d.started_at, d.finished_at, d.ci_run_url, d.previous_deployment_id "
            "FROM deployments d JOIN services s ON s.id = d.service_id "
            "WHERE (CAST(:svc AS text) IS NULL OR s.name = :svc) "
            "ORDER BY d.started_at DESC LIMIT :lim"
        )
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"svc": service, "lim": limit}).mappings().all()
        return [{k: (str(v) if k.endswith("id") and v else v) for k, v in r.items()} for r in rows]

    # -- reads -----------------------------------------------------------------------------
    def list_services(self, window_minutes: int = 5) -> list[dict[str, Any]]:
        sql = """
        SELECT s.name, s.environment,
               COALESCE(m.requests, 0) AS request_count, COALESCE(m.errors, 0) AS error_count,
               CASE WHEN COALESCE(m.requests, 0) > 0
                    THEN m.errors::float / m.requests ELSE NULL END AS error_rate,
               COALESCE(m.requests, 0)::float / (:w * 60) AS requests_per_second,
               m.p95 AS latency_p95_ms,
               d.version AS latest_version, d.commit_sha AS latest_commit,
               d.started_at AS latest_deployed_at
        FROM services s
        LEFT JOIN (
          SELECT service_id, sum(request_count)::bigint AS requests, sum(error_count)::bigint AS errors,
                 max(latency_p95_ms)::float AS p95
          FROM service_metrics_1m WHERE bucket >= now() - make_interval(mins => :w)
          GROUP BY service_id) m ON m.service_id = s.id
        LEFT JOIN LATERAL (
          SELECT version, commit_sha, started_at FROM deployments
          WHERE service_id = s.id ORDER BY started_at DESC LIMIT 1) d ON true
        ORDER BY s.name
        """
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(text(sql), {"w": window_minutes}).mappings()]

    def telemetry_stats(self, window_minutes: int = 10) -> dict[str, int]:
        with self.engine.connect() as conn:
            out: dict[str, int] = {}
            for table, col in (
                ("spans", "start_time"),
                ("log_records", "time"),
                ("metric_points", "time"),
            ):
                out[table] = int(
                    conn.execute(
                        text(
                            f"SELECT count(*) FROM {table} WHERE {col} >= now() - make_interval(mins => :w)"
                        ),
                        {"w": window_minutes},
                    ).scalar_one()
                )
            return out
