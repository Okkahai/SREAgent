# Architecture (agent-oriented summary)

Authoritative detail lives in [docs/02](../02-architecture.md), [03](../03-repository-structure.md), [04](../04-database-schema.md), [05](../05-incident-lifecycle.md), [06](../06-observability-architecture.md), [07](../07-ai-agent-responsibilities.md), [08](../08-security-boundaries.md). This page is a map; if it disagrees with the code, the code wins, then fix this page.

## Runtime topology
```
demo shop / any app --OTLP--> otel-collector (dev) --> OpsPilot API --> Postgres (partitioned telemetry + state)
                                                         |  ^
GitHub webhooks / REST (read) ---------------------------+  |
                                          Celery worker + beat <--> Redis
                                          (detector every 15 s, rollups, investigations, partitions)
Next.js dashboard (read-only, server-side fetch) --> API
```
Prod (single VPS): Caddy (80/443 only) -> web (basic auth) and API (public routes limited to ingest, deployments, webhook, approvals); apps send OTLP/HTTP straight to the API with the ingest token.

## Backend layers (`backend/src/opspilot`, enforced by import-linter)
`api` / `workers` -> `services` (use cases) -> `domain` (pure: incident state machine, policy). `ports` (e.g. `TelemetryStore`) implemented by `adapters` (Postgres). `agent` holds the investigator: LLM port + Anthropic adapter, read-only `tools`, `runner`, `verifier`, rule-based `heuristic`. `integrations` holds GitHub read client, CODEOWNERS parser and the PR-only writer.

## Key flows
- Ingest: OTLP/HTTP protobuf (gzip, size-bounded, bearer token) -> daily partitions (`log_records`, `spans`, `metric_points`) + 1-minute rollups; retention via `TELEMETRY_RETENTION_DAYS`.
- Detect: rules on error rate, p95 latency, DB pool saturation; dedupe by fingerprint; baseline = capped median; NO_DATA never opens/resolves. Lifecycle: detected -> investigating -> identified -> mitigating -> monitoring -> resolved -> closed (MTTD/MTTR recorded).
- Investigate: bounded loop of read-only tools; results stored as OBSERVATION evidence; verifier drops unknown evidence ids, requires deployment evidence for deploy hypotheses and a commit diff for code/config causes, caps confidence, never allows CONFIRMED_FACT. Failures are `FAILED` and retried up to 3 times; detection is unaffected.
- Remediate: policy table assigns risk; `OPEN_PR` only; approve by payload hash with approver token and `X-OpsPilot-Actor`; execute needs kill switch on and `GITHUB_WRITE_TOKEN`; branch `opspilot/*`, PR, no merge.

## Repository map
`backend/` API, workers, migrations 0001-0005, tests (`unit/`, `integration/`). `web/` Next.js app and Playwright e2e. `demo/shop/` gateway, checkout, payments, fault registry, load generator. `deploy/` otel collector, Kustomize (`base`, `demo`, `overlays/kind`), Caddy. `scripts/` `fault.sh`, `deploy.sh`, `demo_check.sh`, `kind.sh`, `backup.sh`. Compose: `docker-compose.yml` (dev, `demo` profile), `docker-compose.prod.yml`.

## Security posture in one paragraph
Read-only first; kill switch off by default; shared bearer tokens (ingest, viewer optional, approver) and HMAC-verified webhooks; K8s restricted Pod Security with default-deny NetworkPolicies; prod containers have memory limits and only Caddy publishes ports. Details and gaps: docs/08, docs/11.
