"""Helpers that build real OTLP protobuf payloads for tests."""

import time

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource


def kv(key: str, value: str | int) -> KeyValue:
    v = AnyValue(int_value=value) if isinstance(value, int) else AnyValue(string_value=value)
    return KeyValue(key=key, value=v)


def resource(
    service: str = "checkout", version: str = "1.0.0", commit: str = "abc1234"
) -> Resource:
    return Resource(
        attributes=[
            kv("service.name", service),
            kv("deployment.environment.name", "demo"),
            kv("service.version", version),
            kv("vcs.ref.head.revision", commit),
        ]
    )


def now_ns() -> int:
    return time.time_ns()


def trace_request(
    *, service: str = "checkout", error: bool = False, duration_ms: int = 100, trace_byte: int = 1
) -> ExportTraceServiceRequest:
    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    rs.resource.CopyFrom(resource(service))
    span = rs.scope_spans.add().spans.add()
    span.trace_id = bytes([trace_byte]) * 16
    span.span_id = bytes([trace_byte]) * 8
    span.name = "POST /checkout"
    span.kind = 2  # SERVER
    end = now_ns()
    span.start_time_unix_nano = end - duration_ms * 1_000_000
    span.end_time_unix_nano = end
    span.status.code = 2 if error else 0
    span.attributes.append(kv("http.route", "/checkout"))
    return req


def logs_request(
    body: str = "QueuePool limit reached", trace_byte: int = 1
) -> ExportLogsServiceRequest:
    req = ExportLogsServiceRequest()
    rl = req.resource_logs.add()
    rl.resource.CopyFrom(resource())
    rec = rl.scope_logs.add().log_records.add()
    rec.time_unix_nano = now_ns()
    rec.severity_number = 17  # ERROR
    rec.body.string_value = body
    rec.trace_id = bytes([trace_byte]) * 16
    rec.span_id = bytes([trace_byte]) * 8
    return req


def metrics_request() -> ExportMetricsServiceRequest:
    req = ExportMetricsServiceRequest()
    rm = req.resource_metrics.add()
    rm.resource.CopyFrom(resource())
    sm = rm.scope_metrics.add()
    gauge = sm.metrics.add()
    gauge.name = "db.client.connection.count"
    p = gauge.gauge.data_points.add()
    p.time_unix_nano = now_ns()
    p.as_int = 2
    p.attributes.append(kv("state", "used"))
    hist = sm.metrics.add()
    hist.name = "http.server.request.duration"
    hp = hist.histogram.data_points.add()
    hp.time_unix_nano = now_ns()
    hp.count = 10
    hp.sum = 1.5
    return req
