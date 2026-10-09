"""MCP server configuration (env vars prefixed HAGGLE_MCP_)."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HAGGLE_MCP_", env_file=".env", extra="ignore")

    # One token per client scope (docs/03-contracts.md §1.2). Both are required: a server that
    # starts without tokens must fail loudly instead of running unauthenticated.
    seller_token: SecretStr
    catalog_token: SecretStr
    backend: Literal["home", "cloud", "local"] = "local"
    # DNS-rebinding protection: Host headers this server answers ("name:port", "*" = any port).
    # Add the service's real name where it runs: "mcp:*" in compose, the Cloud Run host in prod.
    allowed_hosts: list[str] = ["127.0.0.1:*", "localhost:*", "[::1]:*"]


@lru_cache
def get_mcp_settings() -> McpSettings:
    return McpSettings()  # values come from the environment
