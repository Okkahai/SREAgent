import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shop.common import install_faults
from shop.faults import FaultRegistry


def make() -> tuple[TestClient, FaultRegistry]:
    faults = FaultRegistry()
    app = FastAPI()
    install_faults(app, faults)

    @app.get("/work")
    def work() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app), faults


def test_unknown_fault_rejected() -> None:
    client, _ = make()
    assert client.put("/_faults/nope").status_code == 404


def test_down_returns_503_but_health_stays_up() -> None:
    client, _ = make()
    assert client.get("/work").status_code == 200
    assert client.put("/_faults/down").status_code == 200
    assert client.get("/work").status_code == 503
    assert client.get("/healthz").status_code == 200
    client.delete("/_faults")
    assert client.get("/work").status_code == 200


def test_http_500_rate() -> None:
    client, _ = make()
    client.put("/_faults/http_500", json={"rate": 1.0})
    assert client.get("/work").status_code == 500
    client.delete("/_faults", params={"name": "http_500"})
    assert client.get("/work").status_code == 200


def test_memory_spike_allocates_and_releases() -> None:
    faults = FaultRegistry()
    faults.set("memory_spike", {"mb": 1})
    assert len(faults._ballast) == 1
    faults.clear("memory_spike")
    assert faults._ballast == []


def test_registry_rejects_unknown() -> None:
    with pytest.raises(KeyError):
        FaultRegistry().set("bogus")
