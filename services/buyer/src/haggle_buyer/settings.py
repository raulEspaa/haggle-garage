"""Buyer configuration (env vars prefixed HAGGLE_BUYER_)."""

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class BuyerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HAGGLE_BUYER_", env_file=".env", extra="ignore")

    model_id: str = "gemini-3.1-flash-lite"
    temperature: float = 0.8  # some variety between runs of the same persona

    seller_url: str = "http://127.0.0.1:8200"
    seller_timeout_s: float = 90.0
    mcp_url: str = "http://127.0.0.1:8100/mcp"
    # The CATALOG token: lookup_model_sheet only. Locally it is the MCP server's catalog token.
    mcp_token: SecretStr = Field(
        default=SecretStr("local-catalog-token"),
        validation_alias=AliasChoices("HAGGLE_BUYER_MCP_TOKEN", "HAGGLE_MCP_CATALOG_TOKEN"),
    )
    turn_cap: int = 12
    # Gemini's free tier allows 15 requests/minute per model, SHARED by buyer and seller (same
    # key). The buyer takes at most this many, leaving the rest to the seller.
    max_requests_per_minute: float = 5.0


@lru_cache
def get_buyer_settings() -> BuyerSettings:
    return BuyerSettings()
