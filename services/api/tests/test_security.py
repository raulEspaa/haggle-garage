"""Pure request-level protections: no database, no network."""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from haggle_api.security import InvalidInputError, clean_message, client_ip, ip_hash

STATIC = Path(__file__).resolve().parents[1] / "src" / "haggle_api" / "static"


@pytest.mark.parametrize(
    ("forwarded", "socket", "hops", "expected"),
    [
        (None, "127.0.0.1", 0, "127.0.0.1"),
        ("6.6.6.6", "127.0.0.1", 0, "127.0.0.1"),  # no proxy: the header is ignored
        ("1.2.3.4", "10.0.0.1", 1, "1.2.3.4"),
        # The attacker pre-fills a fake left-most entry; Google appends the real one.
        ("6.6.6.6, 1.2.3.4", "10.0.0.1", 1, "1.2.3.4"),
        ("6.6.6.6, 1.2.3.4, 10.9.9.9", "10.0.0.1", 2, "1.2.3.4"),
        ("1.2.3.4", "10.0.0.1", 2, "10.0.0.1"),  # fewer hops than expected: don't trust it
        (None, None, 0, "unknown"),
    ],
)
def test_client_ip_only_trusts_the_right_most_hops(
    forwarded: str | None, socket: str | None, hops: int, expected: str
) -> None:
    assert client_ip(forwarded, socket, hops) == expected


def test_ip_hash_is_stable_within_a_day_and_rotates_daily() -> None:
    monday = datetime(2026, 10, 5, 9, tzinfo=UTC)
    monday_night = datetime(2026, 10, 5, 23, tzinfo=UTC)
    tuesday = datetime(2026, 10, 6, 9, tzinfo=UTC)

    first = ip_hash("1.2.3.4", "secret", monday)

    assert first == ip_hash("1.2.3.4", "secret", monday_night)
    assert first != ip_hash("1.2.3.4", "secret", tuesday)
    assert first != ip_hash("1.2.3.4", "other-secret", monday)
    assert "1.2.3.4" not in first


def test_clean_message_normalizes_lookalikes() -> None:
    # NFKC folds full-width digits ("30,000") and the "fi" ligature, so filters see what the
    # model will see.
    fullwidth = "\uff13\uff10\uff0c\uff10\uff10\uff10 \ufb01nal"
    assert clean_message(f"  {fullwidth}  ", 500) == "30,000 final"


def test_clean_message_keeps_newlines_and_accents() -> None:
    assert clean_message("¿Precio?\nÚltima oferta", 500) == "¿Precio?\nÚltima oferta"


@pytest.mark.parametrize("text", ["", " \n ", "a" * 11, "x\u200by", "x\u2066y", "x\x1by"])
def test_clean_message_rejects(text: str) -> None:
    with pytest.raises(InvalidInputError):
        clean_message(text, 10)


def test_client_code_never_uses_html_sinks() -> None:
    # Model output is untrusted (OWASP LLM05): the browser must only ever see it as text.
    source = (STATIC / "app.js").read_text()
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("//"))

    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", code)
