# Demo shop

Three small FastAPI services instrumented with OpenTelemetry, used as the monitored system for OpsPilot.

```
loadgen ──► gateway ──► checkout ──► shop-db (Postgres)
                            └──────► payments
```

| Service | Role | Notable telemetry |
|---------|------|-------------------|
| gateway | public API (`/products`, `/checkout`) | HTTP server/client spans and metrics |
| checkout | writes orders, calls payments | SQLAlchemy spans, `db.client.connection.count`/`max` (pool saturation) |
| payments | fake card processor | request latency/errors |

## Fault injection

Each service exposes `/_faults` (bound to localhost). Faults are reversible and change real behaviour:

| Fault | Effect | Signature in telemetry |
|-------|--------|------------------------|
| `http_500` | fail a fraction of requests | 500s, "injected internal error" logs |
| `db_timeout` | hold connection past statement timeout | slow spans, `canceling statement due to statement timeout` |
| `memory_spike` | retain N MB | process memory growth |
| `down` | service answers 503 | dependency failure seen by callers |
| `latency` | add per-request delay | p95 latency increase |
| bad deployment | `scripts/deploy.sh bad` redeploys checkout as v1.1.0 with `DB_POOL_SIZE=2` | pool saturation, "QueuePool limit ... reached" logs, 503s after the deploy |

The bad deployment is a real container recreation with a new `service.version` and `vcs.ref.head.revision`; the regression is a configuration change of the kind a commit would introduce. In Phase 6, OpsPilot will link such a version to a real commit diff.
