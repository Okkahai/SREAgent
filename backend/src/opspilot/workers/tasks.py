import logging

from opspilot.adapters.postgres_store import PostgresStore
from opspilot.config import get_settings
from opspilot.db.engine import get_engine
from opspilot.workers.celery_app import celery_app

log = logging.getLogger(__name__)


def _store() -> PostgresStore:
    return PostgresStore(get_engine(), get_settings().telemetry_retention_days)


@celery_app.task(name="opspilot.workers.tasks.heartbeat")  # type: ignore[untyped-decorator]
def heartbeat() -> str:
    """Proves worker + beat + broker are wired."""
    log.info("worker heartbeat")
    return "ok"


@celery_app.task(name="opspilot.workers.tasks.rollup_service_metrics")  # type: ignore[untyped-decorator]
def rollup_service_metrics() -> int:
    """Refresh per-minute RED rollups from recent server spans (input for detectors)."""
    return _store().rollup_service_metrics()


@celery_app.task(name="opspilot.workers.tasks.maintain_partitions")  # type: ignore[untyped-decorator]
def maintain_partitions() -> list[str]:
    """Create upcoming daily partitions and drop those past retention."""
    dropped = _store().maintain_partitions()
    if dropped:
        log.info("dropped partitions: %s", dropped)
    return dropped
