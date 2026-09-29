"""Steady synthetic traffic against the gateway. Real requests, real telemetry."""

import os
import random
import threading
import time

import httpx

TARGET = os.environ.get("TARGET_URL", "http://gateway:8000")
RPS = float(os.environ.get("LOAD_RPS", "30"))
WORKERS = int(os.environ.get("LOAD_WORKERS", "16"))


def worker(interval: float) -> None:
    with httpx.Client(timeout=8.0) as client:
        while True:
            start = time.monotonic()
            try:
                if random.random() < 0.2:
                    client.get(f"{TARGET}/products")
                else:
                    client.post(f"{TARGET}/checkout", json={})
            except httpx.HTTPError:
                pass
            time.sleep(max(0.0, interval - (time.monotonic() - start)))


def main() -> None:
    interval = WORKERS / RPS
    print(f"loadgen: {RPS} rps with {WORKERS} workers -> {TARGET}", flush=True)
    for _ in range(WORKERS):
        threading.Thread(target=worker, args=(interval,), daemon=True).start()
        time.sleep(interval / WORKERS)
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
