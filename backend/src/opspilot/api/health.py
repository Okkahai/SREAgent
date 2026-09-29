import logging
from typing import Annotated

import redis
from fastapi import APIRouter, Depends, Response, status

from opspilot import __version__
from opspilot.config import Settings, get_settings
from opspilot.db.health import check_database

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: the process is up. No dependency checks."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
def readyz(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, object]:
    """Readiness: dependencies reachable."""
    checks: dict[str, str] = {}
    try:
        check_database(settings.database_url)
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("postgres readiness failed: %s", exc)
        checks["postgres"] = "unavailable"
    try:
        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("redis readiness failed: %s", exc)
        checks["redis"] = "unavailable"
    ready = all(v == "ok" for v in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "degraded", "checks": checks}
