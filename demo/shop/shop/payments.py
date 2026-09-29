import logging
import random
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shop.common import install_faults
from shop.faults import FaultRegistry
from shop.otel import setup_otel

setup_otel("payments")
log = logging.getLogger("payments")
faults = FaultRegistry()
app = FastAPI(title="payments")
install_faults(app, faults)


class Charge(BaseModel):
    order_id: str
    amount_cents: int


@app.post("/charge")
def charge(body: Charge) -> dict[str, str]:
    time.sleep(random.uniform(0.01, 0.04))  # simulated card network latency
    if body.amount_cents <= 0:
        raise HTTPException(422, "invalid amount")
    log.info("charged order %s amount=%d", body.order_id, body.amount_cents)
    return {"status": "charged", "order_id": body.order_id}
