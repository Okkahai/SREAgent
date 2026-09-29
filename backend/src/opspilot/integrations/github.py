"""Read-only GitHub client. It exposes GET calls only; write scopes arrive with Phase 7's separate
executor credentials (docs/08 §2)."""

import base64
from dataclasses import dataclass, field
from typing import Any

import httpx

from opspilot.integrations import codeowners

MAX_FILES = 50
MAX_PATCH = 1500  # characters kept per file: enough to see a changed value, bounded for prompts


class GitHubError(Exception):
    pass


@dataclass
class CommitInfo:
    repo: str
    sha: str
    message: str
    author: str | None
    committed_at: str | None
    url: str | None
    files: list[dict[str, Any]] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)


class GitHubClient:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None) -> None:
        self._c = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15.0,
            transport=transport,
        )

    def _get(self, path: str) -> Any:
        try:
            r = self._c.get(path)
        except httpx.HTTPError as exc:
            raise GitHubError(f"{type(exc).__name__}: {exc}"[:200]) from exc
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise GitHubError(f"GitHub {r.status_code} for {path}")
        return r.json()

    def codeowners(self, repo: str) -> str:
        for p in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            data = self._get(f"/repos/{repo}/contents/{p}")
            if data and data.get("content"):
                return base64.b64decode(data["content"]).decode("utf-8", "replace")
        return ""

    def commit(self, repo: str, sha: str) -> CommitInfo | None:
        d = self._get(f"/repos/{repo}/commits/{sha}")
        if d is None:
            return None
        rules = codeowners.parse(self.codeowners(repo))
        files = [
            {
                "path": f["filename"],
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                "patch": (f.get("patch") or "")[:MAX_PATCH],
                "owners": codeowners.owners_for(rules, f["filename"]),
            }
            for f in d.get("files", [])[:MAX_FILES]
        ]
        owners = sorted({o for f in files for o in f["owners"]})
        c = d["commit"]
        return CommitInfo(
            repo,
            d["sha"],
            c["message"],
            (c.get("author") or {}).get("name"),
            (c.get("author") or {}).get("date"),
            d.get("html_url"),
            files,
            owners,
        )
