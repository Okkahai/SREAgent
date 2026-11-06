# Verification

What "done" means and what has actually been run. Update the log below whenever you verify something.

## What CI runs (`.github/workflows/ci.yml`, on push to `main` and every PR)
| Job | What it checks |
|-----|----------------|
| backend | ruff check, ruff format --check, mypy, lint-imports, pytest with `INTEGRATION=1` against real Postgres 16 and Redis 7 (Python 3.11) |
| web | `npm ci`, lint, typecheck, build (Node 22) |
| compose | `docker compose config -q`, bring up the stack, curl `/healthz`, `/readyz`, web |
| web-e2e | Playwright against api + web + Postgres + Redis |
| k8s-manifests | Kustomize render of `overlays/kind` + kubeconform `-strict` |
| kind-e2e | build images, deploy to kind, run the failure-injection scenario (`scripts/kind.sh check`) |
| demo | stack with `demo` profile, `scripts/demo_check.sh` (healthy, faults, bad deploy, recovery, telemetry, rule-based investigation) |
| demo-unit | demo shop ruff + pytest |
| security | pip-audit, `npm audit --omit=dev --audit-level=critical`, Trivy config scan of rendered manifests (HIGH/CRITICAL) |
| secrets-scan | gitleaks |

Not covered by CI: `docker-compose.prod.yml`, `deploy/caddy/Caddyfile`, `scripts/backup.sh`, live LLM, real GitHub writes, container image CVEs.

## Local commands that mirror CI
```
cp .env.example .env
pip install -e 'backend[dev]'                      # Python 3.11
make lint                                          # ruff, mypy, lint-imports, eslint, tsc
docker compose up -d postgres redis                # for integration tests
INTEGRATION=1 DATABASE_URL=postgresql+psycopg://opspilot:opspilot_dev_password@localhost:5432/opspilot \
  REDIS_URL=redis://localhost:6379/0 make test
(cd web && npm ci && npm run build)
(cd demo/shop && pip install -e '.[dev]' && ruff check . && ruff format --check . && pytest -q)
make demo-up && make demo-check                    # needs Docker; DETECTION_RECOVERY_MINUTES=1 speeds recovery
make kind-up && make kind-check && make kind-down  # needs kind, kubectl, Docker
docker compose -f docker-compose.prod.yml --env-file .env config -q   # prod file syntax (needs prod env values)
```
Port clash? Set `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `WEB_HOST_PORT`, `API_HOST_PORT` in `.env`.

## Verification ledger
| Date | What | Result | Evidence |
|------|------|--------|----------|
| 2026-11-04 | Full CI on `main` @ d022124 | success (all 10 jobs) | Actions run #40, https://github.com/Okkahai/SREAgent/actions/runs/41757992234 |
| 2026-11-06 | Repo state read for migration (git log, PR list, workflows, docs) | consistent with PROJECT_STATE.md | this PR |
| 2026-11-06 | Cloud sandbox: Docker daemon | unavailable; compose, demo, kind, prod stack not runnable there | session note |

## Local verification log (append below)
<!-- Date, machine/OS, command, result, notes. T-001 results go here. -->
