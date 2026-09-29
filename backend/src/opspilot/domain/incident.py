"""Incident domain: statuses, epistemic levels and the lifecycle state machine (docs/05).

Pure code, no I/O. `transition` is the only place that decides which status changes are legal.
"""

from enum import StrEnum


class Status(StrEnum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    IDENTIFIED = "IDENTIFIED"
    MITIGATING = "MITIGATING"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Level(StrEnum):
    """Every statement on an incident is exactly one of these (docs/01 §3)."""

    OBSERVATION = "OBSERVATION"
    HYPOTHESIS = "HYPOTHESIS"
    CONFIRMED_FACT = "CONFIRMED_FACT"


class Event(StrEnum):
    BREACH = "BREACH"  # detector sees the signal unhealthy
    RECOVERING = "RECOVERING"  # detector sees the signal healthy again
    RECOVERED = "RECOVERED"  # healthy for the whole recovery window
    INVESTIGATION_STARTED = "INVESTIGATION_STARTED"
    ROOT_CAUSE_FOUND = "ROOT_CAUSE_FOUND"
    ACTION_STARTED = "ACTION_STARTED"
    ACTION_DONE = "ACTION_DONE"
    CLOSE = "CLOSE"


S, E = Status, Event
_OPEN_UNHEALTHY = (S.DETECTED, S.INVESTIGATING, S.IDENTIFIED, S.MITIGATING)

_TRANSITIONS: dict[tuple[Status, Event], Status] = {
    (S.DETECTED, E.INVESTIGATION_STARTED): S.INVESTIGATING,
    (S.INVESTIGATING, E.ROOT_CAUSE_FOUND): S.IDENTIFIED,
    (S.IDENTIFIED, E.ACTION_STARTED): S.MITIGATING,
    (S.MITIGATING, E.ACTION_DONE): S.MONITORING,
    (S.MONITORING, E.RECOVERED): S.RESOLVED,
    (S.MONITORING, E.BREACH): S.DETECTED,  # relapse while monitoring
    (S.MONITORING, E.RECOVERING): S.MONITORING,
    (S.RESOLVED, E.BREACH): S.DETECTED,  # reopen (the detector decides whether it is allowed)
    (S.RESOLVED, E.CLOSE): S.CLOSED,
    **{(s, E.BREACH): s for s in _OPEN_UNHEALTHY},  # still failing: no change
    **{(s, E.RECOVERING): S.MONITORING for s in _OPEN_UNHEALTHY},
}


class InvalidTransition(ValueError):
    pass


def transition(status: Status, event: Event) -> Status:
    try:
        return _TRANSITIONS[(status, event)]
    except KeyError:
        raise InvalidTransition(f"{event} is not allowed in status {status}") from None


def is_open(status: Status) -> bool:
    return status not in (Status.RESOLVED, Status.CLOSED)
