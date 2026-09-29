# OpsPilot

AI-powered DevOps/SRE platform: **failure → observability data → incident → root-cause analysis → code context → AI investigation → proposed fix → human approval → optional PR → measured result.**

The central question: *what failed, why, what evidence supports that, and how should it be fixed?*

Design principles: deterministic detection, evidence-backed AI (every claim is labelled OBSERVATION / HYPOTHESIS / CONFIRMED_FACT), read-only integrations first, human approval for anything dangerous, OpenTelemetry throughout.

## Status

| Phase | State |
|-------|-------|
| Design docs (10 deliverables) | done, see [docs/](docs/) |
| 1. Architecture + local environment | done |
| 2. Demo app + observability | done, see below |
| 3. Ingestion | done, see below |
| 4. Incident detection | done, see below |
| 5. AI investigation | done, see below |
| 6. GitHub integration (read-only) | done, see below |
| 7. Suggested fixes, policy, approvals | done, see below |
| 8. Dashboard | done, see below |
| 9. Docker / Kubernetes | done, see below |
| 10 | see [roadmap](docs/10-roadmap.md) |

## Quickstart

```bash
make up        # postgres, redis, otel-collector, api, worker, beat, web
make smoke     # health checks
```

- API: http://localhost:8000 (`/healthz`, `/readyz`, `/docs`)
- Web: http://localhost:3000
- OTLP: `localhost:4317` (gRPC), `localhost:4318` (HTTP)

## Demo application (Phase 2)

```bash
make demo-up                                   # gateway, checkout, payments, shop-db, load generator
make demo-telemetry                            # traces/metrics/logs arriving at the OTel collector
scripts/fault.sh payments set down             # dependency failure
scripts/fault.sh checkout set http_500 '{"rate":0.5}'
scripts/fault.sh checkout set db_timeout
scripts/fault.sh checkout set memory_spike '{"mb":300}'
scripts/fault.sh checkout clear                # revert
scripts/deploy.sh bad                          # real redeploy: v1.1.0, DB pool 20 -> 2
scripts/deploy.sh good                         # roll back to v1.0.0
make demo-check                                # automated end-to-end failure-injection check
```

Every failure changes real behaviour (errors, latency, saturation), so the resulting telemetry is genuine. Services emit OTLP traces, metrics and logs with `service.name`, `service.version`, `deployment.environment.name` and `vcs.ref.head.revision`, and logs carry `trace_id`/`span_id`. Details: [demo/README.md](demo/README.md).

## Ingestion (Phase 3)

The collector forwards OTLP to the API, which stores it in Postgres (daily-partitioned tables, 7-day retention) with service, version, commit and trace correlation:

```bash
curl localhost:8000/v1/services            # per-service RED metrics (last 5 min) + latest deployment
curl localhost:8000/v1/deployments         # deployment history (scripts/deploy.sh records these)
curl localhost:8000/v1/telemetry/stats     # rows ingested per signal
```

Writes (`/v1/otlp/v1/{traces,logs,metrics}`, `POST /v1/deployments`) need `Authorization: Bearer $OPSPILOT_INGEST_TOKEN`. Ingest accepts OTLP/HTTP protobuf (gzip supported). Migrations run with `alembic upgrade head` when the API container starts.

## Incident detection (Phase 4)

A Celery task evaluates deterministic rules every 15 s (error rate, p95 latency, DB pool saturation) and drives the incident lifecycle: DETECTED → MONITORING → RESOLVED, with dedupe, reopen, deployment correlation, a timeline and OBSERVATION evidence.

```bash
curl 'localhost:8000/v1/incidents?open_only=true'
curl localhost:8000/v1/incidents/INC-0001     # timeline + evidence
```

Rules and thresholds: `backend/src/opspilot/services/detection.py`; lifecycle: `domain/incident.py` and [docs/05](docs/05-incident-lifecycle.md). No AI is involved in detection; investigation (Phase 5) starts from these incidents.

Development: `make test`, `make lint`, `make fmt`. Backend needs Python 3.11 (`pip install -e 'backend[dev]'`), web needs Node 22 (`npm ci` in `web/`).

## AI investigation (Phase 5)

