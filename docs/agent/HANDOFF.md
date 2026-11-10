# Handoff

Written 2026-11-06 when moving development from cloud Claude Code sessions to a local multi-agent setup (T3 Code with Claude Code and Codex CLI, git worktrees, independent reviewers, GitHub CI).

## Where things stand
- Product work is complete through roadmap Phases 1-10 plus PRs #11-#14. `main` @ `d022124`, CI green. No open PRs. No unmerged work on any remote branch.
- PR #15 (docs-only) added `AGENTS.md`, `CLAUDE.md` and `docs/agent/*`; Gün approved it on 2026-11-10 and it is merged to `main`. Nothing else changed.

## Do this next (exact)
1. Run **T-001** locally: fresh worktree, follow [VERIFICATION.md](VERIFICATION.md), record results in its "Local verification log".
2. When Gün has a server: **T-002**. Until then it stays BLOCKED.
3. Ask Gün for: domain (or IP-only test), Hetzner server, Market OS repo URL, and (for T-005) whether to supply an Anthropic key and a spend cap.

## Do not
- Start implementation work that is not in TASK_REGISTRY.md without asking.
- Merge anything, enable `OPSPILOT_ACTIONS_ENABLED`, or put real secrets in the repo.
- Assume the prod stack works: it has never run on a real server.

## Multi-agent setup suggestions (not yet configured)
- Worktree per task: `git worktree add ../sreagent-T-001 -b codex/T-001-verify-ci origin/main`.
- Author agent and reviewer agent should differ (for example Codex authors, Claude reviews). Reviewer reads the diff plus [AGENTS.md](../../AGENTS.md) invariants and the task's acceptance criteria.
- GitHub CI is the shared gate; the 10 jobs in `ci.yml` run on every PR.
- Consider a branch-protection rule requiring CI and one review on `main` [A: not verified whether it exists].

## Open questions
- Does Gün want IP-only HTTP for the first server test, or will a domain exist first?
- Is there a spend limit for live-LLM evaluation?
- Should T-004 (OIDC) happen before the app is exposed publicly, or are three shared tokens plus basic auth acceptable for the first deployment? (Current docs say acceptable with tokens mandatory when public.)
