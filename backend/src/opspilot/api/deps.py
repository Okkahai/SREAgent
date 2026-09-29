import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from opspilot.adapters.postgres_store import PostgresStore
from opspilot.config import Settings, get_settings
from opspilot.db.engine import get_engine


def get_store(settings: Annotated[Settings, Depends(get_settings)]) -> PostgresStore:
    return _store(settings.telemetry_retention_days)


@lru_cache
def _store(retention_days: int) -> PostgresStore:
    return PostgresStore(get_engine(), retention_days)


def require_ingest_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Bearer-token auth for machine writes (OTLP ingest, deployment events)."""
    if not settings.opspilot_ingest_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ingest token not configured")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), settings.opspilot_ingest_token.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")


def require_approver(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_opspilot_actor: Annotated[str | None, Header()] = None,
) -> str:
    """The `approver` role. Returns the actor name recorded in approvals and the audit log."""
    if not settings.opspilot_approver_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "approver token not configured")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), settings.opspilot_approver_token.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    if not x_opspilot_actor or not x_opspilot_actor.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-OpsPilot-Actor header required")
    return x_opspilot_actor.strip()[:100]
