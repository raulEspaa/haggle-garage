"""Typed configuration loaded from environment variables.

The .NET equivalent is binding `appsettings.json` + env vars to an `IOptions<T>` class.
Every variable is prefixed with `HAGGLE_`, e.g. `HAGGLE_DATABASE_URL`.
A local `.env` file is read for convenience; it is gitignored and never used in production.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = "postgresql+psycopg://haggle:haggle@localhost:5432/haggle"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HAGGLE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["local", "prod"] = "local"
    # SecretStr hides the value in repr()/logs; call .get_secret_value() only where needed.
    database_url: SecretStr = SecretStr(LOCAL_DATABASE_URL)
    git_sha: str = "dev"


@lru_cache
def get_settings() -> Settings:
    """Build settings once per process (env vars are read at first call)."""
    return Settings()
