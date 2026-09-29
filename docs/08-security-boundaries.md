# 08 — Security Boundaries

## 1. Trust zones

```
[Untrusted]  monitored app telemetry, logs, commit messages, repo code, webhook payloads
     │  validated, size-capped, redacted, authenticated
[Semi-trusted] OTel Collector, CI/GitHub webhooks (signature-verified)
     │
[Trusted core] OpsPilot API, workers, Postgres, Redis   (private network)
     │  ─ read-only tools only ─►  [LLM provider]  (external; receives redacted data)
     │
[Privileged, gated] Action executors (MVP: GitHub PR creation only) — need approval + policy pass
```

## 2. Read-only by default
- GitHub: GitHub App with `contents:read`, `metadata:read`, `pull_requests:read`, `actions:read`, `deployments:read`. Write scopes (`pull_requests:write`, `contents:write` on a branch namespace `opspilot/*`) are added only in Phase 7 and only to the executor's credentials.
- No kubectl/cloud credentials in MVP. Rollback/restart/scale are emitted as **runbook proposals** for a human to execute.
- The investigator process has no credentials for executors (separate settings and task queue).

## 3. Dangerous actions: policy + approval

Deterministic policy engine (pure functions, table-driven, unit-tested):

| Action type | Risk | Rule |
|-------------|------|------|
| Read/query | READ_ONLY | allowed |
| OPEN_PR (branch + PR, no merge) | LOW | needs approval in MVP |
| ROLLBACK / RESTART / SCALE / CONFIG_CHANGE | HIGH | approval required; prod requires explicit environment confirmation; never auto |
| DB operations, infra changes, MERGE_PR | DESTRUCTIVE | **not executable by OpsPilot in MVP**; runbook text only |

Additional guards: proposals expire (default 1 h); approver ≠ nothing-else (must be an authenticated user with `approver` role); approval is bound to the exact proposal payload hash (changed parameters invalidate it); execution row requires an approval FK; every step appended to `audit_log`; kill-switch env var `OPSPILOT_ACTIONS_ENABLED=false` (default false).

## 4. Authentication and authorization
- Dashboard/API: OIDC-ready; MVP uses a single admin API token / local session with role claims (`viewer`, `approver`, `admin`). Roles enforced server-side per route.
- Ingest: per-environment bearer tokens (hashed at rest), rate-limited.
- Webhooks: HMAC signature verification (GitHub `X-Hub-Signature-256`), replay window.
- Service-to-service inside compose/K8s: private network, no published DB/Redis ports outside dev.

## 5. Secrets
- Env vars / Docker/K8s secrets; `.env` git-ignored; `.env.example` has placeholders only.
- CI runs secret scanning (gitleaks) and dependency audit.
- Secrets never in logs, evidence, prompts. Ingest-time redaction (tokens, `Authorization`, emails, key patterns) plus a second redaction before any LLM call.

## 6. LLM-specific threats
| Threat | Control |
|--------|---------|
| Prompt injection from logs/code | Data-block framing, read-only tools, schema validation, verifier |
| Data exfiltration to provider | Redaction, allow-list of fields, no raw secrets available to tools |
| Tool abuse | Tool allow-list, argument validation, per-investigation budgets |
| Hallucinated evidence | Server-side evidence capture; ids verified |
| Cost/DoS | Token & call budgets, per-incident investigation cap, queue rate limits |

## 7. Application security
- Input validation via Pydantic; parameterized SQL only; output encoding in UI; CORS allow-list; security headers on web; request size limits.
- Containers: non-root user, read-only root FS where possible, pinned base images, minimal images, health checks, dropped capabilities (K8s `securityContext`).
- K8s (Phase 9): NetworkPolicies default-deny, ServiceAccount per component, resource limits, Secrets not ConfigMaps.
- Supply chain: pinned/locked dependencies, Dependabot, image scanning (Trivy) in CI (Phase 10).

## 8. Audit
`audit_log` (append-only) records approvals, executions, config changes, token creation, policy overrides. Agent tool calls are stored in `agent_steps`.

## 9. Threat-model summary (STRIDE highlights)
- **Spoofing:** forged webhooks/ingest → signatures, tokens.
- **Tampering:** altered evidence → server-side capture, immutable timeline.
- **Repudiation:** who approved → approvals + audit log.
- **Info disclosure:** secrets in telemetry → redaction; least-privilege tokens.
- **DoS:** telemetry flood → rate limiting, collector limiter, partition/retention.
- **Elevation:** LLM triggers action → structurally impossible (no write tools; executor gated).

## Phase 7 implementation notes
- Policy: `domain/policy.py`. Risk comes only from the table; unknown types are DESTRUCTIVE and refused. `OPEN_PR` files are validated (max 5 files, 20 KB each, no `.github/`, CODEOWNERS, `.env`, path traversal). The target repository is never taken from model output.
- Approval binds to `payload_hash` (sha256 of incident, type, parameters); a changed payload cannot be executed on an old approval. A database trigger refuses `action_executions` rows without a matching APPROVE, and `audit_log` rejects UPDATE/DELETE.
- Roles: a single `approver` bearer token plus a required `X-OpsPilot-Actor` name (recorded in approvals and audit). Viewer/admin roles and OIDC arrive with Phase 10.
- Executor: `integrations/github_write.py` only lists/creates refs, contents and PRs under `opspilot/`; there is no merge, delete or force-push call. It uses `GITHUB_WRITE_TOKEN`, separate from the investigator's read-only token. Kill switch `OPSPILOT_ACTIONS_ENABLED` defaults to false.
- Not done: prod environment confirmation (no HIGH action is executable yet), automatic post-action monitoring transitions (a PR fixes nothing until a human merges it).
