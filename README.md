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
| 5–10 | see [roadmap](docs/10-roadmap.md) |

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
