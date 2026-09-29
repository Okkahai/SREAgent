"""Deterministic detection rules (docs/06 §4). Pure functions over aggregated windows.

Detection is intentionally not AI: it must be cheap, testable and reliable. Each rule returns a
Verdict: BREACH (unhealthy), OK (healthy) or NO_DATA (not enough traffic to judge either way).
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from opspilot.domain.incident import Severity


class Kind(StrEnum):
    BREACH = "BREACH"
    OK = "OK"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class DetectionConfig:
    window_minutes: int = 2
    baseline_minutes: int = 60
    min_requests: int = 20
    error_floor: float = 0.02  # never alert below 2% errors
    error_multiplier: float = 3.0  # ...and require 3x the service's own baseline
    baseline_cap: float = 0.05  # a "baseline" above 5% is itself an outage; do not learn it
    latency_multiplier: float = 2.0
    latency_floor_ms: float = 500.0
    saturation_threshold: float = 0.9
    min_saturation_points: int = 4
    recovery_minutes: int = 10
    reopen_minutes: int = 30
    deploy_link_minutes: int = 15


DEFAULT_CONFIG = DetectionConfig()


@dataclass(frozen=True)
class WindowStats:
    requests: int
    errors: int
    p95_ms: float | None = None

    @property
    def error_rate(self) -> float | None:
        return self.errors / self.requests if self.requests else None


@dataclass(frozen=True)
class Verdict:
    kind: Kind
    severity: Severity | None = None
    title: str = ""
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)


NO_DATA = Verdict(Kind.NO_DATA)
OK = Verdict(Kind.OK)


def error_rate_severity(rate: float) -> Severity:
    if rate >= 0.5:
        return Severity.CRITICAL
    if rate >= 0.2:
        return Severity.HIGH
    if rate >= 0.05:
        return Severity.MEDIUM
    return Severity.LOW


def evaluate_error_rate(
    service: str,
    current: WindowStats,
    baseline_rate: float | None,
    cfg: DetectionConfig = DEFAULT_CONFIG,
) -> Verdict:
    rate = current.error_rate
    if current.requests < cfg.min_requests or rate is None:
        return NO_DATA
    base = min(baseline_rate or 0.0, cfg.baseline_cap)
    threshold = max(cfg.error_floor, cfg.error_multiplier * base)
    details = {
        "window_minutes": cfg.window_minutes,
        "requests": current.requests,
        "errors": current.errors,
        "error_rate": round(rate, 4),
        "baseline_error_rate": round(base, 4),
        "threshold": round(threshold, 4),
    }
    if rate < threshold:
        return Verdict(Kind.OK, details=details)
    return Verdict(
        Kind.BREACH,
        error_rate_severity(rate),
        f"{service}: error rate {rate:.1%} (baseline {base:.1%})",
        f"{current.errors} of {current.requests} requests failed in the last "
        f"{cfg.window_minutes} min; threshold {threshold:.1%}",
        details,
    )


def evaluate_latency(
    service: str,
    current: WindowStats,
    baseline_p95_ms: float | None,
    cfg: DetectionConfig = DEFAULT_CONFIG,
) -> Verdict:
    if current.requests < cfg.min_requests or current.p95_ms is None:
        return NO_DATA
    threshold = max(cfg.latency_floor_ms, cfg.latency_multiplier * (baseline_p95_ms or 0.0))
    details = {
        "window_minutes": cfg.window_minutes,
        "requests": current.requests,
        "p95_ms": round(current.p95_ms, 1),
        "baseline_p95_ms": round(baseline_p95_ms, 1) if baseline_p95_ms else None,
        "threshold_ms": round(threshold, 1),
    }
    if current.p95_ms < threshold:
        return Verdict(Kind.OK, details=details)
    severe = current.p95_ms >= 5 * threshold
    return Verdict(
        Kind.BREACH,
        Severity.HIGH if severe else Severity.MEDIUM,
        f"{service}: p95 latency {current.p95_ms:.0f} ms (threshold {threshold:.0f} ms)",
        f"p95 over the last {cfg.window_minutes} min exceeds {threshold:.0f} ms",
        details,
    )


def evaluate_saturation(
    service: str,
    used_avg: float | None,
    limit: float | None,
    points: int,
    cfg: DetectionConfig = DEFAULT_CONFIG,
) -> Verdict:
    if used_avg is None or not limit or points < cfg.min_saturation_points:
        return NO_DATA
    ratio = used_avg / limit
    details = {
        "window_minutes": cfg.window_minutes,
        "pool_used_avg": round(used_avg, 2),
        "pool_max": limit,
        "utilisation": round(ratio, 3),
        "threshold": cfg.saturation_threshold,
    }
    if ratio < cfg.saturation_threshold:
        return Verdict(Kind.OK, details=details)
    return Verdict(
        Kind.BREACH,
        Severity.HIGH if ratio >= 1.0 else Severity.MEDIUM,
        f"{service}: database connection pool at {ratio:.0%}",
        f"average {used_avg:.1f} of {limit:.0f} connections in use over the last "
        f"{cfg.window_minutes} min",
        details,
    )
