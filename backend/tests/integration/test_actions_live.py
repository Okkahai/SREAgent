"""Proposal -> approval -> PR execution against a real Postgres. GitHub is an httpx MockTransport
that records every request so the tests can assert that nothing but branch+PR creation happens."""

import os
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from opspilot.agent.runner import claim_pending, run_investigation
from opspilot.config import get_settings
from opspilot.integrations.github_write import GitHubWriter
from opspilot.services import actions
from tests.fakes import FakeLLM, Final, ToolCall
from tests.integration.test_investigation_live import db, ids_from  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("INTEGRATION"), reason="set INTEGRATION=1 with Postgres and Redis running"
)
FILES = [{"path": "demo/shop/shop/checkout.py", "content": "DB_POOL_SIZE = 20\n"}]


def github(calls: list[tuple[str, str]], fail_pr: bool = False) -> GitHubWriter:
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        p = req.url.path
        if req.method == "GET" and p == "/repos/o/r":
            return httpx.Response(200, json={"default_branch": "main"})
        if req.method == "GET" and "/git/ref/heads/main" in p:
            return httpx.Response(200, json={"object": {"sha": "base"}})
        if req.method == "POST" and p.endswith("/git/refs"):
            return httpx.Response(201, json={})
        if req.method == "GET" and "/contents/" in p:
            return httpx.Response(404)
        if req.method == "PUT" and "/contents/" in p:
            return httpx.Response(201, json={})
        if req.method == "POST" and p.endswith("/pulls"):
            if fail_pr:
                return httpx.Response(422, json={})
            return httpx.Response(
                201, json={"html_url": "https://github.com/o/r/pull/9", "number": 9}
            )
        return httpx.Response(500)

    return GitHubWriter("w", httpx.MockTransport(handler))


@pytest.fixture()
def proposals(db: Any) -> Any:  # noqa: F811
    engine, inc = db
    (inv,) = claim_pending(engine)
    llm = FakeLLM(
        [
            ToolCall("1", "error_logs", {}),
            ToolCall("2", "recent_deployments", {}),
            lambda h: Final(
                {
                    "summary": "s",
                    "hypotheses": [
                        {
                            "statement": "pool shrank",
                            "category": "DEPLOYMENT",
                            "confidence": 0.7,
                            "evidence_ids": ids_from(h),
                        }
                    ],
                    "unknowns": [],
                    "recommended_actions": [
                        {
                            "type": "OPEN_PR",
                            "title": "restore pool",
                            "rationale": "r",
                            "parameters": {"files": FILES},
                        },
                        {
                            "type": "ROLLBACK",
                            "title": "roll back",
                            "rationale": "r",
                            "parameters": {"steps": ["redeploy 1.0.0"]},
                        },
                        {
                            "type": "OPEN_PR",
                            "title": "touch CI",
                            "rationale": "r",
                            "parameters": {
                                "files": [{"path": ".github/workflows/ci.yml", "content": "x"}]
                            },
                        },
                        {"type": "MERGE_PR", "title": "merge", "rationale": "r", "parameters": {}},
                    ],
                }
            ),
        ]
    )
    assert run_investigation(engine, inv, llm) == "COMPLETED"
    with engine.connect() as c:
        rows = (
            c.execute(text("SELECT * FROM action_proposals ORDER BY created_at")).mappings().all()
        )
    return engine, inc, {r["type"]: r for r in rows}


def test_policy_assigns_risk_and_refuses_unsafe_actions(proposals: Any) -> None:
    engine, inc, by_type = proposals
    assert set(by_type) == {"OPEN_PR", "ROLLBACK"}  # protected-path PR and MERGE_PR never stored
    assert by_type["OPEN_PR"]["risk"] == "LOW" and by_type["ROLLBACK"]["risk"] == "HIGH"
    assert by_type["ROLLBACK"]["policy_decision"]["executable"] is False
    with engine.connect() as c:
        res = c.execute(text("SELECT result FROM investigations")).scalar_one()
    assert len(res["rejected"]) >= 2


def run_exec(engine: Any, pid: Any, enabled: bool = True, w: Any = None, repo: str = "o/r") -> Any:
    return actions.execute_proposal(engine, str(pid), "alice", w, enabled, repo)


def approve(engine: Any, p: Any, h: str | None = None) -> str:
    return actions.decide_proposal(
        engine, str(p["id"]), "alice", "APPROVE", h or p["payload_hash"], "ok"
    )


def test_nothing_executes_without_approval_or_when_disabled(proposals: Any) -> None:
    engine, _, by = proposals
    calls: list[tuple[str, str]] = []
    pr = by["OPEN_PR"]
    with pytest.raises(actions.ActionError) as e:
        run_exec(engine, pr["id"], w=github(calls))
    assert e.value.status == 409  # still PENDING_APPROVAL
    approve(engine, pr)
    with pytest.raises(actions.ActionError) as e:
        run_exec(engine, pr["id"], enabled=False, w=github(calls))
    assert e.value.status == 403
    assert calls == []


