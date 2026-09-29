"""Detector: evaluates the rules for every service and drives the incident lifecycle.

`evaluate(now)` is deterministic given the database state and `now`, which is what makes the
whole detection path unit/integration testable without waiting on wall-clock time.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Engine

from opspilot.adapters import postgres_incidents as q
from opspilot.domain.incident import Event, Status, transition
from opspilot.services.detection import (
    DetectionConfig,
    Kind,
    Verdict,
    evaluate_error_rate,
    evaluate_latency,
    evaluate_saturation,
)

log = logging.getLogger(__name__)
SOURCE = "detector"


class Detector:
    def __init__(self, engine: Engine, cfg: DetectionConfig | None = None) -> None:
        self.engine = engine
        self.cfg = cfg or DetectionConfig()

    def evaluate(self, now: datetime) -> None:
        cfg = self.cfg
        with self.engine.connect() as conn:
            targets = q.service_targets(conn)
        for svc in targets:
            with self.engine.connect() as conn:
                win_start = now - timedelta(minutes=cfg.window_minutes)
                cur = q.window_stats(conn, svc["id"], win_start, now)
                base_rate, base_p95 = q.baseline(
                    conn, svc["id"], now - timedelta(minutes=cfg.baseline_minutes), win_start
                )
                used, limit, points = q.pool_stats(conn, svc["id"], win_start, now)
            verdicts = {
                "error_rate": evaluate_error_rate(svc["name"], cur, base_rate, cfg),
                "latency": evaluate_latency(svc["name"], cur, base_p95, cfg),
                "saturation": evaluate_saturation(svc["name"], used, limit, points, cfg),
            }
            for rule, verdict in verdicts.items():
                if verdict.kind is Kind.NO_DATA:
                    continue
                with self.engine.begin() as conn:
                    self._apply(conn, svc, rule, verdict, now)

    # -- lifecycle ------------------------------------------------------------------------
    def _apply(
        self, conn: Connection, svc: dict[str, Any], rule: str, v: Verdict, now: datetime
    ) -> None:
        fingerprint = f"{rule}:{svc['name']}:{svc['environment']}"
        inc = q.find_open(conn, fingerprint)
        if v.kind is Kind.BREACH:
            if inc:
                self._still_breaching(conn, inc, v, now)
            else:
                self._open_or_reopen(conn, svc, rule, fingerprint, v, now)
        elif inc:
            self._recovering(conn, inc, now)

    def _still_breaching(
        self, conn: Connection, inc: dict[str, Any], v: Verdict, now: datetime
    ) -> None:
        new = transition(Status(inc["status"]), Event.BREACH)
        q.update_incident(conn, inc["id"], status=new.value, last_breach_at=now, healthy_since=None)
        if new.value != inc["status"]:
            q.add_event(
                conn,
                inc["id"],
                now,
                "STATE_CHANGE",
                SOURCE,
                f"signal degraded again during {inc['status']}; back to {new.value}",
                ref=v.details,
            )

    def _open_or_reopen(
        self,
        conn: Connection,
        svc: dict[str, Any],
        rule: str,
        fingerprint: str,
        v: Verdict,
        now: datetime,
    ) -> None:
        cfg = self.cfg
        assert v.severity is not None
        started = self._estimate_onset(conn, svc, rule, v, now)
        dep = q.correlate_deployment(
            conn, svc["id"], svc["environment"], started, cfg.deploy_link_minutes
        )
        dep_id = dep["id"] if dep else None

        last = q.latest_resolved(conn, fingerprint)
        if (
            last
            and last["resolved_at"]
            and now - last["resolved_at"] <= timedelta(minutes=cfg.reopen_minutes)
            and last["deployment_id"] == dep_id
        ):
            transition(Status.RESOLVED, Event.BREACH)
            q.update_incident(
                conn,
                last["id"],
                status=Status.DETECTED.value,
                resolved_at=None,
                outcome=None,
                last_breach_at=now,
                healthy_since=None,
            )
            q.add_event(
                conn,
                last["id"],
                now,
                "STATE_CHANGE",
                SOURCE,
                "REOPENED: same signal breached again shortly after resolution",
                ref=v.details,
            )
            return

        inc = q.create_incident(
            conn,
            title=v.title,
            severity=v.severity.value,
            service_id=svc["id"],
            deployment_id=dep_id,
            environment=svc["environment"],
            rule=rule,
            fingerprint=fingerprint,
            started_at=min(started, now),
            detected_at=now,
        )
        iid = inc["id"]
        if dep:
            scope = "" if dep["same_service"] else f" (different service: {dep['service']})"
            q.add_event(
                conn,
                iid,
                dep["started_at"],
                "DEPLOYMENT",
                "deploy-api",
                f"deployment {dep['version']} of {dep['service']} started{scope}",
                ref={
                    "deployment_id": dep["id"],
                    "version": dep["version"],
                    "commit_sha": dep["commit_sha"],
                },
            )
        q.add_event(conn, iid, started, "METRIC_ANOMALY", SOURCE, v.summary, ref=v.details)
        q.add_event(
            conn,
            iid,
            now,
            "STATE_CHANGE",
            SOURCE,
            f"incident {inc['short_id']} created ({v.severity.value}), status DETECTED",
        )
        q.add_evidence(
            conn,
            iid,
            "METRIC",
            v.summary,
            {"rule": rule, "service": svc["name"], **v.details},
            captured_query=f"rule={rule} window={cfg.window_minutes}m source=service_metrics_1m/metric_points",
        )
        log.info("incident opened: %s %s", inc["short_id"], v.title)

    def _recovering(self, conn: Connection, inc: dict[str, Any], now: datetime) -> None:
        status = Status(inc["status"])
        if status is not Status.MONITORING:
            new = transition(status, Event.RECOVERING)
            q.update_incident(conn, inc["id"], status=new.value, healthy_since=now)
            q.add_event(
                conn,
                inc["id"],
                now,
                "STATE_CHANGE",
                SOURCE,
                f"signal healthy again; {status.value} -> {new.value}",
            )
            return
        since = inc["healthy_since"]
        if since is None:
            q.update_incident(conn, inc["id"], healthy_since=now)
            return
        if now - since >= timedelta(minutes=self.cfg.recovery_minutes):
            transition(status, Event.RECOVERED)
            outcome = {
                "result": "RECOVERED_SELF",  # no action executed yet; becomes RECOVERED_AFTER_ACTION in Phase 7
                "recovered_at": since.isoformat(),
                "mttd_s": int((inc["detected_at"] - inc["started_at"]).total_seconds()),
                "mttr_s": int((since - inc["started_at"]).total_seconds()),
            }
            q.update_incident(
                conn, inc["id"], status=Status.RESOLVED.value, resolved_at=since, outcome=outcome
            )
            q.add_event(
                conn,
                inc["id"],
                now,
                "STATE_CHANGE",
                SOURCE,
                f"healthy for {self.cfg.recovery_minutes} min; incident RESOLVED",
                ref=outcome,
            )

    def _estimate_onset(
        self, conn: Connection, svc: dict[str, Any], rule: str, v: Verdict, now: datetime
    ) -> datetime:
        default = now - timedelta(minutes=self.cfg.window_minutes)
        if rule == "error_rate":
            t = q.onset_error_rate(
                conn, svc["id"], now - timedelta(minutes=15), float(v.details["threshold"])
            )
            if t:
                return min(t, now)
        return default
