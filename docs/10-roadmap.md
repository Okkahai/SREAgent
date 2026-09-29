# 10 — Implementation Roadmap

Each phase is a small series of PRs. Exit criteria must be demonstrable.

| Phase | Scope | Exit criteria |
|-------|-------|---------------|
| **1. Architecture + local env** | Design docs; repo skeleton; docker-compose (Postgres, Redis, OTel Collector, API, worker, web); FastAPI health/readiness; Next.js skeleton; Makefile; CI | `make up` healthy; `/healthz` & `/readyz` pass (DB+Redis checked); CI green; collector receives OTLP |
| **2. Demo app + observability** (done) | Instrumented microservices, load generator, fault injection, Postgres for demo, Collector pipelines, versioned "bad deploy" | Each fault visibly changes telemetry (debug exporter / logs) |
| **3. Ingestion** (done) | Alembic + core tables; OTLP/HTTP ingest; deployments API; rollups; retention | Demo telemetry queryable in Postgres with service/version/trace correlation |
| **4. Incident detection** (done) | Rules engine, beat scheduler, incident state machine, timeline, dedupe/reopen | A2 scenario opens/resolves incidents; A1 no false positives |
| **5. AI investigation** | Agent runtime, read-only tools, evidence capture, verifier, confidence caps, output schema, LLM port | A3, A4, A5, A6, A9 pass |
| **6. GitHub integration** | GitHub App (read-only), commit/diff/CODEOWNERS sync, deployment→commit mapping, webhooks, CI run tracking | Incident shows suspect commit with owners and changed files |
| **7. Suggested fixes** | Remediation planner, policy engine, approvals, PR executor (write scope), runbooks | A7, A8 pass |
| **8. Dashboard** | Overview, incident detail (timeline/evidence/logs/metrics/traces), services, deployments; live data | All views driven by API; e2e Playwright smoke |
| **9. Docker/K8s** | Production Dockerfiles, Helm/Kustomize, kind in CI, NetworkPolicies, HPA, OTel collector deployment | Same scenario runs on kind |
| **10. Testing + hardening** | Load test, e2e failure-injection suite in CI, security scanning (gitleaks, Trivy, pip-audit), import-linter, RBAC hardening, docs polish, eval report | All MVP criteria (doc 09) met |

## Phase 1 breakdown (this PR)
1. Design docs 01–10 + README.
2. Backend skeleton: settings, JSON logging, OTel init, `/healthz`, `/readyz`, Celery app with a heartbeat task, tests.
3. Web skeleton: Next.js + TS app that calls the API health endpoint (shows real status).
4. Compose stack: postgres, redis, otel-collector, api, worker, web with health checks.
5. Makefile, `.env.example`, `.gitignore`.
6. CI: backend lint+tests (with Postgres/Redis services), web lint/typecheck/build, compose config validation, gitleaks.

## Risks to schedule around
- Phase 3 storage design (partitions, rollups) is the hardest to change later → prototype early with realistic volume.
- Phase 5 quality depends on Phase 2 fault realism → invest in believable failures.
- Phase 7 write scopes → separate GitHub App credentials and review before enabling.
