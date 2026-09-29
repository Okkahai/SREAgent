"""AI investigations and their audited steps (docs/07).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE investigations (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          status text NOT NULL CHECK (status IN ('RUNNING','COMPLETED','FAILED')),
          model text,
          error text,
          result jsonb,
          started_at timestamptz NOT NULL DEFAULT now(),
          finished_at timestamptz
        );
        -- Claiming an incident for investigation is an insert; only one may run at a time.
        CREATE UNIQUE INDEX investigations_one_running ON investigations (incident_id)
          WHERE status = 'RUNNING';
        CREATE INDEX investigations_incident ON investigations (incident_id, started_at);

        CREATE TABLE agent_steps (
          id bigserial PRIMARY KEY,
          investigation_id uuid NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
          seq int NOT NULL,
          tool text NOT NULL,
          args jsonb NOT NULL,
          evidence_id uuid REFERENCES evidence(id),
          error text,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX agent_steps_investigation ON agent_steps (investigation_id, seq);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE agent_steps, investigations CASCADE")
