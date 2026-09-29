from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from opspilot import __version__
from opspilot.api import health, incidents, ingest, platform
from opspilot.config import get_settings
from opspilot.logging import configure_logging
from opspilot.telemetry import setup_tracing


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.opspilot_log_level)
    setup_tracing("opspilot-api", settings.otel_exporter_otlp_endpoint, settings.opspilot_env)

    app = FastAPI(title="OpsPilot API", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(platform.router)
    app.include_router(incidents.router)
    # Exclude ingest from self-tracing: OpsPilot's own telemetry must not feed back into itself.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="v1/otlp,healthz,readyz")
    return app


app = create_app()
