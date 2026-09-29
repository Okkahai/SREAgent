# 02 — System Architecture

## 1. Context

```
                        ┌──────────────────────────┐
  Demo app (shop) ─OTLP─►  OpenTelemetry Collector │──OTLP/HTTP──┐
  (checkout, catalog,   └──────────────────────────┘             │
   payments, postgres)                                            ▼
                                                     ┌──────────────────────┐
  GitHub ──webhooks/REST──────────────────────────►  │   OpsPilot API       │
  CI provider ────────────────────────────────────►  │   (FastAPI)          │
  Deploy hook (curl in pipeline) ─────────────────►  └─────────┬────────────┘
                                                               │ enqueue
                                    ┌──────────────────────────┼─────────────────┐
                                    ▼                          ▼                 ▼
                            ┌──────────────┐          ┌───────────────┐  ┌───────────────┐
                            │ Detector     │          │ Investigator  │  │ Integrations  │
                            │ (Celery beat │          │ (Celery, AI   │  │ sync workers  │
                            │  + workers)  │          │  agent)       │  │ (GitHub, CI)  │
                            └──────┬───────┘          └──────┬────────┘  └──────┬────────┘
                                   └──────────┬──────────────┴──────────────────┘
                                              ▼
                                   ┌─────────────────────┐        ┌────────────────┐
                                   │ PostgreSQL          │        │ Redis          │
                                   │ (state + telemetry) │        │ (broker/cache) │
                                   └─────────────────────┘        └────────────────┘
                                              ▲
                                   ┌──────────┴───────────┐
                                   │ Next.js dashboard    │
                                   └──────────────────────┘
```

## 2. Components

| Component | Tech | Responsibility |
|-----------|------|----------------|
| `api` | FastAPI | REST API for dashboard, OTLP-derived ingest endpoints, webhooks, approval endpoints. Stateless. |
| `worker` | Celery | Detection evaluation, investigations, integration syncs, retention. |
| `beat` | Celery beat | Schedules detector evaluation and syncs. |
| `web` | Next.js + TS | Dashboard. Talks only to `api`. |
| `otel-collector` | OTel Collector contrib | Receives OTLP from apps, batches, enriches (resource attrs), forwards to `api` ingest. Also scrapes OpsPilot's own telemetry. |
| `postgres` | PostgreSQL 16 | System of record for incidents, deployments, and ingested telemetry (partitioned). |
| `redis` | Redis 7 | Celery broker/result backend, rate-limit counters, short-lived cache. |
| `demo-app` | Python services | Deliberately observable microservices with fault injection (Phase 2). |

### Layering inside the backend (hexagonal)

```
api (HTTP)  ─┐
workers     ─┼─► services (use cases) ─► domain (entities, policies) 
webhooks    ─┘            │
                          ├─► ports (interfaces): TelemetryStore, SCMProvider,
                          │        CIProvider, DeployProvider, LLMProvider, ActionExecutor
                          └─► adapters: postgres, github, anthropic, ...
```

Domain code has no I/O. Adapters implement ports. This is what makes "GitHub, CI providers and cloud platforms added independently" real.

## 3. Key flows

**Ingest:** app → OTLP → collector → `POST /v1/ingest/{logs,metrics,traces}` (authenticated by ingest token) → validate/normalize → batch insert. Metrics are stored as rolled-up series (per service/route/minute) plus raw points with short retention.

**Detect:** beat triggers `detector.evaluate` every 15 s → rules query aggregates → on breach opens/updates an incident (dedupe by service+rule fingerprint) and appends timeline events → enqueues `investigate(incident_id)`.

**Investigate:** worker runs the agent (doc 07). Agent uses read-only tools over the telemetry store and SCM provider; emits structured findings that are validated and persisted with evidence links.

**Remediate:** agent proposes typed `ActionProposal`s. Policy engine classifies risk. Anything mutating needs an approver; the approval is recorded, then an `ActionExecutor` (MVP: PR creation only; others are "manual runbook" outputs) runs it.

**Measure:** after an action, the detector keeps watching; the incident's `outcome` records whether the signal recovered and when.

## 4. Architectural decisions (ADR summary)

| # | Decision | Alternatives | Rationale |
|---|----------|--------------|-----------|
| 001 | Postgres-only store for MVP | ClickHouse, Loki/Tempo/Prometheus | One dependency, transactional joins between incidents and telemetry; behind `TelemetryStore` port for later swap |
| 002 | Celery + Redis | arq, Temporal | Retries, schedules, well-known; acceptable for MVP; investigation is idempotent so at-least-once is fine |
| 003 | OTLP via Collector | Custom agents | Standard, vendor-neutral, showcases OTel |
| 004 | Deterministic detection, AI investigation | AI-only detection | Detection must be cheap, testable, reliable; AI is for explanation |
| 005 | Read-only agent tools | Agent with shell/kubectl | Safety boundary is structural (no write tool exists) |
| 006 | Modular monolith (api+worker share a codebase) | Microservices | Fewer moving parts; module boundaries preserved for later split |
| 007 | Sync SQLAlchemy 2.0 + psycopg in workers, async in API | All async | Celery is sync-native; shared models |

## 5. Scalability & failure behavior

- API is stateless → horizontally scalable. Workers scale by queue (`detect`, `investigate`, `sync`).
- Ingestion uses batch inserts; backpressure via 429 + collector retry/queue.
- Redis loss: in-flight tasks retried on reconnect; DB is the truth. Postgres loss: API returns 503; collector buffers.
- LLM outage: incidents still open with observations and timeline; investigation status `FAILED`/retryable.

## 6. Deployment topology

- **Local:** `docker compose` (profiles: `core`, `demo`, `full`).
- **Kubernetes (Phase 9):** Helm chart or Kustomize; Deployments for api/worker/beat/web, StatefulSet/managed PG, NetworkPolicies, HPA on api/worker, OTel Collector as DaemonSet/Deployment.
