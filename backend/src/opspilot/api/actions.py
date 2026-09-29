from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from opspilot.api.deps import require_approver
from opspilot.config import Settings, get_settings
from opspilot.db.engine import get_engine
from opspilot.integrations.github_write import GitHubWriter
from opspilot.services import actions

router = APIRouter(prefix="/v1", tags=["actions"])


class Decision(BaseModel):
    decision: str  # APPROVE | REJECT
    payload_hash: str  # must equal the proposal's hash: approves exactly what was shown
    comment: str | None = None


@router.get("/incidents/{ident}/proposals")
def list_proposals(ident: str) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT p.id, p.type, p.title, p.rationale, p.parameters, p.payload_hash, p.risk, p.status, "
                "p.policy_decision, p.expires_at, p.created_at FROM action_proposals p "
                "JOIN incidents i ON i.id = p.incident_id WHERE i.short_id = :x OR i.id::text = :x "
                "ORDER BY p.created_at"
            ),
            {"x": ident},
        ).mappings()
        return [dict(r) for r in rows]


def _wrap(fn: Any, *a: Any) -> Any:
    try:
        return fn(*a)
    except actions.ActionError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.post("/proposals/{pid}/decision")
def decide(
    pid: str, body: Decision, actor: Annotated[str, Depends(require_approver)]
) -> dict[str, str]:
    status = _wrap(
        actions.decide_proposal,
        get_engine(),
        pid,
        actor,
        body.decision,
        body.payload_hash,
        body.comment,
    )
    return {"status": status}


@router.post("/proposals/{pid}/execute")
def execute(
    pid: str,
    actor: Annotated[str, Depends(require_approver)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    writer = GitHubWriter(settings.github_write_token) if settings.github_write_token else None
    return dict(
        _wrap(
            actions.execute_proposal,
            get_engine(),
            pid,
            actor,
            writer,
            settings.opspilot_actions_enabled,
            settings.github_repo,
        )
    )
