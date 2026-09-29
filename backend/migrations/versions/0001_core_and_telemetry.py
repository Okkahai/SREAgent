"""Core entities and partitioned telemetry tables (docs/04-database-schema.md).

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE services (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          name text NOT NULL,
          environment text NOT NULL,
          owner_team text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (name, environment)
        );

        CREATE TABLE deployments (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          service_id uuid NOT NULL REFERENCES services(id),
          version text NOT NULL,
          commit_sha text,
          previous_deployment_id uuid REFERENCES deployments(id),
          status text NOT NULL CHECK (status IN ('STARTED','SUCCEEDED','FAILED','ROLLED_BACK')),
          started_at timestamptz NOT NULL,
          finished_at timestamptz,
          ci_run_url text,
          metadata jsonb NOT NULL DEFAULT '{}'
        );
        CREATE INDEX deployments_service_started ON deployments (service_id, started_at DESC);

        -- Partitioned by day; partitions are created on demand (opspilot.db.partitions).
        CREATE TABLE log_records (
          time timestamptz NOT NULL,
          service_id uuid NOT NULL,
          environment text NOT NULL,
          severity_number smallint NOT NULL,
          body text NOT NULL,
          trace_id char(32),
          span_id char(16),
          deployment_version text,
          commit_sha text,
          attributes jsonb NOT NULL DEFAULT '{}'
        ) PARTITION BY RANGE (time);
        CREATE INDEX log_records_service_time ON log_records (service_id, time DESC);
        CREATE INDEX log_records_trace ON log_records (trace_id) WHERE trace_id IS NOT NULL;

        CREATE TABLE spans (
          trace_id char(32) NOT NULL,
          span_id char(16) NOT NULL,
          parent_span_id char(16),
          service_id uuid NOT NULL,
          name text NOT NULL,
          kind smallint NOT NULL DEFAULT 0,
          start_time timestamptz NOT NULL,
          duration_ns bigint NOT NULL,
          status_code smallint NOT NULL DEFAULT 0,
          status_message text,
          deployment_version text,
          commit_sha text,
          attributes jsonb NOT NULL DEFAULT '{}',
          PRIMARY KEY (trace_id, span_id, start_time)
        ) PARTITION BY RANGE (start_time);
        CREATE INDEX spans_service_time ON spans (service_id, start_time DESC);

        CREATE TABLE metric_points (
          time timestamptz NOT NULL,
          service_id uuid NOT NULL,
          name text NOT NULL,
          value double precision NOT NULL,
          attributes jsonb NOT NULL DEFAULT '{}',
          deployment_version text
        ) PARTITION BY RANGE (time);
        CREATE INDEX metric_points_lookup ON metric_points (service_id, name, time DESC);

        -- Per-minute RED rollup consumed by detectors (Phase 4) and the dashboard.
        CREATE TABLE service_metrics_1m (
          bucket timestamptz NOT NULL,
          service_id uuid NOT NULL REFERENCES services(id),
          route text NOT NULL DEFAULT '',
          request_count bigint NOT NULL,
          error_count bigint NOT NULL,
          latency_p50_ms real,
          latency_p95_ms real,
          latency_p99_ms real,
          PRIMARY KEY (service_id, route, bucket)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TABLE service_metrics_1m, metric_points, spans, log_records, deployments, services CASCADE"
    )
