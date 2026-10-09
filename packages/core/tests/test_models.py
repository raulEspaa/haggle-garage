"""Schema tests that need no database: they inspect the SQLAlchemy metadata."""

from sqlalchemy import CheckConstraint

from haggle_core.db import Base
from haggle_core.db.models import one_of
from haggle_core.domain import GameStatus

EXPECTED_TABLES = {
    "cars",
    "deals",
    "games",
    "llm_usage",
    "model_sheets",
    "negotiation_events",
    "pricing_policies",
    "sheet_chunks",
    "turns",
}


def test_all_contract_tables_are_mapped() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_one_of_builds_check_from_enum() -> None:
    expression = one_of("status", GameStatus)

    assert expression.startswith("status IN (")
    for status in GameStatus:
        assert f"'{status.value}'" in expression


def test_games_protect_core_invariants() -> None:
    games = Base.metadata.tables["games"]
    checks = {c.name for c in games.constraints if isinstance(c, CheckConstraint)}

    assert {
        "ck_games_level_range",
        "ck_games_status_valid",
        "ck_games_floor_below_list",
        "ck_games_turn_count_range",
    } <= checks


def test_deals_allow_at_most_one_deal_per_game() -> None:
    deals = Base.metadata.tables["deals"]

    assert [column.name for column in deals.primary_key.columns] == ["game_id"]
