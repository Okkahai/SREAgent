import json
from typing import Any

from opspilot.agent.heuristic import PLAN, HeuristicInvestigator, analyze
from opspilot.agent.llm import Final, ToolCall
from opspilot.agent.verifier import verify


def hist(**tools: Any) -> list[tuple[ToolCall, str]]:
    """History as the runner builds it: each tool result carries its evidence id."""
    return [
        (ToolCall(n, n, {}), json.dumps({"evidence_id": f"ev-{n}", "untrusted_data": d}))
        for n, d in tools.items()
    ]


SEEN = {f"ev-{n}": t for n, t in [
    ("pool_saturation", "METRIC"), ("error_rate_series", "METRIC"), ("error_logs", "LOG"),
    ("error_spans", "TRACE"), ("errors_by_version", "TRACE"), ("recent_deployments", "DEPLOYMENT"),
]}  # fmt: skip


def cats(out: dict[str, Any]) -> list[str]:
    return [h["category"] for h in verify(out, SEEN).hypotheses]


def test_plan_then_final() -> None:
    inv = HeuristicInvestigator()
    h: list[tuple[ToolCall, str]] = []
    for name in PLAN:
        step = inv.step("", "", h, [])
        assert isinstance(step, ToolCall) and step.name == name
        h.append((step, "unavailable: x"))
    final = inv.step("", "", h, [])
    assert isinstance(final, Final) and final.output["hypotheses"] == []
    assert any("unavailable" in u for u in final.output["unknowns"])


def test_saturated_pool_is_a_resource_hypothesis() -> None:
    out = analyze(
        hist(
            pool_saturation=[{"used": 9.8, "pool_max": 10}],
            error_rate_series=[{"errors": 5}],
            error_logs=[{"pattern": "QueuePool limit reached", "occurrences": 9}],
        )
    )
    assert cats(out) == ["RESOURCE"]
    (h,) = verify(out, SEEN).hypotheses
    assert h["confidence"] <= 0.9 and len(h["evidence_ids"]) == 3


def test_healthy_pool_gives_no_hypothesis() -> None:
    out = analyze(hist(pool_saturation=[{"used": 2, "pool_max": 10}]))
    assert out["hypotheses"] == [] and "no rule matched" in " ".join(out["unknowns"])


def test_new_version_concentration_is_deployment_correlation() -> None:
    dep = [{"version": "1.1.0", "same_service": True}]
    out = analyze(
        hist(
            recent_deployments=dep,
            errors_by_version=[
                {"deployment_version": "1.0.0", "server_spans": 100, "errors": 1},
                {"deployment_version": "1.1.0", "server_spans": 100, "errors": 40},
            ],
        )
    )
    assert cats(out) == ["DEPLOYMENT"] and "correlation" in out["hypotheses"][0]["reasoning"]


def test_dependency_failure_is_not_blamed_on_the_deploy() -> None:
    out = analyze(
        hist(
            recent_deployments=[{"version": "1.1.0", "same_service": True}],
            errors_by_version=[  # every version fails equally
                {"deployment_version": "1.0.0", "server_spans": 100, "errors": 30},
                {"deployment_version": "1.1.0", "server_spans": 100, "errors": 32},
            ],
            error_spans=[
                {"name": "POST payments", "kind": 3, "errors": 60, "status_message": "503"},
                {"name": "POST /checkout", "kind": 2, "errors": 10, "status_message": ""},
            ],
        )
    )
    assert cats(out) == ["DEPENDENCY"]


def test_never_recommends_actions() -> None:
    out = analyze(hist(pool_saturation=[{"used": 10, "pool_max": 10}]))
    assert "recommended_actions" not in out
