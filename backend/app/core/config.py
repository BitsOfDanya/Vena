from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VENA_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Vena API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    cors_origins: list[AnyHttpUrl] = [AnyHttpUrl("http://localhost:3000")]
    ml_dir: Path = Path(__file__).resolve().parents[3] / "ml"
    database_url: str = "postgresql+psycopg://vena:vena@localhost:5432/vena"
    timezone: str = "Europe/Moscow"
    public_url: str = "http://localhost:3100"
    seed_demo: bool = True
    digest_enabled: bool = True
    prediction_stale_seconds: int = 86_400
    prediction_critical_limit: int = 20
    prediction_cooldown_minutes: int = 240
    # The stream worker publishes a snapshot within seconds of an event batch;
    # polling every 30 s keeps the end-to-end delay well under 300 s.
    prediction_refresh_seconds: int = 30
    # Spool directory shared with the ML stream worker; unset disables event intake.
    inbox_dir: Path | None = None
    ingest_on_startup: bool = True
    auth_enabled: bool = False
    jwt_secret: str = ""
    jwt_issuer: str = "vena"
    jwt_audience: str = "vena-api"
    jwt_ttl_minutes: int = Field(default=60, ge=1, le=1440)
    auth_login_limit: int = Field(default=10, ge=1)
    auth_login_window_seconds: int = Field(default=300, ge=1)
    smtp_host: str = Field(default="", validation_alias=AliasChoices("SMTP_HOST", "VENA_SMTP_HOST"))
    smtp_port: int = Field(
        default=587, validation_alias=AliasChoices("SMTP_PORT", "VENA_SMTP_PORT")
    )
    smtp_username: str = Field(
        default="", validation_alias=AliasChoices("SMTP_USERNAME", "VENA_SMTP_USERNAME")
    )
    smtp_password: str = Field(
        default="", validation_alias=AliasChoices("SMTP_PASSWORD", "VENA_SMTP_PASSWORD")
    )
    smtp_from: str = Field(default="", validation_alias=AliasChoices("SMTP_FROM", "VENA_SMTP_FROM"))
    smtp_tls: bool = Field(default=True, validation_alias=AliasChoices("SMTP_TLS", "VENA_SMTP_TLS"))

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()
