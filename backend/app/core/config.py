from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
