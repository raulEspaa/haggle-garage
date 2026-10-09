"""Typed configuration loaded from environment variables.

The .NET equivalent is binding `appsettings.json` + env vars to an `IOptions<T>` class.
Every variable is prefixed with `HAGGLE_`, e.g. `HAGGLE_DATABASE_URL`.
A local `.env` file is read for convenience; it is gitignored and never used in production.
"""

import os
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


def gemini_configured() -> bool:
    """Can the google-genai SDK (used by ADK, LangChain and our embedder) reach Gemini?

    Two backends, chosen by environment variables the SDK reads itself (ADR-0013):
    * Vertex AI: GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT (+ GOOGLE_CLOUD_LOCATION),
      authenticated with ADC (`gcloud auth application-default login`, or the Cloud Run
      service account). No API key.
    * Gemini API (AI Studio): GOOGLE_API_KEY.
    """
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true"):
        return bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
