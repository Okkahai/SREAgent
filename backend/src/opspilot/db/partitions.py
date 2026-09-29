"""Daily range partitions for telemetry tables, created on demand and dropped by retention."""

import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Connection, text

PARTITIONED_TABLES = ("log_records", "spans", "metric_points")
_NAME = re.compile(r"^(?P<table>[a-z_]+)_(?P<day>\d{8})$")


def partition_name(table: str, day: date) -> str:
    if table not in PARTITIONED_TABLES:
        raise ValueError(f"not a partitioned table: {table}")
    return f"{table}_{day:%Y%m%d}"


def ensure_partition(conn: Connection, table: str, day: date) -> None:
    name = partition_name(table, day)
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    # Advisory lock serialises concurrent creators of the same partition.
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:n))"), {"n": name})
    conn.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {table} "  # noqa: S608 - name validated
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
        )
    )


def drop_old_partitions(
    conn: Connection, retention_days: int, today: date | None = None
) -> list[str]:
    cutoff = (today or datetime.now(UTC).date()) - timedelta(days=retention_days)
    dropped: list[str] = []
    rows = conn.execute(
        text("SELECT c.relname FROM pg_class c JOIN pg_inherits i ON i.inhrelid = c.oid")
    ).scalars()
    for relname in list(rows):
        m = _NAME.match(relname)
        if not m or m["table"] not in PARTITIONED_TABLES:
            continue
        day = datetime.strptime(m["day"], "%Y%m%d").date()
        if day < cutoff:
            conn.execute(text(f"DROP TABLE {relname}"))
            dropped.append(relname)
    return dropped
