# 04 — Database Schema (PostgreSQL 16)

Conventions: UUID primary keys (`gen_random_uuid()`), `timestamptz` everywhere (UTC), `created_at/updated_at` on mutable tables, JSONB for attributes. Telemetry tables are range-partitioned by time. Migrations via Alembic (introduced in Phase 3 with the first tables).

## ER overview

```
services ─┬─< deployments >── commits >── repositories
          ├─< incidents ─┬─< incident_events        (timeline)
          │              ├─< evidence ──> (log/metric/trace/deployment/commit refs)
          │              ├─< hypotheses ─< hypothesis_evidence
          │              ├─< investigations ─< agent_steps
          │              ├─< action_proposals ─< approvals
          │              │                    └─< action_executions
          │              └─ incident_deployments (M:N)
          ├─< log_records / metric_points / spans   (partitioned telemetry)
          └─< detection_rules
```

## Core tables

```sql
CREATE TYPE incident_status   AS ENUM ('DETECTED','INVESTIGATING','IDENTIFIED','MITIGATING','MONITORING','RESOLVED','CLOSED');
CREATE TYPE severity          AS ENUM ('LOW','MEDIUM','HIGH','CRITICAL');
CREATE TYPE epistemic_level   AS ENUM ('OBSERVATION','HYPOTHESIS','CONFIRMED_FACT');
CREATE TYPE action_status     AS ENUM ('PROPOSED','PENDING_APPROVAL','APPROVED','REJECTED','EXECUTING','SUCCEEDED','FAILED','EXPIRED');
CREATE TYPE action_risk       AS ENUM ('READ_ONLY','LOW','HIGH','DESTRUCTIVE');

CREATE TABLE services (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  environment text NOT NULL,                 -- prod|staging|dev
  repository_id uuid REFERENCES repositories(id),
  owner_team text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (name, environment)
);

CREATE TABLE repositories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider text NOT NULL,                    -- github
  full_name text NOT NULL,                   -- owner/repo
  default_branch text NOT NULL,
  installation_ref text,                     -- GitHub App installation id (no secrets stored here)
  UNIQUE (provider, full_name)
);

CREATE TABLE commits (
  sha text PRIMARY KEY,
  repository_id uuid NOT NULL REFERENCES repositories(id),
  author text, message text, committed_at timestamptz NOT NULL,
  files_changed jsonb NOT NULL DEFAULT '[]'  -- [{path, additions, deletions, status}]
);

CREATE TABLE deployments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  service_id uuid NOT NULL REFERENCES services(id),
  version text NOT NULL,
  commit_sha text REFERENCES commits(sha),
  previous_deployment_id uuid REFERENCES deployments(id),
  status text NOT NULL,                      -- STARTED|SUCCEEDED|FAILED|ROLLED_BACK
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  ci_run_url text,
  metadata jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON deployments (service_id, started_at DESC);

CREATE TABLE incidents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  short_id text UNIQUE NOT NULL,             -- INC-0042, human-friendly
  title text NOT NULL,
  status incident_status NOT NULL DEFAULT 'DETECTED',
  severity severity NOT NULL,
  service_id uuid NOT NULL REFERENCES services(id),   -- primary affected service
  affected_service_ids uuid[] NOT NULL DEFAULT '{}',
  deployment_id uuid REFERENCES deployments(id),      -- suspected/associated deployment
  environment text NOT NULL,
  fingerprint text NOT NULL,                 -- dedupe key: rule + service + env
  started_at timestamptz NOT NULL,           -- estimated fault onset
  detected_at timestamptz NOT NULL,
  resolved_at timestamptz,
  root_cause_hypothesis_id uuid,             -- FK added after hypotheses
  confidence numeric(3,2) CHECK (confidence BETWEEN 0 AND 1),
  outcome jsonb,                             -- {result, recovered_at, mttr_s, notes}
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (detected_at >= started_at OR started_at IS NULL),
  CHECK (resolved_at IS NULL OR resolved_at >= detected_at)
);
-- one open incident per fingerprint
CREATE UNIQUE INDEX incidents_open_fp ON incidents (fingerprint) WHERE status NOT IN ('RESOLVED','CLOSED');

CREATE TABLE incident_events (           -- append-only timeline
  id bigserial PRIMARY KEY,
  incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  occurred_at timestamptz NOT NULL,
  kind text NOT NULL,                      -- DEPLOYMENT|METRIC_ANOMALY|LOG_PATTERN|STATE_CHANGE|AI_STEP|ACTION|HUMAN
  source text NOT NULL,                    -- detector|agent|github|user
  summary text NOT NULL,
  level epistemic_level NOT NULL DEFAULT 'OBSERVATION',
  ref jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON incident_events (incident_id, occurred_at);

CREATE TABLE evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  level epistemic_level NOT NULL,
  type text NOT NULL,                      -- LOG|METRIC|TRACE|DEPLOYMENT|COMMIT|DIFF|CONFIG
  summary text NOT NULL,
  ref jsonb NOT NULL,                      -- {trace_id} | {log_ids:[..]} | {metric, window, query} | {sha, path, lines}
  captured_query text,                     -- exact deterministic query, so evidence is reproducible
  created_by text NOT NULL,                -- detector|agent:<tool>|user
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE hypotheses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  investigation_id uuid,
  statement text NOT NULL,
  level epistemic_level NOT NULL DEFAULT 'HYPOTHESIS',
  confidence numeric(3,2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  would_confirm text, would_refute text,
  status text NOT NULL DEFAULT 'OPEN',     -- OPEN|SUPPORTED|REFUTED|CONFIRMED
  suspected_changes jsonb NOT NULL DEFAULT '[]',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE hypothesis_evidence (
  hypothesis_id uuid REFERENCES hypotheses(id) ON DELETE CASCADE,
  evidence_id uuid REFERENCES evidence(id) ON DELETE CASCADE,
  stance text NOT NULL CHECK (stance IN ('SUPPORTS','REFUTES')),
  PRIMARY KEY (hypothesis_id, evidence_id)
);
ALTER TABLE incidents ADD FOREIGN KEY (root_cause_hypothesis_id) REFERENCES hypotheses(id);
-- Enforced by trigger: a hypothesis with confidence > 0 or level > OBSERVATION
-- may only be set as incidents.root_cause_hypothesis_id if >=1 SUPPORTS evidence row exists.

CREATE TABLE investigations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  status text NOT NULL,                    -- QUEUED|RUNNING|COMPLETED|FAILED
  model text NOT NULL, prompt_version text NOT NULL,
  started_at timestamptz, finished_at timestamptz,
  input_tokens int, output_tokens int, error text,
  result jsonb                             -- validated structured output
);
CREATE TABLE agent_steps (                 -- full tool-call audit trail
  id bigserial PRIMARY KEY,
  investigation_id uuid NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
  seq int NOT NULL, tool text NOT NULL,
  arguments jsonb NOT NULL, result_summary text, result_ref jsonb,
  duration_ms int, created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE action_proposals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  type text NOT NULL,                      -- OPEN_PR|ROLLBACK|RESTART|SCALE|CONFIG_CHANGE|RUNBOOK
  title text NOT NULL, rationale text NOT NULL,
  parameters jsonb NOT NULL DEFAULT '{}',
  risk action_risk NOT NULL,               -- assigned by POLICY, never by the LLM
  status action_status NOT NULL DEFAULT 'PROPOSED',
  policy_decision jsonb NOT NULL,          -- which rules fired, requires_approval, approver_role
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE approvals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id uuid NOT NULL REFERENCES action_proposals(id),
  approver text NOT NULL, decision text NOT NULL CHECK (decision IN ('APPROVE','REJECT')),
  comment text, decided_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE action_executions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id uuid NOT NULL REFERENCES action_proposals(id),
  approval_id uuid NOT NULL REFERENCES approvals(id),   -- cannot execute without approval
  status action_status NOT NULL, started_at timestamptz, finished_at timestamptz,
  result jsonb, error text
);

CREATE TABLE detection_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text UNIQUE NOT NULL, kind text NOT NULL,    -- ERROR_RATE|LATENCY_P95|SATURATION|DEPLOY_REGRESSION|LOG_PATTERN
  params jsonb NOT NULL, severity severity NOT NULL, enabled bool NOT NULL DEFAULT true
);

CREATE TABLE audit_log (                          -- append-only, all state-changing actions
  id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL, action text NOT NULL, subject text NOT NULL, detail jsonb NOT NULL DEFAULT '{}'
);
```

