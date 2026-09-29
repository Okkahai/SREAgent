import logging
import os
import random

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from pydantic import BaseModel

from shop.common import install_faults
from shop.faults import FaultRegistry
from shop.otel import setup_otel

setup_otel("gateway")
log = logging.getLogger("gateway")
faults = FaultRegistry()
CHECKOUT_URL = os.environ.get("CHECKOUT_URL", "http://checkout:8000")
HTTPXClientInstrumentor().instrument()
client = httpx.Client(timeout=5.0)
app = FastAPI(title="gateway")
install_faults(app, faults)

CATALOG = [
    {"sku": "book-001", "price_cents": 1999},
    {"sku": "mug-002", "price_cents": 899},
    {"sku": "tee-003", "price_cents": 2499},
]


class Cart(BaseModel):
    sku: str | None = None


@app.get("/products")
def products() -> list[dict[str, object]]:
    return CATALOG


@app.post("/checkout")
def checkout(cart: Cart) -> dict[str, str]:
    item = next((i for i in CATALOG if i["sku"] == cart.sku), random.choice(CATALOG))
    try:
        resp = client.post(
            f"{CHECKOUT_URL}/checkout",
            json={"sku": item["sku"], "amount_cents": item["price_cents"]},
        )
    except httpx.HTTPError as exc:
        log.error("checkout upstream unreachable: %s", exc)
        raise HTTPException(502, "checkout unreachable") from None
    if resp.status_code >= 400:
        log.error("checkout returned %d", resp.status_code)
        raise HTTPException(resp.status_code, "checkout failed")
    return resp.json()
