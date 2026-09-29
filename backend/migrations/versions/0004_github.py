"""GitHub read-only cache: commits (with changed files and owners) and CI runs (docs/02, docs/08).

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE commits (
          repo text NOT NULL,
          sha text NOT NULL,
          message text NOT NULL,
          author text,
          committed_at timestamptz,
          url text,
          files jsonb NOT NULL DEFAULT '[]',
          owners jsonb NOT NULL DEFAULT '[]',
          fetched_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (repo, sha)
        );

        CREATE TABLE ci_runs (
          id bigint PRIMARY KEY,
          repo text NOT NULL,
          name text NOT NULL,
          head_sha text NOT NULL,
          status text NOT NULL,
          conclusion text,
          html_url text,
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ci_runs_sha ON ci_runs (repo, head_sha);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE ci_runs, commits")
