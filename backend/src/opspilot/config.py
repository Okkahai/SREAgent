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
    detection_recovery_minutes: int = 10
    # LLM provider for investigations. Without a key, investigations fail as retryable (detection is unaffected).
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"
    agent_max_steps: int = 8
    # Read-only GitHub access (contents/metadata/actions read). Empty disables commit evidence.
    github_token: str = ""
    github_repo: str = ""  # default "owner/name" for deployments that do not name a repository
    github_webhook_secret: str = ""
    max_ingest_bytes: int = 10 * 1024 * 1024
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
