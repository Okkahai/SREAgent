# Decisions

Status column: **Historical** = taken earlier (design docs, PR descriptions, or Gün's thread decisions), recorded here, not re-litigated. **Proposed** = needs Gün's approval. Dates are when recorded in this file unless stated.

| ID | Decision | Rationale / source | Status |
|----|----------|--------------------|--------|
| D-001 | Postgres-only store for telemetry and state, behind the `TelemetryStore` port | docs/02 ADR 001 | Historical |
| D-002 | Celery + Redis for jobs and beat | docs/02 ADR 002 | Historical |
| D-003 | OTLP-based ingestion (OTLP/HTTP protobuf, no JSON) | docs/02 ADR 003, PR #3 | Historical |
| D-004 | Detection is deterministic; AI only investigates | docs/02 ADR 004 | Historical |
| D-005 | Agent has read-only tools; no write tool exists | docs/02 ADR 005, docs/08 | Historical |
| D-006 | Modular monolith (api + worker share a codebase) | docs/02 ADR 006 | Historical |
| D-007 | Risk comes from a deterministic policy table; unknown action types are DESTRUCTIVE and refused; only `OPEN_PR` executes | PR #7, docs/08 | Historical |
| D-008 | Approvals bind to the sha256 payload hash; proposals expire after 60 min; audit log append-only via DB triggers | PR #7 | Historical |
| D-009 | `OPSPILOT_INVESTIGATOR` = llm (default) / rules / auto; both use the same evidence capture and verifier | PR #11 | Historical |
| D-010 | Production target: one Hetzner VPS, 2 vCPU / 4 GB RAM | Gün, thread, 2026-11-03/04; docs/12 | Historical |
| D-011 | Per-app Compose project with its own Postgres and Redis (no shared DB between apps) | Gün/thread, for co-hosting Market OS | Historical |
| D-012 | Memory limits on containers plus a 2 GB swapfile | docs/12, PR #14 | Historical |
| D-013 | Caddy terminates HTTPS; only 80/443 published | PR #14 | Historical |
| D-014 | Daily `pg_dump` via `scripts/backup.sh`, 7 kept locally; off-server copy is manual | PR #14, docs/12 | Historical |
| D-015 | `OPSPILOT_ACTIONS_ENABLED=false` by default; viewer, approver and ingest tokens are mandatory when publicly exposed (compose fails without them) | PR #14 | Historical |
| D-016 | No OIDC / per-user identity yet; shared tokens + one basic-auth login for the dashboard | docs/11, PR #14 | Historical (revisit: T-004) |
| D-017 | Next.js 15.5.x kept; the PostCSS build-time advisory is accepted, CI gates at `critical` | PR #14, ci.yml comment | Historical (revisit: T-008) |
| D-018 | Trivy installed as a pinned release with checksum, not via trivy-action | PR #14 | Historical |
| D-019 | Development moves to local multi-agent workflow (T3 Code, Claude Code, Codex CLI, worktrees, independent reviewers, GitHub CI); agents never merge; shared rules in AGENTS.md | Gün approved docs-only migration PR, 2026-11-06 | Historical |
| D-020 | Handoff state lives in `docs/agent/*` and is updated in the same PR as the work | PR #15, approved by Gün 2026-11-10 | Historical |
