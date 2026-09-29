"""Helpers shared by every demo service: fault endpoints, latency/500/down middleware."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from shop.faults import KNOWN_FAULTS, FaultRegistry

log = logging.getLogger("shop")

EXEMPT_PREFIXES = ("/healthz", "/_faults")


def install_faults(app: FastAPI, faults: FaultRegistry) -> None:
    @app.middleware("http")
    async def fault_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)
        if faults.get("down") is not None:
            log.error("service is down (injected fault): rejecting %s", request.url.path)
            return JSONResponse({"error": "service unavailable"}, status_code=503)
        latency = faults.get("latency")
        if latency:
            await asyncio.sleep(float(latency["seconds"]))
        if faults.should_fail_http():
            log.error("injected internal error on %s", request.url.path)
            return JSONResponse({"error": "internal error"}, status_code=500)
        return await call_next(request)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/_faults")
    def list_faults() -> dict[str, Any]:
        return {"active": faults.snapshot(), "known": list(KNOWN_FAULTS)}

    @app.put("/_faults/{name}")
    def set_fault(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            active = faults.set(name, params)
        except KeyError:
            raise HTTPException(404, f"unknown fault {name!r}") from None
        log.warning("fault activated: %s %s", name, active)
        return {"active": name, "params": active}

    @app.delete("/_faults")
    def clear_faults(name: str | None = None) -> dict[str, str]:
        faults.clear(name)
        log.warning("fault cleared: %s", name or "all")
        return {"cleared": name or "all"}

    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,_faults")
