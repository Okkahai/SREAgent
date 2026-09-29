"""In-process, reversible fault injection controlled over HTTP (`/_faults`).

Faults are deliberately simple and real: they change actual behaviour (errors, latency,
memory), so the resulting telemetry is genuine and not seeded.
"""

import random
import threading
from typing import Any

# name -> default parameters. A fault is active when present in the active map.
KNOWN_FAULTS: dict[str, dict[str, Any]] = {
    # HTTP 500 spike: fail `rate` (0..1) of requests.
    "http_500": {"rate": 0.4},
    # DB timeout: hold the connection for `seconds` with a statement timeout below that.
    "db_timeout": {"seconds": 2.0, "statement_timeout_ms": 500},
    # Memory spike: retain `mb` megabytes.
    "memory_spike": {"mb": 200},
    # Dependency failure: the service answers 503 to everything except health/faults.
    "down": {},
    # Added latency per request in seconds.
    "latency": {"seconds": 1.0},
}


class FaultRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, dict[str, Any]] = {}
        self._ballast: list[bytearray] = []

    def set(self, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if name not in KNOWN_FAULTS:
            raise KeyError(name)
        merged = {**KNOWN_FAULTS[name], **(params or {})}
        with self._lock:
            self._active[name] = merged
            if name == "memory_spike":
                self._ballast.append(bytearray(int(merged["mb"]) * 1024 * 1024))
        return merged

    def clear(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self._active.clear()
            else:
                self._active.pop(name, None)
            if name in (None, "memory_spike"):
                self._ballast.clear()

    def get(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            return self._active.get(name)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._active)

    def should_fail_http(self) -> bool:
        fault = self.get("http_500")
        return bool(fault) and random.random() < float(fault["rate"])
