import itertools

import pytest

from opspilot.domain.incident import Event, InvalidTransition, Status, is_open, transition


def test_happy_path_lifecycle() -> None:
    s = Status.DETECTED
    for ev, expected in [
        (Event.INVESTIGATION_STARTED, Status.INVESTIGATING),
        (Event.ROOT_CAUSE_FOUND, Status.IDENTIFIED),
        (Event.ACTION_STARTED, Status.MITIGATING),
        (Event.ACTION_DONE, Status.MONITORING),
        (Event.RECOVERED, Status.RESOLVED),
        (Event.CLOSE, Status.CLOSED),
    ]:
        s = transition(s, ev)
        assert s is expected


def test_recovery_and_relapse() -> None:
    for open_status in (
        Status.DETECTED,
        Status.INVESTIGATING,
        Status.IDENTIFIED,
        Status.MITIGATING,
    ):
        assert transition(open_status, Event.RECOVERING) is Status.MONITORING
        assert transition(open_status, Event.BREACH) is open_status
    assert transition(Status.MONITORING, Event.BREACH) is Status.DETECTED
    assert transition(Status.RESOLVED, Event.BREACH) is Status.DETECTED


@pytest.mark.parametrize(
    ("status", "event"),
    [
        (Status.DETECTED, Event.RECOVERED),
        (Status.DETECTED, Event.CLOSE),
        (Status.INVESTIGATING, Event.ACTION_STARTED),
        (Status.MONITORING, Event.INVESTIGATION_STARTED),
        (Status.RESOLVED, Event.RECOVERING),
        (Status.CLOSED, Event.BREACH),
        (Status.CLOSED, Event.CLOSE),
    ],
)
def test_illegal_transitions_rejected(status: Status, event: Event) -> None:
    with pytest.raises(InvalidTransition):
        transition(status, event)


def test_closed_is_terminal_and_only_resolved_can_close() -> None:
    for ev in Event:
        with pytest.raises(InvalidTransition):
            transition(Status.CLOSED, ev)
    can_close = [s for s, e in itertools.product(Status, Event) if e is Event.CLOSE and _ok(s, e)]
    assert can_close == [Status.RESOLVED]


def _ok(s: Status, e: Event) -> bool:
    try:
        transition(s, e)
    except InvalidTransition:
        return False
    return True


def test_is_open() -> None:
    assert (
        is_open(Status.MONITORING) and not is_open(Status.RESOLVED) and not is_open(Status.CLOSED)
    )
