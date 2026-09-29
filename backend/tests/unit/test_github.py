import base64
import hashlib
import hmac
import json

import httpx
from fastapi.testclient import TestClient

from opspilot.integrations.github import GitHubClient


def transport(calls: list[tuple[str, str]]) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.url.path.endswith("/contents/.github/CODEOWNERS"):
            body = base64.b64encode(b"/demo/ @org/shop\n").decode()
            return httpx.Response(200, json={"content": body})
        if "/contents/" in req.url.path:
            return httpx.Response(404)
        if req.url.path.endswith("/commits/abc123"):
            return httpx.Response(
                200,
                json={
                    "sha": "abc123",
                    "html_url": "https://github.com/o/r/commit/abc123",
                    "commit": {
                        "message": "shrink pool\n\nbody",
                        "author": {"name": "Dev", "date": "2026-09-29T07:00:00Z"},
                    },
                    "files": [
                        {
                            "filename": "demo/shop/x.py",
                            "status": "modified",
                            "additions": 1,
                            "deletions": 1,
                            "patch": "-POOL=20\n+POOL=2",
                        }
                    ],
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_commit_with_owners_and_only_get_requests():
    calls: list[tuple[str, str]] = []
    c = GitHubClient("t", transport(calls)).commit("o/r", "abc123")
    assert c and c.owners == ["@org/shop"] and c.files[0]["patch"].endswith("+POOL=2")
    assert {m for m, _ in calls} == {"GET"}
    assert GitHubClient("t", transport([])).commit("o/r", "nope") is None


def test_webhook_signature(monkeypatch):
    from opspilot.config import get_settings
    from opspilot.main import create_app

    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        body = json.dumps({"zen": "x"}).encode()
        sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
        h = {"X-GitHub-Event": "ping", "Content-Type": "application/json"}
        assert (
            client.post(
                "/v1/webhooks/github", content=body, headers={**h, "X-Hub-Signature-256": sig}
            ).status_code
            == 202
        )
        assert (
            client.post(
                "/v1/webhooks/github",
                content=body,
                headers={**h, "X-Hub-Signature-256": "sha256=bad"},
            ).status_code
            == 401
        )
    finally:
        get_settings.cache_clear()
