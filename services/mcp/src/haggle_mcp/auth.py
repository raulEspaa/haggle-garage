"""App-level authentication for the MCP endpoint (ADR-0008).

Why a plain ASGI middleware instead of MCP's own middleware hook? The MCP SDK v2 marks its
middleware API as *provisional* ("the signature may change in a 2.x minor release"). An ASGI
middleware is a stable standard and works the same whatever framework sits behind it.

Two layers:
1. `TokenAuthMiddleware` rejects any request to /mcp without a known token (HTTP 401).
2. Each tool checks the token's *scope* (`require_scope`). The spec's 2026-07-28 revision says
   list endpoints must not vary per connection, so every client SEES all tools; authorization
   is enforced when a tool is CALLED.
"""

import hmac
import json
from collections.abc import Mapping
from enum import StrEnum

from starlette.types import ASGIApp, Receive, Scope, Send

from haggle_mcp.settings import McpSettings

TOKEN_HEADER = "x-haggle-token"  # noqa: S105 (a header NAME, not a secret)
GAME_HEADER = "x-haggle-game-id"


class ClientScope(StrEnum):
    SELLER = "seller"  # every tool
    CATALOG = "catalog"  # lookup_model_sheet only (the buyer agent)


def scope_for_token(token: str | None, settings: McpSettings) -> ClientScope | None:
    """Map a presented token to its scope. `hmac.compare_digest` runs in constant time,
    so response timing does not reveal how many leading characters were right."""
    if not token:
        return None
    if hmac.compare_digest(token, settings.seller_token.get_secret_value()):
        return ClientScope.SELLER
    if hmac.compare_digest(token, settings.catalog_token.get_secret_value()):
        return ClientScope.CATALOG
    return None


def scope_from_headers(
    headers: Mapping[str, str] | None, settings: McpSettings
) -> ClientScope | None:
    return scope_for_token((headers or {}).get(TOKEN_HEADER), settings)


class TokenAuthMiddleware:
    """Pure ASGI middleware: protects `protected_prefix`, lets everything else through."""

    def __init__(self, app: ASGIApp, settings: McpSettings, protected_prefix: str = "/mcp") -> None:
        self.app = app
        self.settings = settings
        self.protected_prefix = protected_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.protected_prefix):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        if scope_from_headers(headers, self.settings) is None:
            body = json.dumps({"error": "unauthorized"}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
