# 11 — Evaluation and Known Gaps (Phase 10)

Status of every MVP criterion in [doc 09](09-mvp-acceptance-criteria.md), stated as what is actually verified and how.

## Acceptance scenarios

| # | Verified by | Notes |
|---|-------------|-------|
| A1 healthy baseline | `demo` CI job (`scripts/demo_check.sh`) and detector integration tests | Live stack, no incident while healthy |
| A2 bad deploy | `demo` and `kind-e2e` CI jobs | Real second image, real deployment event, incident linked to it |
| A3 investigation evidence | `test_verifier.py`, `test_investigation_live.py` | Verifier and evidence capture are real; the model is a **scripted LLM** in tests |
| A4 dependency failure | scripted-LLM test + verifier rule (DEPLOYMENT hypothesis needs DEPLOYMENT evidence) | Not measured against a live model |
| A5 insufficient data | verifier confidence caps (unit) | |
| A6 prompt injection | redaction + `untrusted_data` framing + no write tools (unit/integration) | Structural: the model has no action tool |
| A7 remediation | `test_actions_live.py`, `test_policy.py` | GitHub calls run against a mocked transport only |
| A8 recovery / MTTD / MTTR | detector integration tests, `demo` job | |
| A9 LLM outage | `test_investigation_live.py` | Incident still detected; investigation FAILED and retryable |

## Platform criteria

| Criterion | Result |
|-----------|--------|
| Ingest >= 1k log records/s, no loss | `tests/integration/test_ingest_load.py`: 10,000 records in 20 requests of 500. Measured locally at ~18k records/s in-process against a local Postgres, zero loss (row count asserted). CI enforces >= 1k/s. Single-node, in-process numbers: not a capacity claim for a networked deployment. |
| Live data only in dashboard | Playwright smoke + `demo_check.sh` incident-page assertion |
| Roles | `viewer` (optional read token), `approver`, ingest token, webhook HMAC; unit-tested in `test_rbac.py`. No `admin` role or OIDC: not built. |
| Actions disabled by default | `OPSPILOT_ACTIONS_ENABLED=false`, DB triggers, `test_actions_live.py` |
| Secrets | gitleaks in CI |
| Dependency scanning | `pip-audit` (backend + demo shop) and `npm audit --audit-level=critical`. Next 15 still reports a build-time PostCSS advisory (fix needs Next 16, a breaking upgrade); accepted, tracked. |
| Manifest scanning | Trivy config scan on the rendered kind overlay, HIGH/CRITICAL gate |
| Architecture boundaries | `import-linter` contracts in `backend/pyproject.toml`, run in CI |
| Kubernetes | `kind-e2e` runs the same failure scenario on kind |

## Rule-based investigator

Unit tests cover each rule (including that a dependency failure is not blamed on the deploy), `test_rule_based_investigator_needs_no_key` runs it end to end on a real database, and the `demo` CI job runs it against the live failure-injection stack and asserts the investigation completes. What it finds on the real bad-deploy telemetry is printed in that job's log, not asserted.

## Not measured / not done

- **Root-cause accuracy, hallucination rate, LLM cost per investigation**: no live-model evaluation has been run (no API key in CI). The golden failure set is the demo scenarios only.
- **OpsPilot self-telemetry** (traces/metrics of the platform itself) is limited to structured JSON logs.
- **Container image vulnerability scanning** is not in CI; only dependencies and manifests are scanned.
- **Dashboard is read-only**; approvals use the API.
- **No admin role, OIDC, or per-user viewer identities**: viewer/approver are shared bearer tokens.
