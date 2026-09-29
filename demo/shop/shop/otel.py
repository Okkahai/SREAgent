"""Shared OpenTelemetry setup: traces, metrics and logs over OTLP/HTTP, plus JSON stdout logs.

Resource attributes are the correlation contract used by OpsPilot (docs/06):
service.name, service.version, deployment.environment.name, vcs.ref.head.revision.
"""

import json
import logging
import os
from datetime import UTC, datetime

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = trace.get_current_span().get_span_context()
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if ctx.is_valid:
            payload["trace_id"] = format(ctx.trace_id, "032x")
            payload["span_id"] = format(ctx.span_id, "016x")
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_otel(service_name: str) -> Resource:
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.environ.get("SERVICE_VERSION", "1.0.0"),
            "deployment.environment.name": os.environ.get("DEPLOY_ENV", "demo"),
            "vcs.ref.head.revision": os.environ.get("COMMIT_SHA", "unknown"),
        }
    )
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")

    tracer_provider = TracerProvider(resource=resource)
    meter_readers = []
    logger_provider = LoggerProvider(resource=resource)
    if endpoint:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(f"{endpoint}/v1/traces"))
        )
        meter_readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(f"{endpoint}/v1/metrics"), export_interval_millis=5000
            )
        )
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(f"{endpoint}/v1/logs"))
        )
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=meter_readers))
    set_logger_provider(logger_provider)

    stdout = logging.StreamHandler()
    stdout.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [stdout, LoggingHandler(level=logging.INFO, logger_provider=logger_provider)]
    root.setLevel(logging.INFO)
    return resource
