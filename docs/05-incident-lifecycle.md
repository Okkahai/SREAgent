# 05 — Incident Lifecycle

## State machine

```
            detector breach
                 │
                 ▼
          ┌───────────┐  investigation queued   ┌───────────────┐
          │ DETECTED  │────────────────────────►│ INVESTIGATING │
          └─────┬─────┘                         └───────┬───────┘
                │ signal recovers (auto)                │ hypothesis with evidence
                │ before investigation                  ▼
                │                               ┌───────────────┐
                │                               │  IDENTIFIED   │◄─── human confirms / edits root cause
                │                               └───────┬───────┘
                │                                       │ action approved & executed
                │                                       ▼
                │                               ┌───────────────┐
                │                               │  MITIGATING   │
                │                               └───────┬───────┘
                │                                       │ action done
                ▼                                       ▼
          ┌───────────┐  signal healthy N min   ┌───────────────┐
          │ RESOLVED  │◄────────────────────────│  MONITORING   │
          └─────┬─────┘                         └───────────────┘
                │ post-review complete / auto-close after 24h
                ▼
          ┌───────────┐
          │  CLOSED   │
          └───────────┘
```

Reopen: if the same fingerprint breaches again within 30 min of `RESOLVED`, the incident returns to `DETECTED` (a `REOPENED` timeline event) instead of creating a duplicate.

## Transitions

| From → To | Trigger | Actor | Guard |
|-----------|---------|-------|-------|
| — → DETECTED | Rule breach sustained ≥ `for` duration | detector | no open incident with same fingerprint |
| DETECTED → INVESTIGATING | Investigation task starts | worker | LLM provider configured |
| INVESTIGATING → IDENTIFIED | Investigation completes with ≥1 hypothesis backed by evidence | agent + verifier | evidence invariant holds |
| INVESTIGATING → INVESTIGATING | Investigation failed → retry (max 3) | worker | — |
| IDENTIFIED → MITIGATING | Action approved and execution started | human + policy | approval row exists |
| any open → MONITORING | Action completed or signal recovers | detector/executor | — |
| MONITORING → RESOLVED | Signal healthy for `recovery_window` (default 10 min) | detector | — |
| MONITORING → DETECTED | Signal breaches again | detector | reopen logic |
| RESOLVED → CLOSED | Human closes, or 24 h elapsed | human/beat | outcome recorded |

Invalid transitions are rejected in the domain layer (a pure function `transition(state, event) -> state`) and unit-tested exhaustively.

## Timestamps
- `started_at`: estimated fault onset (first bucket in the breach window, refined by change-point detection or the deployment finish time).
- `detected_at`: when the detector opened the incident.
- `resolved_at`: start of the sustained-healthy window.
- MTTD = `detected_at − started_at`; MTTR = `resolved_at − started_at`.

## Severity
Assigned deterministically from rule + blast radius (error budget burn, % traffic affected, critical-path service). The AI may *recommend* a change with justification; a change is recorded as a timeline event and requires a human or policy confirmation. It never silently overrides.

## Timeline
Append-only `incident_events` — every deployment, anomaly, log pattern, state change, agent step, proposal, approval and execution appears with source and epistemic level. Example:

```
14:02 DEPLOYMENT   deployment 482 (checkout-api v1.8.0, sha 3fa9c1e) completed     OBSERVATION
14:04 METRIC       error rate 0.4% → 9.1% on POST /checkout                        OBSERVATION
14:05 LOG_PATTERN  "QueuePool limit of size 2 overflow 0 reached" ×212             OBSERVATION
14:06 STATE        incident INC-0042 created (HIGH)                                 OBSERVATION
14:07 AI_STEP      investigation started
14:08 AI_STEP      commit 3fa9c1e changed DB_POOL_SIZE 20 → 2                       HYPOTHESIS (0.84)
```

## Outcome measurement
On resolve, `outcome` records: result (`RECOVERED_AFTER_ACTION`, `RECOVERED_SELF`, `NO_ACTION_NEEDED`, `FALSE_POSITIVE`), MTTD/MTTR, whether the human-confirmed root cause matched the AI's top hypothesis (feeds evaluation, doc 09), and follow-up notes.

## Phase 4 implementation notes
- Implemented transitions: detection (`BREACH`/`RECOVERING`/`RECOVERED`), reopen and dedupe. Investigation, action and close transitions exist in the state machine but are driven by later phases.
- Any open, unhealthy incident whose signal recovers moves to `MONITORING` (not directly to `RESOLVED`), then to `RESOLVED` after `DETECTION_RECOVERY_MINUTES` (default 10) of continuous health. `resolved_at` is the start of the healthy window.
- A window with too little traffic is `NO_DATA`: it never opens, resolves or reopens anything.
- Reopen only happens if the same fingerprint breaches within 30 min **and** the correlated deployment is unchanged; a new deployment context opens a new incident.
- Deployment correlation is a *link* (latest deployment within 15 min before onset, preferring the same service), recorded as an OBSERVATION. Causation is a Phase 5 hypothesis.
- Baselines use the median per-minute error rate and cap it at 5% so a running outage cannot become the "normal" the detector learns.
