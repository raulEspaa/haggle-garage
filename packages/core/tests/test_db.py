"""Integration tests against a real Postgres (+ pgvector). Run `make db-up` first."""

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, func, insert, select, text
from sqlalchemy.exc import IntegrityError

from haggle_core.db.models import Car, Deal, Game
from haggle_core.seed import apply_seed, load_seed

pytestmark = pytest.mark.db

CAR_ID = "vantor-kestrel-rs-1970"


def new_game(conn: Connection, *, level: int, floor_usd: int = 27385) -> uuid.UUID:
    game_id = uuid.uuid4()
    conn.execute(
        insert(Game).values(
            id=game_id,
            car_id=CAR_ID,
            level=level,
            mode="human",
            list_price_usd=38900,
            floor_usd=floor_usd,
            counter_margin="0.034",
        )
    )
    return game_id


def test_migrations_match_the_models(alembic_config: Config, migrated_engine: Engine) -> None:
    # Raises if `alembic revision --autogenerate` would produce any operation (schema drift).
    command.check(alembic_config)


def test_seed_is_idempotent(migrated_engine: Engine, seed_file: Path) -> None:
    apply_seed(migrated_engine, load_seed(seed_file))  # second run (first is in the fixture)

    with migrated_engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Car)) == 3


def test_invalid_level_is_rejected_by_the_database(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="ck_games_level_range"):
        new_game(conn, level=4)


def test_floor_must_be_below_list_price(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="ck_games_floor_below_list"):
        new_game(conn, level=1, floor_usd=40000)


def test_seller_view_hides_the_floor_at_level_3(conn: Connection) -> None:
    visible = new_game(conn, level=1)
    hidden = new_game(conn, level=3)

    rows = conn.execute(
        text("SELECT game_id, floor_usd FROM seller_game_context WHERE game_id IN (:a, :b)"),
        {"a": visible, "b": hidden},
    ).all()
    floors = {row.game_id: row.floor_usd for row in rows}

    assert floors[visible] == 27385
    assert floors[hidden] is None


def test_only_one_deal_per_game(conn: Connection) -> None:
    game_id = new_game(conn, level=3)
    conn.execute(
        insert(Deal).values(game_id=game_id, price_usd=31500, idempotency_key=uuid.uuid4())
    )

    with pytest.raises(IntegrityError, match="pk_deals"):
        conn.execute(
            insert(Deal).values(game_id=game_id, price_usd=30000, idempotency_key=uuid.uuid4())
        )


def test_new_games_start_open(conn: Connection) -> None:
    game_id = new_game(conn, level=2)

    status, turn_count = conn.execute(
        select(Game.status, Game.turn_count).where(Game.id == game_id)
    ).one()

    assert (status, turn_count) == ("open", 0)


async def test_async_engine_works(session_factory: object) -> None:
    # Regression: SQLAlchemy 2.1 no longer installs greenlet by default; without the
    # `sqlalchemy[asyncio]` extra every async query fails at runtime.
    async with session_factory() as session:  # type: ignore[operator]
        assert await session.scalar(text("SELECT 1")) == 1
