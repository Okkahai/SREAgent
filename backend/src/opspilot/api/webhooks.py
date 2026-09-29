import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from opspilot.adapters import postgres_commits as commits
from opspilot.config import get_settings
from opspilot.db.engine import get_engine

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
) -> dict[str, Any]:
    """Signature-verified GitHub webhooks. Only CI run state is recorded; nothing here acts."""
    secret = get_settings().github_webhook_secret
    if not secret:
        raise HTTPException(503, "webhooks disabled: GITHUB_WEBHOOK_SECRET not set")
    body = await request.body()
    want = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, x_hub_signature_256):
        raise HTTPException(401, "bad signature")
    payload = await request.json()
    if x_github_event == "workflow_run" and "workflow_run" in payload:
        with get_engine().begin() as conn:
            commits.upsert_ci_run(conn, payload["repository"]["full_name"], payload["workflow_run"])
    return {"event": x_github_event}