## Telemetry tables (partitioned by day on `time`)

```sql
CREATE TABLE log_records (
  time timestamptz NOT NULL, service_id uuid NOT NULL, environment text NOT NULL,
  severity_number smallint NOT NULL, body text NOT NULL,
  trace_id char(32), span_id char(16),
  deployment_version text, commit_sha text,
  attributes jsonb NOT NULL DEFAULT '{}'
) PARTITION BY RANGE (time);
CREATE INDEX ON log_records (service_id, time DESC);
CREATE INDEX ON log_records (trace_id) WHERE trace_id IS NOT NULL;

CREATE TABLE spans (
  trace_id char(32) NOT NULL, span_id char(16) NOT NULL, parent_span_id char(16),
  service_id uuid NOT NULL, name text NOT NULL, kind smallint,
  start_time timestamptz NOT NULL, duration_ns bigint NOT NULL,
  status_code smallint NOT NULL, status_message text,
  deployment_version text, commit_sha text, attributes jsonb NOT NULL DEFAULT '{}',
  PRIMARY KEY (trace_id, span_id, start_time)
) PARTITION BY RANGE (start_time);

CREATE TABLE metric_points (
  time timestamptz NOT NULL, service_id uuid NOT NULL, name text NOT NULL,
  value double precision NOT NULL, attributes jsonb NOT NULL DEFAULT '{}',
  deployment_version text
) PARTITION BY RANGE (time);
CREATE INDEX ON metric_points (service_id, name, time DESC);

-- Rollup used by detectors and the dashboard (per-minute RED metrics)
CREATE TABLE service_metrics_1m (
  bucket timestamptz NOT NULL, service_id uuid NOT NULL, route text NOT NULL DEFAULT '',
  request_count bigint NOT NULL, error_count bigint NOT NULL,
  latency_p50_ms real, latency_p95_ms real, latency_p99_ms real,
  PRIMARY KEY (service_id, route, bucket)
);
```

## Retention
Raw telemetry: 7 days (drop partitions). Rollups: 30 days. Incidents, evidence, agent steps, audit log: indefinite. Evidence rows store the *captured query and excerpts*, so incident evidence remains readable after raw partitions are dropped.

## Integrity rules (enforced)
1. `root_cause_hypothesis_id` requires ≥1 supporting evidence (trigger).
2. `action_executions.approval_id` NOT NULL and `approvals.decision='APPROVE'` (trigger) — no execution without approval.
3. `action_proposals.risk` is written only by the policy service (DB role separation in Phase 10).
4. `CONFIRMED_FACT` evidence must have `created_by` ≠ an LLM-only source, i.e. produced by deterministic tools or a human.
