"""Commit cache (read-through) and CI run tracking."""

import json
from typing import Any

from sqlalchemy import Connection, text

from opspilot.integrations.github import CommitInfo, GitHubClient


def cached_commit(conn: Connection, repo: str, sha: str) -> dict[str, Any] | None:
    r = (
        conn.execute(
            text(
                "SELECT repo, sha, message, author, committed_at, url, files, owners FROM commits "
                "WHERE repo = :r AND sha = :s"
            ),
            {"r": repo, "s": sha},
        )
        .mappings()
        .first()
    )
    return dict(r) if r else None


def store_commit(conn: Connection, c: CommitInfo) -> None:
    conn.execute(
        text(
            "INSERT INTO commits (repo, sha, message, author, committed_at, url, files, owners) "
            "VALUES (:repo, :sha, :m, :a, :t, :u, CAST(:f AS jsonb), CAST(:o AS jsonb)) "
            "ON CONFLICT (repo, sha) DO NOTHING"
        ),
        {
            "repo": c.repo,
            "sha": c.sha,
            "m": c.message,
            "a": c.author,
            "t": c.committed_at,
            "u": c.url,
            "f": json.dumps(c.files),
            "o": json.dumps(c.owners),
        },
    )


def get_or_fetch_commit(
    conn: Connection, gh: GitHubClient, repo: str, sha: str
) -> dict[str, Any] | None:
    hit = cached_commit(conn, repo, sha)
    if hit:
        return hit
    fetched = gh.commit(repo, sha)
    if fetched is None:
        return None
    store_commit(conn, fetched)
    return cached_commit(conn, repo, fetched.sha)


def upsert_ci_run(conn: Connection, repo: str, run: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO ci_runs (id, repo, name, head_sha, status, conclusion, html_url) "
            "VALUES (:id, :repo, :name, :sha, :st, :co, :u) ON CONFLICT (id) DO UPDATE SET "
            "status = :st, conclusion = :co, updated_at = now()"
        ),
        {
            "id": run["id"],
            "repo": repo,
            "name": run.get("name") or "",
            "sha": run["head_sha"],
            "st": run["status"],
            "co": run.get("conclusion"),
            "u": run.get("html_url"),
        },
    )
