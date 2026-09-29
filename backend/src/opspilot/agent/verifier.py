"""Deterministic verifier: the model proposes, this code decides what is kept and how confident it
may be. Pure functions, no I/O (docs/07 §5)."""

from dataclasses import dataclass, field
from typing import Any

from opspilot.domain.policy import PROPOSABLE

MAX_HYPOTHESES = 3
MAX_ACTIONS = 3
CATEGORIES = {"DEPLOYMENT", "DEPENDENCY", "RESOURCE", "CODE", "CONFIG", "UNKNOWN"}


@dataclass
class Verified:
    summary: str
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)


def confidence_cap(types: set[str], count: int) -> float:
    """Confidence is bounded by how much independent evidence backs a claim."""
    if len(types) >= 2:
        return 0.9 if count >= 3 else 0.7
    return 0.5 if count >= 2 else 0.4


def verify(output: dict[str, Any], evidence: dict[str, str]) -> Verified:
    """`evidence` maps evidence id -> signal type for OBSERVATIONS captured in this investigation.
    Anything not in it (invented ids, other incidents, prior hypotheses) does not count."""
    v = Verified(summary=str(output.get("summary", ""))[:1000])
    v.unknowns = [str(u)[:300] for u in output.get("unknowns", []) if isinstance(u, str)][:10]
    for h in output.get("hypotheses", []):
        if not isinstance(h, dict) or not str(h.get("statement", "")).strip():
            v.rejected.append("malformed hypothesis")
            continue
        statement = str(h["statement"]).strip()[:500]
        ids = list(dict.fromkeys(i for i in h.get("evidence_ids", []) if i in evidence))
        if not ids:
            v.rejected.append(f"no valid evidence: {statement[:80]}")
            continue
        types = {evidence[i] for i in ids}
        category = h.get("category") if h.get("category") in CATEGORIES else "UNKNOWN"
        if category == "DEPLOYMENT" and "DEPLOYMENT" not in types:
            v.rejected.append(f"deployment blamed without deployment evidence: {statement[:80]}")
            continue
        if category in ("CODE", "CONFIG") and "COMMIT" not in types:
            v.rejected.append(f"code/config cause without commit evidence: {statement[:80]}")
            continue
        try:
            claimed = float(h.get("confidence", 0))
        except (TypeError, ValueError):
            claimed = 0.0
        v.hypotheses.append(
            {
                "statement": statement,
                "category": category,
                "confidence": round(max(0.0, min(claimed, confidence_cap(types, len(ids)))), 2),
                "evidence_ids": ids,
                "reasoning": str(h.get("reasoning", ""))[:1000],
                "level": "HYPOTHESIS",  # the AI can never assert CONFIRMED_FACT
            }
        )
    if v.hypotheses:  # actions are only considered when a hypothesis survived verification
        for a in output.get("recommended_actions", []):
            if not isinstance(a, dict) or a.get("type") not in PROPOSABLE:
                v.rejected.append(f"action type not proposable: {str(a)[:60]}")
                continue
            params = a.get("parameters")
            v.actions.append(
                {
                    "type": a["type"],
                    "title": str(a.get("title", ""))[:200] or a["type"],
                    "rationale": str(a.get("rationale", ""))[:1000],
                    "parameters": params if isinstance(params, dict) else {},
                }
            )
        v.actions = v.actions[:MAX_ACTIONS]
    v.hypotheses.sort(key=lambda x: -x["confidence"])
    v.hypotheses = v.hypotheses[:MAX_HYPOTHESES]
    return v
