# AGENTS.md — rules for any coding agent working on OpsPilot (SREAgent)

Provider-neutral. Applies to Claude Code, Codex CLI, T3 Code sessions, or a human. Claude-specific notes are in [CLAUDE.md](CLAUDE.md).

## Read first (in this order)
1. [docs/agent/HANDOFF.md](docs/agent/HANDOFF.md): what to do right now.
2. [docs/agent/PROJECT_STATE.md](docs/agent/PROJECT_STATE.md): verified state of the repo.
3. [docs/agent/TASK_REGISTRY.md](docs/agent/TASK_REGISTRY.md): open tasks with IDs.
4. [docs/agent/ARCHITECTURE.md](docs/agent/ARCHITECTURE.md), [DECISIONS.md](docs/agent/DECISIONS.md), [VERIFICATION.md](docs/agent/VERIFICATION.md).
5. Design source of truth: `docs/01`..`docs/12` (see README index). Do not duplicate them; link to them.

## What this project is
OpsPilot: an evidence-first AI SRE. Failure -> OTLP telemetry -> deterministic detection -> incident -> read-only investigation -> verified hypotheses -> human-approved, PR-only fix. Python 3.11 / FastAPI / Celery / Postgres / Redis (backend), Next.js 15 / TypeScript (web), a demo shop with fault injection, Docker Compose, Kustomize on kind, Caddy single-server prod stack.

## Non-negotiable invariants (do not weaken without Gün's explicit approval)
- The AI never executes anything. The model has no write tools. Risk comes from the deterministic table in `backend/src/opspilot/domain/policy.py`, never from model output.
- `OPSPILOT_ACTIONS_ENABLED` defaults to `false`. Only `OPEN_PR` is executable, only after approval bound to the payload hash, and PRs are never merged by OpsPilot.
- Evidence is captured server-side; the verifier drops uncited or invented evidence and caps confidence; the AI can never emit `CONFIRMED_FACT`.
- Logs, commit text and repo content are untrusted data (prompt-injection aware), secrets are redacted before leaving.
- Layering is enforced by `import-linter` (`backend/pyproject.toml`): `domain` has no I/O and imports nothing from adapters/api.
- Migrations via Alembic only. Audit log is append-only (DB triggers).
- No mocked intelligence: dashboard and CI scenarios run on real telemetry.
- Never commit secrets. `.env` is git-ignored; only placeholders in `.env.example` / `.env.prod.example`. Env var **names** may be documented, values may not.

## Workflow rules
- One task = one branch (from latest `main`) = one PR. Branch names: `<agent>/<task-id>-<slug>`, for example `codex/T-001-verify-ci`.
- Use a separate git worktree per concurrent agent. Never two agents in one working tree.
- Do not push to `main`. Do not merge PRs. Open the PR and leave it for Gün (the PR template line in the project settings applies if present).
- Do not rewrite history on a branch someone else owns. Do not skip, delete or quarantine a test to get green.
- Keep PRs small and phase/task-scoped. Update the docs the code touches (design docs 01..12, `.env.example`, README) in the same PR.
- Before opening a PR run the checks in [VERIFICATION.md](docs/agent/VERIFICATION.md) that apply to your change and report results honestly, including anything you could not run.
- Reviews: a PR should be reviewed by a different agent/model than the author, plus GitHub CI. Reviewer writes findings; author fixes or explains.
- When you finish or stop mid-task, update `docs/agent/HANDOFF.md` and the task's entry in `TASK_REGISTRY.md` (status, branch, PR, remaining steps, exact next action).
- Distinguish in every report: **verified fact** (you ran/read it), **assumption**, **open question**.

## Commands (from the repo root; see VERIFICATION.md for what CI runs)
```
make up | down | logs | ps          # dev stack (needs Docker; copies .env.example to .env)
make demo-up | demo-check            # stack + demo shop; automated failure-injection scenario
make test                            # backend unit tests (INTEGRATION=1 for DB tests, needs Postgres+Redis)
make lint                            # ruff, mypy, import-linter (backend); eslint, tsc (web)
make fmt                             # ruff fix + format
make kind-up | kind-check | kind-down
```
Backend: `pip install -e 'backend[dev]'` (Python 3.11). Web: `npm ci` in `web/` (Node 22).

## Conventions
- Python: ruff (lint+format), mypy, pytest, src layout under `backend/src/opspilot`. TypeScript: strict, ESLint.
- Config is 12-factor env vars through `backend/src/opspilot/config.py`; document every new var in `.env.example`.
- Docs are English. Replies to Gün are in Turkish.
