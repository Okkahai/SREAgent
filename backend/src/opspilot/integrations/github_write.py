"""The only GitHub write path: create a branch under `opspilot/` with file changes and open a PR.
There is intentionally no merge, delete or force-push call (docs/08 §2). Uses credentials separate
from the read-only token."""

import base64
import re
from typing import Any

import httpx

from opspilot.integrations.github import GitHubError

BRANCH_PREFIX = "opspilot/"


class GitHubWriter:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None) -> None:
        self._c = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20.0,
            transport=transport,
        )

    def _call(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = self._c.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise GitHubError(f"{type(exc).__name__}: {exc}"[:200]) from exc
        if r.status_code >= 400:
            raise GitHubError(f"GitHub {r.status_code} for {method} {path}")
        return r.json()

    def open_pull_request(
        self, repo: str, branch_suffix: str, title: str, body: str, files: list[dict[str, str]]
    ) -> dict[str, str]:
        branch = BRANCH_PREFIX + re.sub(r"[^a-zA-Z0-9._-]+", "-", branch_suffix)[:60].strip("-")
        info = self._call("GET", f"/repos/{repo}")
        base = info["default_branch"]
        sha = self._call("GET", f"/repos/{repo}/git/ref/heads/{base}")["object"]["sha"]
        self._call(
            "POST", f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha}
        )
        for f in files:
            existing = None
            try:
                existing = self._call(
                    "GET", f"/repos/{repo}/contents/{f['path']}", params={"ref": branch}
                )
            except GitHubError:
                pass  # new file
            payload: dict[str, Any] = {
                "message": f"OpsPilot: {title}"[:200],
                "content": base64.b64encode(f["content"].encode()).decode(),
                "branch": branch,
            }
            if existing and "sha" in existing:
                payload["sha"] = existing["sha"]
            self._call("PUT", f"/repos/{repo}/contents/{f['path']}", json=payload)
        pr = self._call(
            "POST",
            f"/repos/{repo}/pulls",
            json={"title": title, "head": branch, "base": base, "body": body},
        )
        return {"branch": branch, "url": pr["html_url"], "number": str(pr["number"])}
