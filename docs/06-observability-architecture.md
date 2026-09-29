# 06 — Observability Architecture

OpsPilot both **consumes** telemetry from monitored systems and **emits** its own.

## 1. Signals and pipeline

```
demo services (OTel SDK, auto + manual instrumentation)
   │ OTLP gRPC :4317 / HTTP :4318
   ▼
OTel Collector
   processors: memory_limiter → resource (env, deployment.*) → batch
   exporters : otlphttp → OpsPilot ingest (/v1/otlp/*), debug (dev), [optional] Prometheus endpoint
   ▼
OpsPilot API: authenticate ingest token → normalize → resolve service → batch insert → rollups
```

OpsPilot accepts OTLP/HTTP (protobuf and JSON) at `/v1/otlp/v1/{logs,metrics,traces}`, so the collector's `otlphttp` exporter works unmodified. Auth: bearer ingest token (per environment).

## 2. Resource attributes (the correlation contract)

| Attribute | Use |
|-----------|-----|
| `service.name`, `service.namespace` | service identity |
| `deployment.environment.name` | environment |
| `service.version` | deployment/version |
| `vcs.ref.head.revision` (fallback: `opspilot.commit_sha`) | commit SHA baked in at build time |
| `host.name` / `k8s.pod.name` | instance |
| `trace_id`, `span_id` on logs | log ↔ trace correlation |

Correlation keys: **service · timestamp window · deployment version · trace ID · commit · environment**. A deployment event (`POST /v1/deployments`, sent by the pipeline) supplies version→commit→time; telemetry is joined on `service.version`.

## 3. Signal handling

- **Logs:** OTLP logs with trace context. Structured JSON from the demo. Severity normalized to OTel severity numbers. Bodies truncated (8 KB), secrets redacted at ingest (regex + key-name rules). Error-level logs get a *fingerprint* (message template with variables stripped) for grouping.
- **Metrics:** RED per service/route (`http.server.request.duration` histogram, `http.server.request.count`), plus saturation gauges (`db.client.connection.count`, `process.runtime.memory`, CPU). Histograms rolled up to `service_metrics_1m` with percentiles estimated from buckets.
- **Traces:** spans stored with duration/status. Investigation tools retrieve slow/error traces for a route and window, and the critical path of a trace (which downstream span owns the time/error).
- **Deployments:** first-class events; each creates a timeline anchor and a before/after comparison window.

## 4. Detection signals (deterministic)

| Rule | Condition (default) |
|------|---------------------|
| `error_rate` | route/service error ratio > max(2%, 3× baseline) for 2 min |
| `latency_p95` | p95 > 2× baseline and > absolute floor for 3 min |
| `saturation` | DB pool in-use ≥ 90% / memory > 85% for 2 min |
| `deploy_regression` | any of the above within 15 min after a deployment → links deployment |
| `dependency_failure` | error spans whose peer service has error ratio spike |
| `log_pattern` | new error fingerprint exceeding N/min |

Baseline = same service/route, previous 60 min excluding the current window (seasonality is out of scope for MVP and documented).

## 5. OpsPilot self-observability (dogfooding)

- OTel SDK in API and workers; FastAPI, SQLAlchemy, Celery, Redis and httpx instrumentation; trace context propagated API → Celery task → agent tool calls → LLM call (each agent step is a span).
- Custom metrics: `opspilot.ingest.records`, `opspilot.detection.evaluations`, `opspilot.incidents.opened`, `opspilot.investigation.duration`, `opspilot.llm.tokens`, `opspilot.queue.depth`.
- JSON logs with `trace_id`/`span_id`.
- OpsPilot's telemetry goes to the same collector, so OpsPilot can (in a later phase) monitor itself.

## 6. Local stack
Collector config: `deploy/otel/collector.yaml`. In Phase 1 it exposes OTLP receivers and a `debug` exporter (so telemetry visibly flows); the `otlphttp` exporter to OpsPilot is enabled in Phase 3 when the ingest endpoints exist.
