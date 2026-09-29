# OpsPilot

AI-powered DevOps/SRE platform: **failure → observability data → incident → root-cause analysis → code context → AI investigation → proposed fix → human approval → optional PR → measured result.**

The central question: *what failed, why, what evidence supports that, and how should it be fixed?*

Design principles: deterministic detection, evidence-backed AI (every claim is labelled OBSERVATION / HYPOTHESIS / CONFIRMED_FACT), read-only integrations first, human approval for anything dangerous, OpenTelemetry throughout.

## Status

| Phase | State |
|-------|-------|
| Design docs (10 deliverables) | done, see [docs/](docs/) |
| 1. Architecture + local environment | done (this repo skeleton) |
| 2–10 | see [roadmap](docs/10-roadmap.md) |

## Quickstart

```bash
make up        # postgres, redis, otel-collector, api, worker, beat, web
make smoke     # health checks
```

- API: http://localhost:8000 (`/healthz`, `/readyz`, `/docs`)
- Web: http://localhost:3000
- OTLP: `localhost:4317` (gRPC), `localhost:4318` (HTTP)

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
