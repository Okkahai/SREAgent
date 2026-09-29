from opspilot.agent.llm import redact
from opspilot.agent.verifier import confidence_cap, verify

EV = {"a": "METRIC", "b": "LOG", "c": "DEPLOYMENT", "d": "LOG"}


def hyp(**kw):
    return {
        "statement": "s",
        "category": "CODE",
        "confidence": 0.95,
        "evidence_ids": ["a", "b", "d"],
        **kw,
    }


def test_unknown_evidence_ids_reject_hypothesis():
    v = verify({"summary": "x", "hypotheses": [hyp(evidence_ids=["nope"])], "unknowns": []}, EV)
    assert v.hypotheses == [] and len(v.rejected) == 1


def test_confidence_is_capped_by_evidence():
    assert confidence_cap({"LOG"}, 1) == 0.4
    assert confidence_cap({"LOG"}, 2) == 0.5
    assert confidence_cap({"LOG", "METRIC"}, 2) == 0.7
    assert confidence_cap({"LOG", "METRIC"}, 3) == 0.9
    v = verify({"summary": "", "hypotheses": [hyp(evidence_ids=["b"])], "unknowns": []}, EV)
    assert v.hypotheses[0]["confidence"] == 0.4
    v = verify({"summary": "", "hypotheses": [hyp()], "unknowns": []}, EV)
    assert v.hypotheses[0]["confidence"] == 0.9


def test_ai_cannot_claim_confirmed_fact():
    v = verify({"summary": "", "hypotheses": [hyp(level="CONFIRMED_FACT")], "unknowns": []}, EV)
    assert v.hypotheses[0]["level"] == "HYPOTHESIS"


def test_deployment_blame_needs_deployment_evidence():
    h = hyp(category="DEPLOYMENT", evidence_ids=["a", "b"])
    assert verify({"summary": "", "hypotheses": [h], "unknowns": []}, EV).hypotheses == []
    h = hyp(category="DEPLOYMENT", evidence_ids=["a", "c"])
    assert len(verify({"summary": "", "hypotheses": [h], "unknowns": []}, EV).hypotheses) == 1


def test_redact_strips_secrets_and_emails():
    out = redact("Authorization: Bearer abcdefghijkl user bob@example.com api_key=supersecret1")
    assert "abcdefghijkl" not in out and "bob@example.com" not in out and "supersecret1" not in out
