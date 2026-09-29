import logging
import os
import uuid

import httpx
from fastapi import FastAPI, HTTPException
from opentelemetry import metrics
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.metrics import CallbackOptions, Observation
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from shop.common import install_faults
from shop.faults import FaultRegistry
from shop.otel import setup_otel

setup_otel("checkout")
log = logging.getLogger("checkout")
faults = FaultRegistry()

DATABASE_URL = os.environ.get(
    "SHOP_DATABASE_URL", "postgresql+psycopg://shop:shop@shop-db:5432/shop"
)
PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://payments:8000")
# The deployable knob a "bad deployment" changes: too small a pool exhausts under load.
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "20"))
POOL_TIMEOUT_S = float(os.environ.get("DB_POOL_TIMEOUT_S", "1"))
DB_WORK_S = float(os.environ.get("DB_WORK_S", "0.1"))  # simulated query work per order

engine = create_engine(
    DATABASE_URL, pool_size=POOL_SIZE, max_overflow=0, pool_timeout=POOL_TIMEOUT_S
)
SQLAlchemyInstrumentor().instrument(engine=engine)
HTTPXClientInstrumentor().instrument()
client = httpx.Client(timeout=3.0)


def _pool_in_use(_: CallbackOptions) -> list[Observation]:
    return [Observation(engine.pool.checkedout(), {"state": "used"})]  # type: ignore[attr-defined]


def _pool_max(_: CallbackOptions) -> list[Observation]:
    return [Observation(POOL_SIZE, {"state": "max"})]


_meter = metrics.get_meter("checkout")
_meter.create_observable_gauge("db.client.connection.count", [_pool_in_use], unit="{connection}")
_meter.create_observable_gauge("db.client.connection.max", [_pool_max], unit="{connection}")

app = FastAPI(title="checkout")
install_faults(app, faults)


@app.on_event("startup")
def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS orders (id text PRIMARY KEY, sku text, "
                "amount_cents int, created_at timestamptz DEFAULT now())"
            )
        )
    log.info("checkout started pool_size=%d", POOL_SIZE)


class Order(BaseModel):
    sku: str
    amount_cents: int


@app.post("/checkout")
def checkout(order: Order) -> dict[str, str]:
    order_id = uuid.uuid4().hex
    slow = faults.get("db_timeout")
    try:
        with engine.begin() as conn:  # holds one pooled connection for the whole block
            if slow:
                conn.execute(
                    text(f"SET LOCAL statement_timeout = {int(slow['statement_timeout_ms'])}")
                )
                conn.execute(text("SELECT pg_sleep(:s)"), {"s": float(slow["seconds"])})
            else:
                conn.execute(text("SELECT pg_sleep(:s)"), {"s": DB_WORK_S})
            conn.execute(
                text("INSERT INTO orders (id, sku, amount_cents) VALUES (:i, :s, :a)"),
                {"i": order_id, "s": order.sku, "a": order.amount_cents},
            )
    except PoolTimeout:
        log.error(
            "database connection pool exhausted: QueuePool limit of size %d reached, "
            "connection timed out after %.0fs",
            POOL_SIZE,
            POOL_TIMEOUT_S,
        )
        raise HTTPException(503, "database unavailable") from None
    except DBAPIError as exc:
        log.error("database error during checkout: %s", str(exc.orig).splitlines()[0])
        raise HTTPException(504, "database timeout") from None

    try:
        resp = client.post(
            f"{PAYMENTS_URL}/charge",
            json={"order_id": order_id, "amount_cents": order.amount_cents},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.error("payment failed for order %s: %s", order_id, exc)
        raise HTTPException(502, "payment failed") from None
    log.info("order %s completed", order_id)
    return {"order_id": order_id, "status": "confirmed"}
