"""Rule-based investigator: the `LLM` port without a model, for running without an API key.

It calls a fixed set of read-only tools, then applies a few explicit rules to what they returned.
Everything still goes through the runner: evidence is captured server-side and the verifier caps
confidence, so it cannot claim more than the evidence allows. It has no free-form reasoning and never
recommends actions; it only reports patterns the data shows (OBSERVATION-backed HYPOTHESES)."""

import json
from typing import Any

from opspilot.agent.llm import Final, History, ToolCall

MODEL = "rules-v1"
PLAN = [
    "recent_deployments",
    "errors_by_version",
    "error_rate_series",
    "pool_saturation",
    "error_logs",
    "error_spans",
    "commit_changes",
]
POOL_SATURATED = 0.9
VERSION_RATIO = 3.0  # newest version must fail this many times more often than the others
MIN_ERROR_RATIO = 0.05
DEPENDENCY_SHARE = 0.6
CLIENT_KIND = 3  # OTLP SpanKind.CLIENT
POOL_WORDS = ("pool", "connection", "timeout")


def _parse(history: History) -> tuple[dict[str, str], dict[str, Any], list[str]]:
    """tool name -> evidence id, tool name -> data, tools that were unavailable."""
    ids: dict[str, str] = {}
    data: dict[str, Any] = {}
    missing: list[str] = []
    for call, text in history:
        try:
            body = json.loads(text)
            ids[call.name], data[call.name] = str(body["evidence_id"]), body["untrusted_data"]
        except (ValueError, KeyError, TypeError):
            missing.append(f"{call.name} unavailable ({text[:120]})")
    return ids, data, missing


def _cite(ids: dict[str, str], *names: str) -> list[str]:
    return [ids[n] for n in names if n in ids]


def _ratio(row: dict[str, Any]) -> float:
    return row["errors"] / row["server_spans"] if row["server_spans"] else 0.0


def analyze(history: History) -> dict[str, Any]:
    ids, data, missing = _parse(history)
    hyps: list[dict[str, Any]] = []
    unknowns = list(missing)

    pool = data.get("pool_saturation") or []
    peak = max((r.get("used") or 0 for r in pool), default=0)
    limit = max((r.get("pool_max") or 0 for r in pool), default=0)
    if not pool:
        unknowns.append("no DB connection pool metrics in the incident window")
    elif limit and peak / limit >= POOL_SATURATED:
        logs = [
            r
            for r in data.get("error_logs") or []
            if any(w in r["pattern"].lower() for w in POOL_WORDS)
        ]
        hyps.append(
            {
                "statement": f"The database connection pool is saturated (peak {peak:.1f} of {limit:.0f} in use).",
                "category": "RESOURCE",
                "confidence": 0.7,
                "evidence_ids": _cite(ids, "pool_saturation", "error_rate_series")
                + (_cite(ids, "error_logs") if logs else []),
                "reasoning": "Pool usage is at or above 90% of its maximum"
                + (f"; error logs mention it ({logs[0]['pattern'][:80]!r})." if logs else "."),
            }
        )

    deploys = [r for r in data.get("recent_deployments") or [] if r.get("same_service")]
    versions = data.get("errors_by_version") or []
    if deploys and len(versions) >= 2:
        newest = deploys[0]["version"]
        new = next((r for r in versions if r["deployment_version"] == newest), None)
        others = [r for r in versions if r is not new]
        old_errors, old_total = (
            sum(r["errors"] for r in others),
            sum(r["server_spans"] for r in others),
        )
        old_ratio = old_errors / old_total if old_total else 0.0
        if new and _ratio(new) >= MIN_ERROR_RATIO and _ratio(new) >= VERSION_RATIO * old_ratio:
            hyps.append(
                {
                    "statement": f"Errors are concentrated in the newly deployed version {newest} "
                    f"({new['errors']}/{new['server_spans']} failed vs {old_errors}/{old_total} on earlier versions).",
                    "category": "DEPLOYMENT",
                    "confidence": 0.6,
                    "evidence_ids": _cite(
                        ids, "recent_deployments", "errors_by_version", "commit_changes"
                    ),
                    "reasoning": "The version deployed shortly before onset fails much more often than the "
                    "others. This is a correlation; the cause inside the change is not established.",
                }
            )

    spans = data.get("error_spans") or []
    total = sum(r["errors"] for r in spans)
    client = [r for r in spans if r.get("kind") == CLIENT_KIND]
    if total and client and sum(r["errors"] for r in client) / total >= DEPENDENCY_SHARE:
        top = max(client, key=lambda r: r["errors"])
        hyps.append(
            {
                "statement": f"Failures come from an outbound dependency call: {top['name']!r} "
                f"({top['errors']} failed spans, {top['status_message'] or 'no status message'!r}).",
                "category": "DEPENDENCY",
                "confidence": 0.6,
                "evidence_ids": _cite(ids, "error_spans", "error_logs", "error_rate_series"),
                "reasoning": "Most failed spans are client calls to another service, so the fault is "
                "likely downstream rather than in this service's own code.",
            }
        )

    if not hyps:
        unknowns.append("no rule matched the telemetry in the window")
    unknowns.append(
        "rule-based investigator: no free-form reasoning, no code analysis, no actions proposed"
    )
    return {
        "summary": f"{len(hyps)} rule-based hypothesis(es)" if hyps else "inconclusive",
        "hypotheses": hyps,
        "unknowns": unknowns,
    }


class HeuristicInvestigator:
    model = MODEL

    def step(
        self, system: str, prompt: str, history: History, tools: list[dict[str, Any]]
    ) -> ToolCall | Final:
        if len(history) < len(PLAN):
            return ToolCall(f"rule-{len(history)}", PLAN[len(history)], {})
        return Final(analyze(history))
