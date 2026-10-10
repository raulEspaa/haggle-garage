import base64
import json
import time

import pytest

from haggle_core import gcp_auth


def fake_token(exp: float) -> str:
    def part(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{part({'alg': 'RS256'})}.{part({'exp': int(exp), 'aud': 'x'})}.c2ln"


def test_id_token_is_cached_until_close_to_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    expiry = [time.time() + 3600]

    def fetch(request: object, audience: str) -> str:
        calls.append(audience)
        return fake_token(expiry[0])

    monkeypatch.setattr(gcp_auth.id_token, "fetch_id_token", fetch)
    source = gcp_auth.IdTokenSource("https://haggle-seller-1.europe-west1.run.app")

    first = source.headers()
    source.headers()
    assert calls == ["https://haggle-seller-1.europe-west1.run.app"]  # one fetch, then cached
    assert first["Authorization"].startswith("Bearer ")

    expiry[0] = time.time() + 3600
    source._expires_at = time.time() + 60  # within the refresh margin
    source.headers()
    assert len(calls) == 2
