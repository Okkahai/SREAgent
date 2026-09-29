from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    opspilot_env: str = "dev"
    opspilot_log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://opspilot:opspilot_dev_password@localhost:5432/opspilot"
    )
    redis_url: str = "redis://localhost:6379/0"
    otel_exporter_otlp_endpoint: str | None = None
    # Safety kill-switch: no action executor may run unless explicitly enabled.
    opspilot_actions_enabled: bool = False
    # Bearer token required by the OTLP ingest and deployments write APIs. Empty disables them.
    opspilot_ingest_token: str = ""
    telemetry_retention_days: int = 7
    max_ingest_bytes: int = 10 * 1024 * 1024
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
