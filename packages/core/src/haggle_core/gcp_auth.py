"""Service-to-service auth on Cloud Run: Google-signed ID tokens.

The seller and MCP services are private (no `allUsers` invoker). Cloud Run only lets a request
through if it carries `Authorization: Bearer <ID token>` signed by Google for a service account
that has `roles/run.invoker` on the target, with the target's URL as the token audience.

On Cloud Run the token comes from the metadata server, for the service's own identity. Locally
there is nothing to do: services talk over plain HTTP without IAM (auth mode "none").
"""

import threading
import time

import google.auth.transport.requests
from google.auth import jwt
from google.oauth2 import id_token

REFRESH_MARGIN_S = 300  # tokens live 1 hour; refresh 5 minutes before expiry


class IdTokenSource:
    """A cached ID token for one audience. Thread-safe; fetching is a small blocking call that
    happens about once an hour."""

    def __init__(self, audience: str) -> None:
        self.audience = audience
        self._token = ""
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def token(self) -> str:
        with self._lock:
            if time.time() > self._expires_at - REFRESH_MARGIN_S:
                request = google.auth.transport.requests.Request()
                self._token = id_token.fetch_id_token(request, self.audience)  # type: ignore[no-untyped-call]
                # Our own freshly minted token: read its expiry, no need to verify the signature.
                claims = jwt.decode(self._token, verify=False)  # type: ignore[no-untyped-call]
                self._expires_at = float(claims["exp"])
            return self._token

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token()}"}
