import pytest

from opspilot.domain.policy import PROPOSABLE, RULES, decide, validate_parameters


@pytest.mark.parametrize(
    ("type_", "risk", "executable"),
    [
        ("OPEN_PR", "LOW", True),
        ("RUNBOOK", "READ_ONLY", False),
        ("ROLLBACK", "HIGH", False),
        ("RESTART", "HIGH", False),
        ("SCALE", "HIGH", False),
        ("CONFIG_CHANGE", "HIGH", False),
        ("MERGE_PR", "DESTRUCTIVE", False),
        ("DB_OPERATION", "DESTRUCTIVE", False),
        ("unknown-thing", "DESTRUCTIVE", False),
    ],
)
def test_policy_table(type_, risk, executable):
    d = decide(type_)
    assert (d.risk, d.executable) == (risk, executable)
    assert d.requires_approval == (risk != "READ_ONLY")


def test_destructive_actions_are_never_proposable_or_executable():
    assert not any(RULES[t].executable for t in RULES if RULES[t].risk in ("HIGH", "DESTRUCTIVE"))
    assert not {"MERGE_PR", "DB_OPERATION", "INFRA_CHANGE"} & PROPOSABLE


def ok(path="app/db.py"):
    return {"files": [{"path": path, "content": "POOL = 20\n"}]}


def test_pr_parameter_validation():
    assert validate_parameters("OPEN_PR", ok()) == []
    for bad in (".github/workflows/ci.yml", "../etc/passwd", "/abs", "x/CODEOWNERS", ".env"):
        assert validate_parameters("OPEN_PR", ok(bad)), bad
    assert validate_parameters("OPEN_PR", {})
    assert validate_parameters("OPEN_PR", {"files": [{"path": "a", "content": "x" * 30000}]})
    assert validate_parameters("OPEN_PR", {"files": [ok()["files"][0]] * 6})