Every incident without an investigation is claimed by the `investigate_pending` beat task and run by a worker: a bounded loop of **read-only** tools (error rate, pool saturation, error logs, error spans, errors by version, recent deployments). Each tool result is stored server-side as OBSERVATION evidence; the model can only cite evidence ids. A deterministic verifier drops unsupported hypotheses, caps confidence by evidence quantity and signal diversity, and never allows `CONFIRMED_FACT`. Findings appear in `GET /v1/incidents/{id}` (`investigations`, hypothesis evidence, timeline).

Set `ANTHROPIC_API_KEY` (and optionally `LLM_MODEL`) in `.env`. Without a key, or if the provider is down, the investigation is recorded as `FAILED` (retried up to 3 times) and detection is unaffected. Details: [docs/07](docs/07-ai-agent-responsibilities.md).

## GitHub integration (Phase 6, read-only)

Set `GITHUB_TOKEN` (fine-grained, read-only: Contents, Metadata, Actions) and `GITHUB_REPO=owner/name` (a deployment may override with `metadata.repository`). The `commit_changes` investigation tool then fetches the deployed commit's changed files, diff excerpts and CODEOWNERS owners, caches them in `commits`, and records them as COMMIT evidence; `GET /v1/incidents/{id}` shows the suspect `commit` and `ci_runs`. Without a token the tool reports itself unavailable and the agent may not claim a code cause. `POST /v1/webhooks/github` (HMAC-verified, needs `GITHUB_WEBHOOK_SECRET`) records `workflow_run` events. The client issues GET requests only.

## Suggested fixes and approvals (Phase 7)

After a verified hypothesis the agent may recommend actions. A deterministic policy table (`domain/policy.py`) assigns risk: `OPEN_PR` is LOW and the only thing OpsPilot can execute; `ROLLBACK`/`RESTART`/`SCALE`/`CONFIG_CHANGE` are HIGH runbooks a human performs; `MERGE_PR`, DB and infra changes are refused. Proposals expire after `PROPOSAL_TTL_MINUTES` (60).

```bash
curl -H "Authorization: Bearer $OPSPILOT_APPROVER_TOKEN" -H "X-OpsPilot-Actor: you" -H 'content-type: application/json' \
  -d '{"decision":"APPROVE","payload_hash":"<hash from GET /v1/incidents/INC-0001/proposals>"}' \
  localhost:8000/v1/proposals/<id>/decision
curl -X POST -H "Authorization: Bearer $OPSPILOT_APPROVER_TOKEN" -H "X-OpsPilot-Actor: you" localhost:8000/v1/proposals/<id>/execute
```

Execution needs an approval bound to the exact payload hash, `OPSPILOT_ACTIONS_ENABLED=true` and `GITHUB_WRITE_TOKEN`; it creates an `opspilot/...` branch and a pull request and never merges. Every step lands in the append-only `audit_log`.

## Dashboard (Phase 8)

`http://localhost:3000`: overview (open incidents, ingest health, recent deployments), incidents, incident detail (timeline, investigation with hypotheses linked to their evidence, suspect commit and CI runs, proposed actions with policy risk, evidence with the captured query), services (RED metrics) and deployments. Every value comes from the API; with no data the pages show empty states. Pages refresh every 10 s. The dashboard is read-only: approvals go through the API. CI runs a Playwright smoke test (`npm run e2e` in `web/`, needs the stack running) and `make demo-check` asserts the incident page renders a real incident.

## Kubernetes (Phase 9)

`make kind-up kind-check kind-down` builds the images, deploys OpsPilot plus the demo shop to a kind cluster with Kustomize (`deploy/k8s`, see its README) and runs the same failure-injection scenario as `make demo-check`: faults, incident detection, bad deployment linked to version 1.1.0, rollback, recovery. CI runs it on every PR (`kind-e2e`) and validates the rendered manifests (`k8s-manifests`).

## Docs

1. [Requirements](docs/01-requirements.md)
2. [Architecture](docs/02-architecture.md)
3. [Repository structure](docs/03-repository-structure.md)
4. [Database schema](docs/04-database-schema.md)
5. [Incident lifecycle](docs/05-incident-lifecycle.md)
6. [Observability architecture](docs/06-observability-architecture.md)
7. [AI agent responsibilities](docs/07-ai-agent-responsibilities.md)
8. [Security boundaries](docs/08-security-boundaries.md)
9. [MVP acceptance criteria](docs/09-mvp-acceptance-criteria.md)
10. [Roadmap](docs/10-roadmap.md)
