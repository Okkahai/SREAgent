from typing import Protocol

from opspilot.services.otlp import LogRow, MetricRow, SpanRow


class TelemetryStore(Protocol):
    """Write side of telemetry storage. Postgres today; a columnar store could replace it."""

    def insert_spans(self, rows: list[SpanRow]) -> int: ...
    def insert_logs(self, rows: list[LogRow]) -> int: ...
    def insert_metrics(self, rows: list[MetricRow]) -> int: ...
