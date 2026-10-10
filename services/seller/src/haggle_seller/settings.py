"""Seller configuration (env vars prefixed HAGGLE_SELLER_)."""

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SellerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HAGGLE_SELLER_", env_file=".env", extra="ignore")

    model_id: str = "gemini-3.1-flash-lite"
    temperature: float = 0.7
    max_output_tokens: int = 600

    mcp_url: str = "http://127.0.0.1:8100/mcp"
    # "google" on Cloud Run: send an ID token for the private MCP service (IAM invoker).
    mcp_auth: Literal["none", "google"] = "none"
    # Must equal the MCP server's seller token. Locally both read HAGGLE_MCP_SELLER_TOKEN from the
    # same .env; in the cloud each service gets its own secret (week 7).
    mcp_token: SecretStr = Field(
        default=SecretStr("local-seller-token"),
        validation_alias=AliasChoices("HAGGLE_SELLER_MCP_TOKEN", "HAGGLE_MCP_SELLER_TOKEN"),
    )

    host: str = "127.0.0.1"
    port: int = 8200
    public_url: str = "http://127.0.0.1:8200"  # what the agent card advertises

    # Soft budget (docs/07-threat-model.md §5): above it the seller stops calling the LLM.
    daily_budget_usd: Decimal = Decimal("1.00")
    # Secret used to derive a per-game canary token for the system prompt (prompt-leak tripwire).
    canary_secret: SecretStr = SecretStr("local-canary-secret")


@lru_cache
def get_seller_settings() -> SellerSettings:
    return SellerSettings()
