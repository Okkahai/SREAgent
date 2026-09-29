# 03 — Repository Structure

Monorepo. Each deployable has its own Dockerfile; shared config lives at the root.

```
SREAgent/
├── README.md
├── Makefile                     # dev entrypoints (make up, test, lint, ...)
├── docker-compose.yml           # core stack (+ demo profile from Phase 2)
├── .env.example
├── .github/workflows/ci.yml
├── docs/                        # design docs (this folder), ADRs
├── backend/                     # OpsPilot API + workers (Python 3.11, FastAPI)
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── migrations/              # Alembic (Phase 3+)
│   ├── src/opspilot/
│   │   ├── main.py              # FastAPI app factory
│   │   ├── config.py            # pydantic-settings
│   │   ├── logging.py           # structured JSON logging
│   │   ├── telemetry.py         # OTel self-instrumentation
│   │   ├── api/                 # routers, deps, schemas (HTTP layer)
│   │   ├── domain/              # entities, enums, policies (no I/O)
│   │   ├── services/            # use cases (detection, investigation, ...)
│   │   ├── ports/               # interfaces (TelemetryStore, SCMProvider, LLMProvider, ...)
│   │   ├── adapters/            # postgres/, github/, llm/, ...
│   │   ├── agent/               # investigator: tools, prompts, output schema, verifier
│   │   ├── workers/             # Celery app + tasks
│   │   └── db/                  # SQLAlchemy models, session
│   └── tests/                   # unit/, integration/, e2e/
├── web/                         # Next.js (App Router) + TypeScript dashboard
│   ├── package.json
│   ├── Dockerfile
│   └── src/app/...
├── demo/                        # Phase 2: deliberately observable microservices
│   ├── gateway/  checkout/  catalog/  payments/
│   └── faults/                  # fault-injection controller & scenarios
├── deploy/
│   ├── otel/collector.yaml
│   ├── postgres/init.sql
│   └── k8s/                     # Phase 9 (Kustomize/Helm)
└── scripts/                     # helper scripts (failure injection, smoke tests)
```

## Conventions

- **Python:** ruff (lint+format), mypy (strict on `domain/` and `services/`), pytest; src layout; `uv`-free plain pip/pyproject for CI simplicity.
- **TypeScript:** strict mode, ESLint (next), no `any` in API-client layer.
- **Boundaries enforced:** `domain` imports nothing from `adapters`/`api`; checked with an import-linter rule (Phase 10).
- **Migrations:** Alembic only; no `create_all` outside tests.
- **Commits/PRs:** small, phase-scoped PRs; docs updated with the code that changes them.
- **Config:** 12-factor env vars; `.env.example` documents all; no secrets in repo.
