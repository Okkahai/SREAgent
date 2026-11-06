# CLAUDE.md — Claude-specific notes

Shared rules live in [AGENTS.md](AGENTS.md); read it first. Current work state: [docs/agent/HANDOFF.md](docs/agent/HANDOFF.md). This file only adds what is specific to Claude Code.

- Follow every rule in AGENTS.md (invariants, branch-per-task, no merging, honest reporting).
- Reply to Gün in Turkish; write code, commits, PR text and docs in English.
- Gün prefers research answers to be checked against the current date (state the date you verified against).
- Cloud sandboxes usually have **no Docker daemon**: you cannot run `make up`, `demo-check`, `kind-*` or the prod compose there. Say so in the PR and rely on CI for those; never claim they passed.
- GitHub access in cloud sessions is via the GitHub MCP tools (no `gh`/direct API); append the Claude Code footer on GitHub posts and PR bodies as the session instructs.
- Prefer plain tools (Read/Grep/Edit) over broad shell exploration; keep diffs minimal and complete (callers, tests, fixtures, docs).
- Commit trailers (when the session requires attribution) go at the end of the commit message.
- If you are the reviewer of another agent's PR, do not edit their branch; post findings.
