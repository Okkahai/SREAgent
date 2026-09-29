"""Action proposals, approvals, executions and the audit log (docs/04, docs/08 §3).

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE action_proposals (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
          investigation_id uuid REFERENCES investigations(id),
          type text NOT NULL,
          title text NOT NULL,
          rationale text NOT NULL,
          parameters jsonb NOT NULL DEFAULT '{}',
          payload_hash text NOT NULL,          -- approval is bound to this exact payload
          risk text NOT NULL CHECK (risk IN ('READ_ONLY','LOW','HIGH','DESTRUCTIVE')),
          status text NOT NULL DEFAULT 'PENDING_APPROVAL' CHECK (status IN
            ('PENDING_APPROVAL','APPROVED','REJECTED','EXECUTING','SUCCEEDED','FAILED','EXPIRED')),
          policy_decision jsonb NOT NULL,      -- written by the policy engine only
          expires_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX action_proposals_incident ON action_proposals (incident_id, created_at);

        CREATE TABLE approvals (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          proposal_id uuid NOT NULL REFERENCES action_proposals(id),
          approver text NOT NULL,
          decision text NOT NULL CHECK (decision IN ('APPROVE','REJECT')),
          payload_hash text NOT NULL,
          comment text,
          decided_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE action_executions (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          proposal_id uuid NOT NULL REFERENCES action_proposals(id),
          approval_id uuid NOT NULL REFERENCES approvals(id),
          status text NOT NULL,
          started_at timestamptz NOT NULL DEFAULT now(),
          finished_at timestamptz,
          result jsonb,
          error text
        );

        -- No execution without an APPROVE decision on the same payload, enforced in the database.
        CREATE FUNCTION require_approval_for_execution() RETURNS trigger AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM approvals a JOIN action_proposals p ON p.id = a.proposal_id
            WHERE a.id = NEW.approval_id AND a.proposal_id = NEW.proposal_id
              AND a.decision = 'APPROVE' AND a.payload_hash = p.payload_hash
          ) THEN
            RAISE EXCEPTION 'execution requires an APPROVE decision on the current payload';
          END IF;
          RETURN NEW;
        END $$ LANGUAGE plpgsql;
        CREATE TRIGGER action_executions_need_approval BEFORE INSERT ON action_executions
          FOR EACH ROW EXECUTE FUNCTION require_approval_for_execution();

        CREATE TABLE audit_log (
          id bigserial PRIMARY KEY,
          at timestamptz NOT NULL DEFAULT now(),
          actor text NOT NULL,
          action text NOT NULL,
          subject text NOT NULL,
          detail jsonb NOT NULL DEFAULT '{}'
        );
        CREATE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'audit_log is append-only'; END $$ LANGUAGE plpgsql;
        CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
          FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TABLE action_executions, approvals, action_proposals, audit_log CASCADE; "
        "DROP FUNCTION require_approval_for_execution(), audit_log_append_only()"
    )
