import logging

from opspilot.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="opspilot.workers.tasks.heartbeat")  # type: ignore[untyped-decorator]
def heartbeat() -> str:
    """Proves worker + beat + broker are wired. Detector tasks arrive in Phase 4."""
    log.info("worker heartbeat")
    return "ok"
