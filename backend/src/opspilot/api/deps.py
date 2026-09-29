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
