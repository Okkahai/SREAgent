"""Proposal lifecycle: create (policy decides risk), approve/reject (bound to the payload hash),
execute (only after approval, only if policy allows OpsPilot to run it, only when actions are
enabled). Every state change is audited (docs/08 §3, §8)."""

import hashlib
import json
from typing import Any

from sqlalchemy import Connection, Engine, text

from opspilot.adapters import postgres_incidents as q
from opspilot.domain import policy
from opspilot.integrations.github import GitHubError
from opspilot.integrations.github_write import GitHubWriter


class ActionError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def payload_hash(incident_id: Any, type_: str, params: dict[str, Any]) -> str:
    blob = json.dumps({"i": str(incident_id), "t": type_, "p": params}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def audit(conn: Connection, actor: str, action: str, subject: str, detail: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_log (actor, action, subject, detail) "
            "VALUES (:a, :ac, :s, CAST(:d AS jsonb))"
        ),
        {"a": actor, "ac": action, "s": subject, "d": json.dumps(detail, default=str)},
    )


def create_proposals(
    conn: Connection, incident_id: Any, inv_id: Any, actions: list[dict[str, Any]], ttl_minutes: int
) -> list[str]:
    """Persist model-recommended actions. Returns reasons for those refused."""
    refused: list[str] = []
    for a in actions:
        t, params = a["type"], a["parameters"]
        problems = policy.validate_parameters(t, params)
        if problems:
            refused.append(f"{t} {a['title'][:60]!r}: {'; '.join(problems)}")
            continue
        d = policy.decide(t)
        pid: Any = conn.execute(
            text(
                "INSERT INTO action_proposals (incident_id, investigation_id, type, title, rationale, "
                "parameters, payload_hash, risk, policy_decision, expires_at) VALUES (:i, :v, :t, :ti, :ra, "
                "CAST(:p AS jsonb), :h, :r, CAST(:d AS jsonb), now() + make_interval(mins => :ttl)) "
                "RETURNING id"
            ),
            {
                "i": incident_id,
                "v": inv_id,
                "t": t,
                "ti": a["title"],
                "ra": a["rationale"],
                "p": json.dumps(params),
                "h": payload_hash(incident_id, t, params),
                "r": d.risk,
                "d": json.dumps(d.as_dict()),
                "ttl": ttl_minutes,
            },
        ).scalar_one()
        audit(conn, "agent", "PROPOSAL_CREATED", str(pid), {"type": t, "risk": d.risk})
        q.add_event(
            conn,
            incident_id,
            conn.execute(text("SELECT now()")).scalar_one(),
            "PROPOSAL",
            "agent",
            f"proposed {t} ({d.risk}): {a['title']}",
            level="HYPOTHESIS",
            ref={"proposal_id": str(pid)},
        )
    return refused


def _load(conn: Connection, pid: str) -> dict[str, Any]:
    r = (
        conn.execute(
            text(
                "SELECT p.*, i.environment, i.short_id, "
                "(p.expires_at < now()) AS expired, d.metadata->>'repository' AS dep_repo "
                "FROM action_proposals p JOIN incidents i ON i.id = p.incident_id "
                "LEFT JOIN deployments d ON d.id = i.deployment_id WHERE p.id = :p FOR UPDATE OF p"
            ),
            {"p": pid},
        )
        .mappings()
        .first()
    )
    if r is None:
        raise ActionError(404, "proposal not found")
    return dict(r)


def _expire_if_needed(conn: Connection, p: dict[str, Any]) -> None:
    if p["expired"] and p["status"] in ("PENDING_APPROVAL", "APPROVED"):
        conn.execute(
            text("UPDATE action_proposals SET status = 'EXPIRED' WHERE id = :p"), {"p": p["id"]}
        )
        audit(conn, "system", "PROPOSAL_EXPIRED", str(p["id"]), {})
        p["status"] = "EXPIRED"


def decide_proposal(
    engine: Engine, pid: str, actor: str, decision: str, supplied_hash: str, comment: str | None
) -> str:
    if decision not in ("APPROVE", "REJECT"):
        raise ActionError(422, "decision must be APPROVE or REJECT")
    refusal: ActionError | None = None
    status = ""
    with engine.begin() as conn:  # commits an EXPIRED transition even when we then refuse
        p = _load(conn, pid)
        _expire_if_needed(conn, p)
        if p["status"] != "PENDING_APPROVAL":
            refusal = ActionError(409, f"proposal is {p['status']}")
        elif supplied_hash != p["payload_hash"]:
            refusal = ActionError(409, "payload_hash does not match the proposal being approved")
        if refusal is None:
            status = _record_decision(conn, p, pid, actor, decision, comment)
    if refusal:
        raise refusal
    return status


