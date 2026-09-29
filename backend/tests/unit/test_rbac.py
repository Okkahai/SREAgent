import pytest
from fastapi import HTTPException

from opspilot.api.deps import require_approver, require_viewer
from opspilot.config import Settings


def s(**kw: str) -> Settings:
    return Settings(**kw)  # type: ignore[arg-type]


def test_reads_open_without_viewer_token() -> None:
    require_viewer(s(), None)


def test_viewer_token_enforced() -> None:
    cfg = s(opspilot_viewer_token="v", opspilot_approver_token="a")
    require_viewer(cfg, "Bearer v")
    require_viewer(cfg, "Bearer a")  # approvers can read
    for bad in (None, "Bearer nope", "Bearer "):
        with pytest.raises(HTTPException) as e:
            require_viewer(cfg, bad)
        assert e.value.status_code == 401


def test_viewer_token_cannot_approve() -> None:
    cfg = s(opspilot_viewer_token="v", opspilot_approver_token="a")
    with pytest.raises(HTTPException) as e:
        require_approver(cfg, "Bearer v", "gun")
    assert e.value.status_code == 401
    assert require_approver(cfg, "Bearer a", "gun") == "gun"


def test_empty_approver_token_never_matches_viewer_gate() -> None:
    cfg = s(opspilot_viewer_token="v")
    with pytest.raises(HTTPException):
        require_viewer(cfg, "Bearer ")
