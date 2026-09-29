from opspilot.domain.incident import Severity
from opspilot.services.detection import (
    Kind,
    WindowStats,
    error_rate_severity,
    evaluate_error_rate,
    evaluate_latency,
    evaluate_saturation,
)


def test_error_rate_breach_and_ok() -> None:
    breach = evaluate_error_rate("checkout", WindowStats(200, 60), 0.01)
    assert breach.kind is Kind.BREACH and breach.severity is Severity.HIGH
    assert "30.0%" in breach.title
    assert evaluate_error_rate("checkout", WindowStats(200, 2), 0.01).kind is Kind.OK


def test_error_rate_needs_traffic_and_respects_floor() -> None:
    assert evaluate_error_rate("s", WindowStats(5, 5), 0.0).kind is Kind.NO_DATA
    # 1.5% is above 3x a 0.4% baseline but below the 2% absolute floor
    assert evaluate_error_rate("s", WindowStats(1000, 15), 0.004).kind is Kind.OK


def test_poisoned_baseline_is_capped() -> None:
    # a service that was already at 40% errors must still alert at 50%
    assert evaluate_error_rate("s", WindowStats(100, 50), 0.4).kind is Kind.BREACH


def test_severity_bands() -> None:
    assert [error_rate_severity(r) for r in (0.01, 0.05, 0.2, 0.5)] == [
        Severity.LOW,
        Severity.MEDIUM,
        Severity.HIGH,
        Severity.CRITICAL,
    ]


def test_latency_rule() -> None:
    assert evaluate_latency("s", WindowStats(100, 0, 2000.0), 200.0).kind is Kind.BREACH
    assert evaluate_latency("s", WindowStats(100, 0, 300.0), 200.0).kind is Kind.OK  # under floor
    assert evaluate_latency("s", WindowStats(100, 0, None), 200.0).kind is Kind.NO_DATA


def test_saturation_rule() -> None:
    assert evaluate_saturation("s", 2.0, 2.0, 10).kind is Kind.BREACH
    assert evaluate_saturation("s", 3.0, 20.0, 10).kind is Kind.OK
    assert evaluate_saturation("s", 2.0, 2.0, 1).kind is Kind.NO_DATA
    assert evaluate_saturation("s", None, None, 0).kind is Kind.NO_DATA