def test_approval_is_bound_to_payload_and_runbooks_cannot_execute(proposals: Any) -> None:
    engine, _, by = proposals
    with pytest.raises(actions.ActionError) as e:
        approve(engine, by["OPEN_PR"], h="0" * 64)
    assert e.value.status == 409
    rb = by["ROLLBACK"]
    approve(engine, rb)
    with pytest.raises(actions.ActionError) as e:
        run_exec(engine, rb["id"], w=github([]))
    assert e.value.status == 422


def test_approved_pr_is_created_never_merged_and_audited(proposals: Any) -> None:
    engine, inc, by = proposals
    calls: list[tuple[str, str]] = []
    pr = by["OPEN_PR"]
    approve(engine, pr)
    out = run_exec(engine, pr["id"], w=github(calls))
    assert out["url"].endswith("/pull/9") and out["branch"].startswith("opspilot/")
    methods = {(m, p.split("/", 4)[-1] if p.count("/") > 3 else p) for m, p in calls}
    assert not any("merge" in p or m in ("DELETE", "PATCH") for m, p in calls), calls
    assert ("POST", "/repos/o/r/pulls") in {(m, p) for m, p in calls} and methods
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT status FROM action_proposals WHERE id = :i"), {"i": pr["id"]}
            ).scalar_one()
            == "SUCCEEDED"
        )
        acts = c.execute(text("SELECT action FROM audit_log ORDER BY id")).scalars().all()
        assert {"PROPOSAL_APPROVED", "EXECUTION_STARTED", "EXECUTION_SUCCEEDED"} <= set(acts)
    with pytest.raises(actions.ActionError) as e:  # cannot run twice
        run_exec(engine, pr["id"], w=github(calls))
    assert e.value.status == 409


def test_failed_execution_is_recorded(proposals: Any) -> None:
    engine, _, by = proposals
    pr = by["OPEN_PR"]
    approve(engine, pr)
    with pytest.raises(actions.ActionError) as e:
        run_exec(engine, pr["id"], w=github([], fail_pr=True))
    assert e.value.status == 502
    with engine.connect() as c:
        assert c.execute(text("SELECT status FROM action_executions")).scalar_one() == "FAILED"


def test_expired_proposal_cannot_be_approved(proposals: Any) -> None:
    engine, _, by = proposals
    with engine.begin() as c:
        c.execute(text("UPDATE action_proposals SET expires_at = now() - interval '1 minute'"))
    with pytest.raises(actions.ActionError) as e:
        approve(engine, by["OPEN_PR"])
    assert e.value.status == 409
    with engine.connect() as c:
        assert (
            c.execute(text("SELECT status FROM action_proposals WHERE type='OPEN_PR'")).scalar_one()
            == "EXPIRED"
        )


def test_database_refuses_unapproved_execution_and_audit_edits(proposals: Any) -> None:
    engine, _, by = proposals
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO approvals (proposal_id, approver, decision, payload_hash) "
                "VALUES (:p, 'x', 'REJECT', :h)"
            ),
            {"p": by["OPEN_PR"]["id"], "h": by["OPEN_PR"]["payload_hash"]},
        )
        c.execute(
            text(
                "INSERT INTO action_executions (proposal_id, approval_id, status) "
                "SELECT proposal_id, id, 'EXECUTING' FROM approvals"
            )
        )
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text("INSERT INTO audit_log (actor, action, subject) VALUES ('a','b','c')"))
        c.execute(text("UPDATE audit_log SET actor = 'evil'"))


def test_api_requires_approver_token_and_actor(
    proposals: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, by = proposals
    monkeypatch.setenv("OPSPILOT_APPROVER_TOKEN", "tok")
    get_settings.cache_clear()
    try:
        from opspilot.main import create_app

        c = TestClient(create_app())
        url = f"/v1/proposals/{by['OPEN_PR']['id']}/decision"
        body = {"decision": "APPROVE", "payload_hash": by["OPEN_PR"]["payload_hash"]}
        assert c.post(url, json=body).status_code == 401
        assert (
            c.post(
                url, json=body, headers={"Authorization": "Bearer nope", "X-OpsPilot-Actor": "a"}
            ).status_code
            == 401
        )
        assert c.post(url, json=body, headers={"Authorization": "Bearer tok"}).status_code == 400
        ok = c.post(
            url, json=body, headers={"Authorization": "Bearer tok", "X-OpsPilot-Actor": "gun"}
        )
        assert ok.status_code == 200 and ok.json() == {"status": "APPROVED"}
        ex = c.post(
            f"/v1/proposals/{by['OPEN_PR']['id']}/execute",
            headers={"Authorization": "Bearer tok", "X-OpsPilot-Actor": "gun"},
        )
        assert ex.status_code == 403  # actions disabled by default
    finally:
        get_settings.cache_clear()
