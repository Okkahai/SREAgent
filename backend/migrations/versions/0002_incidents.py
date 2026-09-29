"""Incidents, timeline events and evidence (docs/04).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE SEQUENCE incident_seq;

        CREATE TABLE incidents (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          short_id text UNIQUE NOT NULL,
          title text NOT NULL,
          status text NOT NULL CHECK (status IN
            ('DETECTED','INVESTIGATING','IDENTIFIED','MITIGATING','MONITORING','RESOLVED','CLOSED')),
          severity text NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
          service_id uuid NOT NULL REFERENCES services(id),
          deployment_id uuid REFERENCES deployments(id),
          environment text NOT NULL,
          rule text NOT NULL,
          fingerprint text NOT NULL,
          started_at timestamptz NOT NULL,
          detected_at timestamptz NOT NULL,
          last_breach_at timestamptz NOT NULL,
          healthy_since timestamptz,
          resolved_at timestamptz,
          confidence numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),
          outcome jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (detected_at >= started_at),
          CHECK (resolved_at IS NULL OR resolved_at >= detected_at)
        );
        -- One open incident per fingerprint (dedupe).
        CREATE UNIQUE INDEX incidents_open_fingerprint ON incidents (fingerprint)
          WHERE status NOT IN ('RESOLVED','CLOSED');
        CREATE INDEX incidents_service ON incidents (service_id, detected_at DESC);

        -- Append-only timeline.
        CREATE TABLE incident_events (
          id bigserial PRIMARY KEY,
          incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          occurred_at timestamptz NOT NULL,
          kind text NOT NULL,
          source text NOT NULL,
          summary text NOT NULL,
          level text NOT NULL DEFAULT 'OBSERVATION'
            CHECK (level IN ('OBSERVATION','HYPOTHESIS','CONFIRMED_FACT')),
          ref jsonb NOT NULL DEFAULT '{}'
        );
        CREATE INDEX incident_events_incident ON incident_events (incident_id, occurred_at);

        CREATE TABLE evidence (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          level text NOT NULL CHECK (level IN ('OBSERVATION','HYPOTHESIS','CONFIRMED_FACT')),
          type text NOT NULL,
          summary text NOT NULL,
          ref jsonb NOT NULL,
          captured_query text,
          created_by text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX evidence_incident ON evidence (incident_id);
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TABLE evidence, incident_events, incidents CASCADE; DROP SEQUENCE incident_seq"
    )
