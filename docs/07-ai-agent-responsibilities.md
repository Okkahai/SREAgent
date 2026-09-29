# 07 — AI Agent Responsibilities

Principle: **deterministic code detects, measures and enforces; the LLM investigates, correlates and explains.** The LLM never decides what is allowed to happen.

## 1. What the AI does / does not do

| Does | Does not |
|------|----------|
| Plan an investigation and call read-only tools | Detect incidents or assign risk levels |
| Correlate telemetry, deployments, commits | Execute any action |
| Form hypotheses with stated confirm/refute checks | Assert facts without evidence |
| Read code (diffs, files) around suspect changes | Access secrets, prod credentials, shells, kubectl |
| Draft remediation proposals and patch text | Approve, merge, roll back, restart, scale |
| Explain findings in plain language | Override severity silently |

## 2. Agents (one runtime, distinct roles)

1. **Investigator** — main loop. Input: incident + initial observations. Output: structured `InvestigationResult`.
2. **Verifier** — second pass (separate prompt, ideally separate call). Checks each claimed evidence item resolves to a real DB row, quotes match, timestamps are consistent, and confidence is justified. Downgrades or rejects unsupported claims. Deterministic checks run first; LLM critique second.
3. **Remediation planner** (Phase 7) — turns the accepted root cause into typed `ActionProposal`s and, optionally, a patch. Risk is then assigned by the policy engine.

## 3. Read-only tool set (Investigator)

| Tool | Returns |
|------|---------|
| `get_incident_context` | incident, timeline, current observations |
| `query_metrics(service, metric, window, group_by)` | rolled-up series |
| `compare_windows(service, metric, before, after)` | delta stats |
| `search_logs(service, window, level, text, fingerprint)` | grouped log patterns + samples (capped, redacted) |
| `find_traces(service, route, window, status)` / `get_trace(id)` | slow/error traces, critical path |
| `list_deployments(service, window)` | deployments with version/commit |
| `get_commit_range(from_sha, to_sha)` / `get_commit_diff(sha)` | changed files, patches (size-capped) |
| `read_file(repo, ref, path, range)` / `search_code(query)` | source snippets |
| `get_owners(path)` | CODEOWNERS |
| `record_evidence(...)` | writes an evidence row referencing the query just run |

No tool mutates external systems. `record_evidence` only writes to OpsPilot's own DB and re-runs the referenced query server-side to snapshot the result (the model cannot fabricate evidence content).

## 4. Output contract

```json
{
  "severity": "HIGH",
  "affected_service": "checkout-api",
  "root_cause": {
    "statement": "DB pool size reduced from 20 to 2 in commit 3fa9c1e, exhausting connections under load",
    "level": "HYPOTHESIS",
    "confidence": 0.84,
    "would_confirm": "Pool in-use == max during error window; config diff shows 20→2",
    "would_refute": "Errors present before deploy 482, or pool not saturated"
  },
  "evidence": [{"id": "<evidence uuid>", "stance": "SUPPORTS"}],
  "suspected_changes": [{"sha": "3fa9c1e", "path": "checkout/db.py", "why": "..."}],
  "alternatives_considered": [{"statement": "...", "refuted_by": ["<evidence uuid>"]}],
  "recommended_actions": [{"type": "OPEN_PR", "title": "...", "rationale": "..."}],
  "rollback_recommended": false,
  "unknowns": ["No trace data for payments during window"]
}
```

Validated with Pydantic; invalid output → one repair attempt → `FAILED`.

## 5. Anti-hallucination controls

1. **Evidence-required schema:** `evidence` must be non-empty for any hypothesis with confidence > 0.2; each id must exist and belong to the incident.
2. **Server-side evidence capture:** evidence content is produced by tools, not the model.
3. **Confidence caps:** ≤0.5 with a single signal type; ≤0.7 without a code/config change link; >0.8 requires ≥2 independent signals **and** a candidate change whose timing precedes onset. Caps applied deterministically after the model answers.
4. **CONFIRMED_FACT only from deterministic checks or humans** (e.g. verifying the diff literally changes the value).
5. **Alternatives and unknowns are mandatory** fields.
6. **Verifier pass** before persistence.
7. **Budget limits:** max tool calls (e.g. 25), max tokens, wall-clock timeout.
8. **Reproducibility:** prompt version, model, all tool calls and results stored in `agent_steps`.

## 6. Prompt-injection posture
Logs, commit messages, code and PR text are **untrusted data**. They are delivered inside clearly delimited data blocks, the system prompt states they may contain adversarial instructions, tools are read-only (worst case: a misleading report, not an action), and outputs are schema-validated. Tool result size caps and secret redaction apply before anything reaches the model.

## 7. Evaluation
A golden set of injected failures (doc 09) with known root causes; metrics: root-cause accuracy, evidence validity rate (should be 100%), hallucination rate, time-to-first-hypothesis, tokens/cost. Run in CI against recorded fixtures (deterministic) and manually against a live model.

## 8. Provider abstraction
`LLMProvider` port: `complete(messages, tools, schema) -> response`. Default adapter: Anthropic. A `FakeLLM` adapter with scripted tool calls exists for tests — used only in tests, never presented as product intelligence.
