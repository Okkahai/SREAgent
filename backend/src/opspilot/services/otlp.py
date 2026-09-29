"""Decode OTLP protobuf payloads into flat rows (pure functions, no I/O).

Resource attributes are the correlation contract (docs/06): service.name,
deployment.environment.name, service.version, vcs.ref.head.revision.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource

MAX_BODY_CHARS = 8192


@dataclass(frozen=True)
class ResourceInfo:
    service: str
    environment: str
    version: str | None
    commit: str | None


@dataclass
class SpanRow:
    resource: ResourceInfo
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: int
    start_time: datetime
    duration_ns: int
    status_code: int
    status_message: str | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class LogRow:
    resource: ResourceInfo
    time: datetime
    severity_number: int
    body: str
    trace_id: str | None
    span_id: str | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricRow:
    resource: ResourceInfo
    time: datetime
    name: str
    value: float
    attributes: dict[str, Any] = field(default_factory=dict)


def _any(v: AnyValue) -> Any:
    kind = v.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [_any(x) for x in v.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _any(kv.value) for kv in v.kvlist_value.values}
    if kind == "bytes_value":
        return v.bytes_value.hex()
    return getattr(v, kind)


def _attrs(kvs: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kv in kvs:
        assert isinstance(kv, KeyValue)
        out[kv.key] = _any(kv.value)
    return out


def _resource(res: Resource) -> ResourceInfo:
    a = _attrs(res.attributes)
    return ResourceInfo(
        service=str(a.get("service.name") or "unknown_service"),
        environment=str(
            a.get("deployment.environment.name") or a.get("deployment.environment") or "unknown"
        ),
        version=str(a["service.version"]) if a.get("service.version") else None,
        commit=str(a.get("vcs.ref.head.revision") or a.get("opspilot.commit_sha") or "") or None,
    )


def _ts(unix_nano: int) -> datetime:
    return datetime.fromtimestamp(unix_nano / 1e9, UTC)


def _hex(b: bytes) -> str | None:
    return b.hex() if b and any(b) else None


def decode_traces(body: bytes) -> list[SpanRow]:
    req = ExportTraceServiceRequest()
    req.ParseFromString(body)
    rows: list[SpanRow] = []
    for rs in req.resource_spans:
        res = _resource(rs.resource)
        for ss in rs.scope_spans:
            for s in ss.spans:
                trace_id, span_id = _hex(s.trace_id), _hex(s.span_id)
                if not trace_id or not span_id:
                    continue
                rows.append(
                    SpanRow(
                        resource=res,
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=_hex(s.parent_span_id),
                        name=s.name,
                        kind=int(s.kind),
                        start_time=_ts(s.start_time_unix_nano),
                        duration_ns=max(0, s.end_time_unix_nano - s.start_time_unix_nano),
                        status_code=int(s.status.code),
                        status_message=s.status.message or None,
                        attributes=_attrs(s.attributes),
                    )
                )
    return rows


def decode_logs(body: bytes) -> list[LogRow]:
    req = ExportLogsServiceRequest()
    req.ParseFromString(body)
    rows: list[LogRow] = []
    for rl in req.resource_logs:
        res = _resource(rl.resource)
        for sl in rl.scope_logs:
            for r in sl.log_records:
                ts = r.time_unix_nano or r.observed_time_unix_nano
                text = _any(r.body)
                rows.append(
                    LogRow(
                        resource=res,
                        time=_ts(ts) if ts else datetime.now(UTC),
                        severity_number=int(r.severity_number),
                        body=(text if isinstance(text, str) else str(text))[:MAX_BODY_CHARS],
                        trace_id=_hex(r.trace_id),
                        span_id=_hex(r.span_id),
                        attributes=_attrs(r.attributes),
                    )
                )
    return rows


def decode_metrics(body: bytes) -> list[MetricRow]:
    """Gauges/sums become one point each; histograms become `<name>.count` and `<name>.sum`."""
    req = ExportMetricsServiceRequest()
    req.ParseFromString(body)
    rows: list[MetricRow] = []
    for rm in req.resource_metrics:
        res = _resource(rm.resource)
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                kind = m.WhichOneof("data")
                if kind in ("gauge", "sum"):
                    for p in getattr(m, kind).data_points:
                        value = (
                            p.as_double if p.WhichOneof("value") == "as_double" else float(p.as_int)
                        )
                        rows.append(
                            MetricRow(
                                res, _ts(p.time_unix_nano), m.name, value, _attrs(p.attributes)
                            )
                        )
                elif kind == "histogram":
                    for p in m.histogram.data_points:
                        t, a = _ts(p.time_unix_nano), _attrs(p.attributes)
                        rows.append(MetricRow(res, t, f"{m.name}.count", float(p.count), a))
                        if p.HasField("sum"):
                            rows.append(MetricRow(res, t, f"{m.name}.sum", p.sum, a))
    return rows
