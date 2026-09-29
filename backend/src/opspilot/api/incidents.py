from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from opspilot.adapters import postgres_incidents as q
from opspilot.api.deps import require_viewer
from opspilot.db.engine import get_engine

router = APIRouter(
    prefix="/v1/incidents", tags=["incidents"], dependencies=[Depends(require_viewer)]
)


@router.get("")
def list_incidents(
    open_only: bool = False, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        return q.list_incidents(conn, open_only, limit)


@router.get("/{ident}")
def get_incident(ident: str) -> dict[str, Any]:
    """Incident by short id (INC-0001) or UUID, with timeline and evidence."""
    with get_engine().connect() as conn:
        inc = q.get_incident(conn, ident)
    if inc is None:
        raise HTTPException(404, "incident not found")
    return inc
