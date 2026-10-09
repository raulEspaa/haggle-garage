"""Request-level protections: client IP, privacy-preserving IP hash, input hygiene, headers.

Every function here is pure (or a tiny ASGI middleware), so all of it is unit-testable.
"""

import hashlib
import hmac
import unicodedata
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Zero-width and bidi control characters: invisible text is a classic way to smuggle
# instructions past a human reviewer (and past naive filters).
_INVISIBLE = {
    "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff",
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    "\u2066", "\u2067", "\u2068", "\u2069",
}  # fmt: skip


class InvalidInputError(ValueError):
    pass


def client_ip(forwarded_for: str | None, socket_host: str | None, trusted_hops: int) -> str:
    """The client address we trust.

    X-Forwarded-For is a comma list that ANYONE can pre-fill. Each trusted proxy APPENDS the
    address it saw, so only the last `trusted_hops` entries are trustworthy. Taking the left-most
    entry (a common bug) lets an attacker pick their own IP and dodge rate limits (threat T12).
    """
    if trusted_hops > 0 and forwarded_for:
        hops = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        if len(hops) >= trusted_hops:
            return hops[-trusted_hops]
    return socket_host or "unknown"


def ip_hash(ip: str, secret: str, day: datetime | None = None) -> str:
    """Salted, daily-rotating hash: enough to count games per IP per day, useless to identify
    anyone afterwards (IP addresses are personal data under GDPR, threat T26)."""
    day_key = (day or datetime.now(UTC)).strftime("%Y-%m-%d")
    daily_salt = hmac.new(secret.encode(), day_key.encode(), hashlib.sha256).digest()
    return hmac.new(daily_salt, ip.encode(), hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_message(text: str, max_chars: int) -> str:
    """Normalize a player's message, or raise InvalidInputError."""
    normalized = unicodedata.normalize("NFKC", text).strip()
    if not normalized:
        raise InvalidInputError("Message is empty.")
    if len(normalized) > max_chars:
        raise InvalidInputError(f"Message is longer than {max_chars} characters.")
    for char in normalized:
        if char in _INVISIBLE or (unicodedata.category(char) == "Cc" and char not in "\n\t"):
            raise InvalidInputError("Message contains control or invisible characters.")
    return normalized


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)
SECURITY_HEADERS = {
    b"content-security-policy": CONTENT_SECURITY_POLICY.encode(),
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"no-referrer",
    b"x-frame-options": b"DENY",
}


class SecurityHeadersMiddleware:
    """Add security headers to every response. The CSP forbids inline scripts, so even if model
    output ever reached the DOM as HTML, injected <script> would not run (defense in depth for
    LLM05; the first line is `textContent` in app.js)."""

    def __init__(self, app: ASGIApp, exempt_prefixes: tuple[str, ...] = ()) -> None:
        self.app = app
        self.exempt_prefixes = exempt_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(self.exempt_prefixes):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *SECURITY_HEADERS.items()]
            await send(message)

        await self.app(scope, receive, send_with_headers)
