# Project state

Snapshot date: 2026-11-06. Verified against repo `main` @ `d022124` (PR #14 squash commit) unless marked otherwise.

## Legend
**[V]** verified by reading the repo / GitHub API on the snapshot date. **[H]** historical, from earlier session reports or PR descriptions, not re-verified. **[A]** assumption. **[Q]** open question.

## Verified facts
- [V] Repo: github.com/Okkahai/SREAgent, default branch `main`, single contributor account `Okkahai` (Gün). 14 PRs, all merged, none open.
- [V] Phases 1-10 of the roadmap (docs/10) are merged: #1 design+local env, #2 demo shop, #3 OTLP ingest, #4 detection, #5 AI investigation, #6 GitHub read-only, #7 proposals/policy/approvals/PR executor, #8 dashboard, #9 Kustomize+kind, #10 testing/hardening. Later: #11 rule-based investigator, #12 configurable host ports, #13 README rewrite, #14 Hetzner prod deploy (+ Next.js 15.5.29, mypy, pinned Trivy).
- [V] CI workflow `.github/workflows/ci.yml` has jobs: backend, web, compose, web-e2e, k8s-manifests, kind-e2e, demo, demo-unit, security, secrets-scan. The latest run on `main` (run #40, head d022124, 2026-11-04) concluded `success`. (Earlier summary said "10 checks green"; this matches the 10 jobs.)
- [V] The thread branch `claude/opspilot-architecture-phase1-n7cb0r` (tip e2e3caf) has a tree **identical** to `main` (PRs were squash-merged). It holds no unmerged work.
- [V] No `AGENTS.md`, `CLAUDE.md` or `docs/agent/` existed before this migration PR.
- [V] Migrations 0001..0005 under `backend/migrations/versions/`.
- [V] Backend modules: `api/` (health, ingest, incidents, actions, webhooks, platform), `domain/` (incident state machine, policy), `services/` (detection, detector, otlp, actions), `agent/` (llm port, tools, runner, verifier, heuristic), `integrations/` (github read, github_write, codeowners), `adapters/` (postgres), `workers/` (celery tasks), `db/`.
- [V] Web pages: overview, incidents, incident detail, services, deployments (Next.js 15 server components, read-only, refresh every 10 s).
- [V] Prod stack files exist: `docker-compose.prod.yml`, `deploy/caddy/Caddyfile`, `.env.prod.example`, `scripts/backup.sh`, `docs/12-deploy-hetzner.md`.

## Not verified / known gaps
- [V] The Hetzner/prod stack has never run on a real server; Caddyfile never validated by Caddy; memory limits are estimates (docs/12 "Not verified"). CI does not cover `docker-compose.prod.yml`.
- [V] No live-LLM evaluation (accuracy, hallucination, cost): tests use a scripted LLM (docs/11). The PR executor has only run against mocked GitHub.
- [V] No admin role, OIDC or per-user identity; viewer/approver/ingest are shared bearer tokens; prod dashboard is one shared basic-auth login.
- [V] No container-image vulnerability scan in CI; Next.js 15 carries a build-time PostCSS advisory (fix needs Next 16; CI gates at `critical` only).
- [V] OpsPilot self-telemetry is limited to JSON logs. Prod-environment confirmation for HIGH actions and automatic post-action monitoring are not built (docs/08).
- [H] Cloud sandbox had no Docker daemon, so several PRs were first exercised by CI.
- [Q] Local (non-cloud) run of `make lint` / `make test` on a developer machine has not been recorded since the migration; see T-001.

## Waiting on Gün (inputs only he can provide)
- Domain name (or decision to use IP-only Caddy for a first test).
- A Hetzner server (2 vCPU / 4 GB planned).
- Market OS repository URL (to co-host on the same VPS).

## Uncommitted / unpushed work
- [V] From the cloud session that wrote this PR: none other than this docs PR. The previous implementation session (cse_012xjU4DKxbg8sF8VMYGkofz) reported all work merged; its working tree could not be inspected from here [Q]. Its branch on origin equals `main`.

## Environment variable names (no values)
Core: `POSTGRES_USER/PASSWORD/DB`, `DATABASE_URL`, `REDIS_URL`, `OPSPILOT_ENV`, `OPSPILOT_LOG_LEVEL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `NEXT_PUBLIC_API_URL`, `TELEMETRY_RETENTION_DAYS`, `DETECTION_RECOVERY_MINUTES`.
Auth: `OPSPILOT_INGEST_TOKEN`, `OPSPILOT_VIEWER_TOKEN`, `OPSPILOT_APPROVER_TOKEN`.
AI: `OPSPILOT_INVESTIGATOR` (llm|rules|auto), `ANTHROPIC_API_KEY`, `LLM_MODEL`.
GitHub: `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_WRITE_TOKEN`, `OPSPILOT_ACTIONS_ENABLED`.
Host ports: `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `WEB_HOST_PORT`, `API_HOST_PORT`.
Prod only: `DASH_DOMAIN`, `API_DOMAIN`, `DASH_USER`, `DASH_PASSWORD_HASH`.
