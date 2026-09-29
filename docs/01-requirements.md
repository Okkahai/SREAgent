# 01 — Requirements Analysis

OpsPilot answers one question: **what failed, why, what evidence supports that, and how should it be fixed?**

## 1. Goals and non-goals

**Goals**
- Turn a real failure into a structured, evidence-backed incident and a reviewed remediation proposal.
- Make every AI claim traceable to stored evidence (logs, metrics, traces, deployments, commits).
- Show real infrastructure engineering (containers, OTel, CI/CD, K8s), not just an LLM wrapper.
- Ship one end-to-end demo: inject failure → detect → investigate → root cause → proposed fix.

**Non-goals (MVP)**
- Multi-tenant SaaS, billing, SSO.
- Automatic execution of production actions (rollback/restart/scale/DB/merge). Proposals only.
- Supporting many demo apps or many cloud providers.
- Replacing Prometheus/Grafana/Tempo. OpsPilot ingests and correlates; it is not a general TSDB.

## 2. Functional requirements

| ID | Requirement | Phase |
|----|-------------|-------|
| FR-1 | Connect GitHub repos (read-only: commits, diffs, PRs, CODEOWNERS, workflow runs) | 6 |
| FR-2 | Monitor CI/CD runs and correlate to deployments | 6 |
| FR-3 | Record deployments (service, version, commit SHA, environment, time) via API/webhook | 3 |
| FR-4 | Ingest logs via OTLP | 3 |
| FR-5 | Ingest metrics via OTLP | 3 |
| FR-6 | Ingest traces via OTLP | 3 |
| FR-7 | Detect incidents with deterministic rules (error-rate, latency, saturation, deploy regression) | 4 |
| FR-8 | AI root-cause analysis producing structured output | 5 |
| FR-9 | Repository/code investigation (changed files, relevant functions, owners) | 5–6 |
| FR-10 | Suggested remediation (typed actions, risk-scored) | 7 |
| FR-11 | Incident timeline (chronological, source-attributed) | 4 |
| FR-12 | Incident history and outcome measurement | 4, 7 |
| FR-13 | Optional PR generation (branch + patch + tests, never auto-merged) | 7 |
| FR-14 | Human approval for every dangerous action, gated by deterministic policy | 7 |
| FR-15 | Dashboard: overview, incident detail, services, deployments | 8 |

## 3. Incident data contract

Every incident carries: `id`, `title`, `status`, `severity`, `started_at`, `detected_at`, `resolved_at`, affected service(s), deployment/version, related logs/metrics/traces, suspected root cause, confidence, evidence, suggested actions, executed actions, final outcome. See [04-database-schema.md](04-database-schema.md).

### Epistemic labels (hard requirement)
Every statement attached to an incident is exactly one of:
- **OBSERVATION** — raw or aggregated data as measured (e.g. "p95 latency 2.1s at 14:04"). Produced by deterministic code.
- **HYPOTHESIS** — an inference that references ≥1 observation and states what would confirm/refute it.
- **CONFIRMED_FACT** — a hypothesis validated by a deterministic check or human confirmation (e.g. "deployment 482 changed `pool_size` from 20 to 2", verified from the commit diff).

**Invariant:** a root cause cannot be stored with status above HYPOTHESIS unless it links to ≥1 evidence row; confidence is capped for hypotheses that lack corroborating independent signals. Enforced in code and DB constraints, not in the prompt alone.

## 4. Non-functional requirements

| Area | Requirement |
|------|-------------|
| Safety | No write access to production systems in MVP. Actions execute only after human approval and policy pass. |
| Explainability | Every conclusion links to evidence and to the agent tool-call trace that produced it. |
| Security | Secrets never reach the LLM; prompt-injection resistant (logs are untrusted data); least privilege tokens. |
| Observability | OpsPilot instruments itself with OTel (dogfooding); structured JSON logs with trace IDs. |
| Reliability | Ingestion is decoupled from analysis via queues; the platform degrades gracefully if the LLM is down (detection still works). |
| Performance | Ingest ≥ 1k log records/s locally; incident detection latency < 60 s from fault onset for the demo. |
| Portability | Everything runs with `docker compose up`; same images deploy to Kubernetes. |
| Testability | Unit, integration (real Postgres/Redis), and an end-to-end failure-injection test in CI. |
| Provider independence | SCM, CI, deploy and LLM providers behind interfaces. |

## 5. Assumptions and decisions

- **Ingestion protocol: OTLP** (gRPC/HTTP) through an OpenTelemetry Collector; the collector exports to OpsPilot's ingest API. Vendor-neutral, matches "design around OpenTelemetry".
- **Jobs: Celery + Redis.** Chosen for mature retries/scheduling (beat) and easy local ops. Alternative considered: arq/RQ (simpler, fewer features), Temporal (excellent for durable workflows, heavy for MVP). ADR-002 in architecture doc.
- **Storage:** PostgreSQL only for MVP (with JSONB and time-based partitioning) to keep the stack operable; a columnar store (ClickHouse) is a documented future swap behind a repository interface.
- **GitHub: read-only first** via a GitHub App / fine-grained PAT; PR creation is a later, separately-scoped write permission.
- **LLM:** provider-abstracted (Anthropic default). Agent is tool-using; tools are read-only.

## 6. Risks

| Risk | Mitigation |
|------|------------|
| LLM hallucinated root cause | Evidence-required schema, verifier step, confidence caps, human review |
| Prompt injection via log content | Untrusted-data framing, no write tools, output schema validation, size/redaction limits |
| Telemetry volume | Sampling, retention, partitioning, aggregation at ingest |
| Scope creep | Strict phase gates and MVP acceptance criteria (doc 09) |
| Fake-looking demo | Real failure injection and real telemetry; no seeded "intelligence" |
