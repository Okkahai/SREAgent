# Task registry

Snapshot 2026-11-06. Statuses: `TODO`, `BLOCKED` (needs an input), `IN_PROGRESS`, `DONE`. Everything shipped before this date is listed in PROJECT_STATE.md and `git log`; only open work is tracked here. No task below has a branch or PR yet (verified: no open PRs, no extra remote branches except the merged-out thread branch).

Suggested order: T-001 -> T-002 -> T-003 -> T-004 -> T-005, with T-006..T-009 as hardening backlog.

---
## T-001 Verify CI parity on a local machine
- Status: TODO. Priority: P1. Blocker: none.
- Objective: confirm that a fresh clone passes locally what CI runs, and record the result in VERIFICATION.md.
- Acceptance: `make lint` and `INTEGRATION=1 make test` (with Postgres+Redis up) pass; `make demo-up && make demo-check` pass; web `npm ci && npm run build` pass. Any local-only failure documented or fixed.
- Branch/PR: none. Files: none expected (docs/agent/VERIFICATION.md update).
- Done: CI green on `main` d022124 (2026-11-04) [V]. Remaining: the local run itself.
- Tests outstanding: all of the above locally.
- Next action: clone to a worktree, `cp .env.example .env`, run the commands in VERIFICATION.md, paste outcomes into the "Local verification log".
- Confidence: high that it passes (CI is green), low evidence about local-only quirks (Windows ports, docker versions).

## T-002 Validate the Hetzner/prod deployment on a real server
- Status: BLOCKED (needs a Hetzner server; domain or IP-only test). Priority: P1.
- Objective: run `docker-compose.prod.yml` for real and confirm docs/12 steps work.
- Acceptance: stack healthy via `docker compose -f docker-compose.prod.yml ps`; HTTPS via Caddy on both hosts; dashboard basic-auth works; API host exposes only ingest/deployments/webhook/approval routes; demo or app telemetry arrives; `scripts/backup.sh` produces a dump that restores; `docker stats` shows memory within limits on 4 GB + 2 GB swap; docs/12 corrected and its "Not verified" section updated.
- Files: `docker-compose.prod.yml`, `deploy/caddy/Caddyfile`, `.env.prod.example`, `scripts/backup.sh`, `docs/12-deploy-hetzner.md`.
- Dependencies: Gün provides server and domain (or IP-only plan; Caddy cannot issue public certs for a bare IP, so expect plain HTTP or an internal CA in that mode [A]).
- Decisions in force: see DECISIONS.md D-010..D-016.
- Optional pre-work without a server: validate Caddyfile with `docker run caddy:2-alpine caddy validate`, and consider adding a CI job that runs `docker compose -f docker-compose.prod.yml config -q` with a dummy env file (not done).
- Next action: Gün creates the server; follow docs/12 and log every deviation.
- Confidence: medium. Compose passed `config` locally per PR #14; nothing else is proven.

## T-003 Co-host Market OS on the same VPS
- Status: BLOCKED (Market OS repo URL not provided). Priority: P2. Depends on T-002.
- Objective: run Market OS beside OpsPilot on the single 2 vCPU / 4 GB server.
- Acceptance: per-app Compose project with its own Postgres/Redis (D-011); shared Caddy routing both domains without port clashes; combined memory limits fit with 2 GB swap; OpsPilot receives Market OS telemetry (OTLP + `POST /v1/deployments`) as a second monitored service.
- Open questions [Q]: Market OS stack/language, its memory needs, whether it already speaks OTLP, who owns the shared Caddy.
- Next action: Gün supplies the repo URL; inspect it, then write a plan before changing anything.
- Confidence: low (nothing known about Market OS).

## T-004 Per-user identity (OIDC) and an admin role
- Status: TODO, deliberately deferred (D-016). Priority: P3.
- Objective: replace shared bearer tokens / basic-auth with OIDC-backed users and roles (`viewer`, `approver`, `admin`) as designed in docs/08.
- Acceptance: roles enforced server-side per route; approvals attributed to the authenticated user (not the `X-OpsPilot-Actor` header); tests in the style of `test_rbac.py`; docs/08 and docs/11 updated.
- Files (expected): `backend/src/opspilot/api/deps.py`, `api/actions.py`, config, web auth, `docs/08`.
- Next action: write a short design note first (provider choice, session handling in Next.js), get Gün's approval, then implement.
- Confidence: n/a (not started).

## T-005 Validate the LLM investigator with a real model
- Status: TODO. Priority: P1 (core claim of the product is untested live). Blocker: an `ANTHROPIC_API_KEY` that Gün chooses to provide, and a cost budget.
- Objective: measure root-cause accuracy, evidence validity, hallucination rate and cost per investigation on the demo failure set (bad deploy, db_timeout, memory_spike, payments down, http_500).
- Acceptance: a repeatable script/eval run, results recorded in docs/11 (replacing "not measured"), verifier behaviour confirmed on real model output (invented evidence dropped, deploy not blamed for a dependency outage).
- Dependencies: T-001 (working local stack). Files: `backend/src/opspilot/agent/*`, new eval script under `scripts/` or `backend/tests/`, `docs/11-evaluation.md`.
- Tests done: scripted-LLM tests only. Outstanding: all live-model tests.
- Next action: run the demo stack with `OPSPILOT_INVESTIGATOR=llm` and a key, trigger each fault, export investigations, grade by hand against known ground truth.
- Confidence: unknown by definition.

## T-006 Container image vulnerability scanning in CI
- Status: TODO. Priority: P3. Objective: scan built backend/web/demo images (e.g. Trivy image scan with the pinned release + checksum pattern already used). Acceptance: new CI step gates HIGH/CRITICAL (or documented allowlist); docs/11 updated. Files: `.github/workflows/ci.yml`. Next action: add job reusing the pinned Trivy install.

## T-007 OpsPilot self-telemetry
- Status: TODO. Priority: P3. Objective: emit OpsPilot's own traces/metrics (acceptance criterion in docs/09; today only JSON logs). Files: `backend/src/opspilot/telemetry.py`, collector config. Acceptance: API and worker spans visible in the collector; documented.

## T-008 Upgrade Next.js to 16 (clears build-time PostCSS advisory)
- Status: TODO. Priority: P4. Breaking upgrade; CI gates only at `critical` today. Acceptance: `npm audit --omit=dev` clean at moderate+ or documented; web build, lint, typecheck and Playwright e2e pass. Files: `web/package.json`, `web/package-lock.json`, `.github/workflows/ci.yml` comment.

## T-009 Exercise the PR executor against real GitHub
- Status: TODO. Priority: P2. Objective: run `integrations/github_write.py` once against a throwaway repo with a scoped write token. Acceptance: branch `opspilot/...` and a PR are created, nothing merged, audit rows written, kill switch off again afterwards. Blocker: Gün creates the throwaway repo and token. Files: none expected; update docs/11.

## T-010 Documentation drift cleanup
- Status: TODO. Priority: P4. Known drift [V]: `docs/03-repository-structure.md` shows `demo/{gateway,checkout,catalog,payments}` and `deploy/postgres/init.sql` but the repo has `demo/shop/` (one package) and no `deploy/postgres`; `docs/10-roadmap.md` still has a "Phase 1 breakdown (this PR)" section; docs/09 lists "OpsPilot emits its own traces/metrics" as a criterion that is unmet (T-007). Acceptance: docs match the tree. Docs-only PR.
