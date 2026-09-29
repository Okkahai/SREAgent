"""Read APIs (services, deployments, ingest stats) and the deployment-event write API."""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from opspilot.adapters.postgres_store import PostgresStore
from opspilot.api.deps import get_store, require_ingest_token, require_viewer

router = APIRouter(prefix="/v1", tags=["platform"])
Store = Annotated[PostgresStore, Depends(get_store)]


class DeploymentIn(BaseModel):
    service: str = Field(min_length=1, max_length=200)
    environment: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=200)
    commit_sha: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{7,40}$")
    status: Literal["STARTED", "SUCCEEDED", "FAILED", "ROLLED_BACK"] = "SUCCEEDED"
    started_at: datetime
    finished_at: datetime | None = None
    ci_run_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/deployments", status_code=201, dependencies=[Depends(require_ingest_token)])
def create_deployment(body: DeploymentIn, store: Store) -> dict[str, Any]:
    return store.record_deployment(body.model_dump())


@router.get("/deployments", dependencies=[Depends(require_viewer)])
def list_deployments(
    store: Store,
    service: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    return store.list_deployments(service, limit)


@router.get("/services", dependencies=[Depends(require_viewer)])
def list_services(store: Store) -> list[dict[str, Any]]:
    """Per-service RED metrics over the last 5 minutes plus latest deployment."""
    return store.list_services()


@router.get("/telemetry/stats", dependencies=[Depends(require_viewer)])
def telemetry_stats(store: Store) -> dict[str, int]:
    """Rows ingested in the last 10 minutes, per signal (ingest health)."""
    return store.telemetry_stats()
