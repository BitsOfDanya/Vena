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
    database_url: str = "postgresql+psycopg://vena:vena_local@localhost:5433/vena"
    upload_dir: Path = Path("./data/uploads")
    jwt_secret: str = "local-development-secret-change-me"
    dispatcher_invite_code: str = ""
    auth_cookie_secure: bool = False
    max_upload_mb: int = 25
    timezone: str = "Europe/Moscow"
    public_url: str = "http://localhost:3100"
    seed_demo: bool = False
    digest_enabled: bool = True
    prediction_stale_seconds: int = 86_400
    prediction_critical_limit: int = 20
    prediction_cooldown_minutes: int = 240
    prediction_refresh_minutes: int = 15
    ingest_on_startup: bool = True
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
