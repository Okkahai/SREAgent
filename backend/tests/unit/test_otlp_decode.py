from opspilot.services import otlp
from tests.otlp_builders import logs_request, metrics_request, trace_request


def test_decode_traces_maps_correlation_attributes() -> None:
    rows = otlp.decode_traces(trace_request(error=True, duration_ms=250).SerializeToString())
    assert len(rows) == 1
    r = rows[0]
    assert r.resource.service == "checkout"
    assert r.resource.environment == "demo"
    assert r.resource.version == "1.0.0"
    assert r.resource.commit == "abc1234"
    assert r.trace_id == "01" * 16 and r.span_id == "01" * 8
    assert r.parent_span_id is None
    assert r.status_code == 2 and r.kind == 2
    assert 249_000_000 <= r.duration_ns <= 251_000_000
    assert r.attributes["http.route"] == "/checkout"


def test_decode_logs_keeps_trace_context() -> None:
    (r,) = otlp.decode_logs(logs_request("boom").SerializeToString())
    assert r.body == "boom" and r.severity_number == 17
    assert r.trace_id == "01" * 16


def test_decode_metrics_gauge_and_histogram() -> None:
    rows = otlp.decode_metrics(metrics_request().SerializeToString())
    by_name = {r.name: r.value for r in rows}
    assert by_name["db.client.connection.count"] == 2.0
    assert by_name["http.server.request.duration.count"] == 10.0
    assert by_name["http.server.request.duration.sum"] == 1.5


def test_span_without_ids_is_skipped() -> None:
    req = trace_request()
    req.resource_spans[0].scope_spans[0].spans[0].trace_id = b""
    assert otlp.decode_traces(req.SerializeToString()) == []
