from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr
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
    prediction_refresh_seconds: int = 30
    inbox_dir: Path | None = None
    ingest_on_startup: bool = True
    auth_enabled: bool = False
    jwt_secret: str = ""
    jwt_issuer: str = "vena"
    jwt_audience: str = "vena-api"
    jwt_ttl_minutes: int = Field(default=60, ge=1, le=1440)
    auth_login_limit: int = Field(default=10, ge=1)
    auth_login_window_seconds: int = Field(default=300, ge=1)
    ldap_enabled: bool = False
    ldap_url: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: SecretStr = SecretStr("")
    ldap_base_dn: str = ""
    ldap_user_filter: str = (
        "(|(uid={login})(mail={login})(sAMAccountName={login})(userPrincipalName={login}))"
    )
    ldap_username_attribute: str = "sAMAccountName"
    ldap_id_attribute: str = "objectGUID"
    ldap_group_roles: dict[str, Literal["viewer", "dispatcher", "admin"]] = {}
    ldap_default_role: Literal["viewer", "dispatcher", "none"] = "viewer"
    ldap_ca_file: str | None = None
    ldap_timeout_seconds: int = Field(default=5, ge=1, le=30)
    dataset_dir: Path | None = None
    upload_max_bytes: int = 268435456
    upload_max_rows: int = 1000000
    equipment_sync_enabled: bool = False
    equipment_sync_url: str = ""
    equipment_sync_token: SecretStr = SecretStr("")
    equipment_sync_source: str = Field(default="customer", min_length=1, max_length=64)
    equipment_sync_interval_seconds: int = Field(default=900, ge=60, le=86400)
    equipment_sync_field_map: dict[str, str] = {}
    equipment_sync_ca_file: str | None = None
    equipment_sync_allow_http: bool = False

    @property
    def ldap_configured(self) -> bool:
        return bool(
            self.ldap_enabled
            and self.ldap_url
            and self.ldap_base_dn
            and self.ldap_bind_dn
            and self.ldap_bind_password.get_secret_value()
        )

    smtp_host: str = Field(default="", validation_alias=AliasChoices("SMTP_HOST", "VENA_SMTP_HOST"))
    smtp_port: int = Field(
        default=587, validation_alias=AliasChoices("SMTP_PORT", "VENA_SMTP_PORT")
    )
    smtp_username: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_USER", "SMTP_USERNAME", "VENA_SMTP_USERNAME"),
    )
    smtp_password: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("SMTP_PASSWORD", "VENA_SMTP_PASSWORD")
    )
    smtp_from: str = Field(default="", validation_alias=AliasChoices("SMTP_FROM", "VENA_SMTP_FROM"))
    smtp_tls: bool = Field(default=True, validation_alias=AliasChoices("SMTP_TLS", "VENA_SMTP_TLS"))

    smtp_secure: bool = Field(
        default=False, validation_alias=AliasChoices("SMTP_SECURE", "VENA_SMTP_SECURE")
    )

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()
