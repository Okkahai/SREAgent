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


@celery_app.task(name="opspilot.workers.tasks.detect_incidents")  # type: ignore[untyped-decorator]
def detect_incidents() -> bool:
    """Evaluate detection rules. A Postgres advisory lock keeps overlapping runs from racing."""
    from datetime import UTC, datetime

    from sqlalchemy import text

    from opspilot.services.detector import Detector

    engine = get_engine()
    with engine.connect() as lock_conn:
        if not lock_conn.execute(text("SELECT pg_try_advisory_lock(727001)")).scalar_one():
            return False
        try:
            Detector(engine, _detection_config()).evaluate(datetime.now(UTC))
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(727001)"))
    return True


def _detection_config():  # type: ignore[no-untyped-def]
    from opspilot.services.detection import DetectionConfig

    s = get_settings()
    return DetectionConfig(recovery_minutes=s.detection_recovery_minutes)


@celery_app.task(name="opspilot.workers.tasks.investigate_pending")  # type: ignore[untyped-decorator]
def investigate_pending() -> int:
    """Claim incidents that need an investigation and fan them out to workers."""
    from opspilot.agent.runner import claim_pending

    ids = claim_pending(get_engine())
    for inv_id in ids:
        investigate.delay(str(inv_id))
    return len(ids)


@celery_app.task(name="opspilot.workers.tasks.investigate")  # type: ignore[untyped-decorator]
def investigate(investigation_id: str) -> str:
    from opspilot.agent.llm import AnthropicLLM
    from opspilot.agent.runner import run_investigation
    from opspilot.integrations.github import GitHubClient

    s = get_settings()
    llm = AnthropicLLM(s.anthropic_api_key, s.llm_model) if s.anthropic_api_key else None
    gh = GitHubClient(s.github_token) if s.github_token else None
    return run_investigation(
        get_engine(),
        investigation_id,
        llm,
        s.agent_max_steps,
        gh,
        s.github_repo,
        s.proposal_ttl_minutes,
    )
