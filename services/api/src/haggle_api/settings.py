"""API configuration (env vars prefixed HAGGLE_API_). Defaults are the public-demo limits from
docs/07-threat-model.md §5."""

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HAGGLE_API_", env_file=".env", extra="ignore")

    seller_url: str = "http://127.0.0.1:8200"
    # A seller turn is 2-3 model calls; on a busy Gemini day that took up to ~60 s. On a timeout
    # the turn still completes on the seller, and the page polls the game state to show it.
    seller_timeout_s: float = 90.0
    # "google" on Cloud Run: send an ID token for the private seller service (IAM invoker).
    seller_auth: Literal["none", "google"] = "none"

    demo_enabled: bool = True  # the kill switch: false -> 503 for new games and messages
    # Number of reverse proxies in front of us that append to X-Forwarded-For. 0 locally (use the
    # socket address); 1 on Cloud Run (take the right-most entry, the one Google appended).
    trusted_proxy_hops: int = 0
    ip_hash_secret: SecretStr = SecretStr("local-ip-hash-secret")

    games_per_ip_per_day: int = 5
    games_per_hour_global: int = 60
    messages_per_ip_per_hour: int = 30
    daily_budget_usd: Decimal = Decimal("1.00")

    turn_cap: int = 12
    game_idle_minutes: int = 30
    floor_guess_tolerance: Decimal = Decimal("0.015")  # ±1.5 % (docs/01-vision-and-scope.md §4)
    max_message_chars: int = 500


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
