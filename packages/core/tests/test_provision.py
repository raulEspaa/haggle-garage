"""Least-privilege roles, checked against a real Postgres: what each service can and cannot do."""

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import ProgrammingError

from haggle_core.provision import provision

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def role_urls(database_url: str, migrated_engine: Engine) -> dict[str, str]:
    with migrated_engine.begin() as conn:  # ADK's schema exists in production databases
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS adk"))
    return provision(database_url)


def run(url: str, sql: str) -> object:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            return conn.execute(text(sql)).first()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("role", "sql"),
    [
        ("haggle_seller", "SELECT floor_usd FROM games"),  # the seller must never see the floor
        ("haggle_seller", "SELECT counter_margin FROM games"),
        ("haggle_seller", "SELECT * FROM deals"),
        ("haggle_seller", "SELECT * FROM negotiation_events"),
        (
            "haggle_api",
            "INSERT INTO deals (game_id, price_usd, idempotency_key) "
            "VALUES (gen_random_uuid(), 1, gen_random_uuid())",
        ),  # only the MCP server closes deals
        ("haggle_api", "SELECT * FROM negotiation_events"),
        ("haggle_mcp", "DELETE FROM games"),
        ("haggle_mcp", "UPDATE games SET floor_usd = 1"),
    ],
)
def test_roles_are_denied_what_they_do_not_need(
    role_urls: dict[str, str], role: str, sql: str
) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        run(role_urls[role], sql)


@pytest.mark.parametrize(
    ("role", "sql"),
    [
        ("haggle_seller", "SELECT level, floor_usd FROM seller_game_context"),
        ("haggle_seller", "SELECT id, status, turn_count, turn_cap FROM games"),
        ("haggle_api", "SELECT floor_usd FROM games"),  # revealed to players after the game
        ("haggle_mcp", "SELECT floor_usd FROM games"),
    ],
)
def test_roles_can_do_their_job(role_urls: dict[str, str], role: str, sql: str) -> None:
    run(role_urls[role], sql)


def test_running_again_rotates_the_passwords(database_url: str, role_urls: dict[str, str]) -> None:
    rotated = provision(database_url)

    assert rotated["haggle_api"] != role_urls["haggle_api"]
    run(rotated["haggle_api"], "SELECT 1")