def _record_decision(
    conn: Connection, p: dict[str, Any], pid: str, actor: str, decision: str, comment: str | None
) -> str:
    conn.execute(
        text(
            "INSERT INTO approvals (proposal_id, approver, decision, payload_hash, comment) "
            "VALUES (:p, :a, :d, :h, :c)"
        ),
        {"p": pid, "a": actor, "d": decision, "h": p["payload_hash"], "c": comment},
    )
    status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    conn.execute(
        text("UPDATE action_proposals SET status = :s WHERE id = :p"), {"s": status, "p": pid}
    )
    audit(conn, actor, f"PROPOSAL_{status}", pid, {"comment": comment})
    q.add_event(
        conn,
        p["incident_id"],
        conn.execute(text("SELECT now()")).scalar_one(),
        "APPROVAL",
        actor,
        f"{p['type']} proposal {status.lower()} by {actor}",
        level="CONFIRMED_FACT",
        ref={"proposal_id": pid},
    )
    return status


def execute_proposal(
    engine: Engine,
    pid: str,
    actor: str,
    writer: GitHubWriter | None,
    actions_enabled: bool,
    default_repo: str,
) -> dict[str, Any]:
    if not actions_enabled:
        raise ActionError(403, "actions are disabled (OPSPILOT_ACTIONS_ENABLED=false)")
    with engine.begin() as conn:
        p = _load(conn, pid)
        _expire_if_needed(conn, p)
    if p["status"] == "EXPIRED":
        raise ActionError(409, "proposal expired")
    with engine.begin() as conn:
        p = _load(conn, pid)
        if p["status"] != "APPROVED":
            raise ActionError(409, f"proposal is {p['status']}, not APPROVED")
        if not policy.decide(p["type"]).executable:
            raise ActionError(
                422, f"{p['type']} cannot be executed by OpsPilot; follow it as a runbook"
            )
        approval = conn.execute(
            text(
                "SELECT id FROM approvals WHERE proposal_id = :p AND decision = 'APPROVE' "
                "AND payload_hash = :h ORDER BY decided_at DESC LIMIT 1"
            ),
            {"p": pid, "h": p["payload_hash"]},
        ).scalar_one_or_none()
        if approval is None:
            raise ActionError(409, "no approval for the current payload")
        repo = p["dep_repo"] or default_repo
        if writer is None or not repo:
            raise ActionError(503, "GitHub write access or repository is not configured")
        exec_id = conn.execute(
            text(
                "INSERT INTO action_executions (proposal_id, approval_id, status) "
                "VALUES (:p, :a, 'EXECUTING') RETURNING id"
            ),
            {"p": pid, "a": approval},
        ).scalar_one()
        conn.execute(
            text("UPDATE action_proposals SET status = 'EXECUTING' WHERE id = :p"), {"p": pid}
        )
        audit(conn, actor, "EXECUTION_STARTED", pid, {"execution_id": str(exec_id), "repo": repo})
    params = p["parameters"]
    try:
        result: dict[str, Any] = dict(
            writer.open_pull_request(
                repo,
                f"{p['short_id']}-{str(pid)[:8]}",
                p["title"],
                f"{p['rationale']}\n\nProposed by OpsPilot for {p['short_id']}. Approved by {actor}. "
                "Review before merging; OpsPilot never merges.",
                params["files"],
            )
        )
        status, error = "SUCCEEDED", None
    except GitHubError as exc:
        result, status, error = {}, "FAILED", str(exc)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE action_executions SET status = :s, finished_at = now(), "
                "result = CAST(:r AS jsonb), error = :e WHERE id = :x"
            ),
            {"s": status, "r": json.dumps(result), "e": error, "x": exec_id},
        )
        conn.execute(
            text("UPDATE action_proposals SET status = :s WHERE id = :p"), {"s": status, "p": pid}
        )
        audit(conn, actor, f"EXECUTION_{status}", pid, {"result": result, "error": error})
        q.add_event(
            conn,
            p["incident_id"],
            conn.execute(text("SELECT now()")).scalar_one(),
            "ACTION",
            "executor",
            f"{p['type']} {status.lower()}"
            + (f": {result.get('url')}" if result else f": {error}"),
            ref={"proposal_id": pid, **result},
        )
    if status == "FAILED":
        raise ActionError(502, error or "execution failed")
    return result
