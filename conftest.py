"""Shared pytest fixtures for every package in the workspace (pytest loads the root conftest.py
for all test directories below it).

Database tests (marked `db`) run against a disposable database whose name MUST end in
`_test`: the fixture drops and recreates its `public` schema. If Postgres is not reachable,
they are skipped locally. CI sets HAGGLE_REQUIRE_DB=1 so they fail instead of silently skipping.
"""

import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, insert, make_url, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from haggle_core.db.models import Game
from haggle_core.db.session import create_engine as create_async_engine
from haggle_core.db.session import create_session_factory
from haggle_core.seed import apply_seed, load_seed

REPO_ROOT = Path(__file__).resolve().parent
SEED_FILE = REPO_ROOT / "db" / "seed" / "cars.yaml"
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://haggle:haggle@localhost:5432/haggle_test"


@pytest.fixture(scope="session")
def seed_file() -> Path:
    return SEED_FILE


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("HAGGLE_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        # Safety net: never wipe a database that is not explicitly a test database.
        pytest.fail(f"Refusing to run DB tests against {database!r}: name must end in '_test'.")

    engine = create_engine(url)
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        if os.environ.get("HAGGLE_REQUIRE_DB") == "1":
            raise
        pytest.skip(f"Postgres not reachable ({type(exc).__name__}). Run `make db-up`.")
    finally:
        engine.dispose()
    return url


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture(scope="session")
def migrated_engine(database_url: str, alembic_config: Config) -> Iterator[Engine]:
    """A fresh schema built by running every migration, exactly like production."""
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config, "head")
    apply_seed(engine, load_seed(SEED_FILE))
    yield engine
    engine.dispose()


@pytest.fixture
def conn(migrated_engine: Engine) -> Iterator[Connection]:
    """A connection inside a transaction that is always rolled back: tests leave no trace."""
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
async def session_factory(
    database_url: str, migrated_engine: Engine
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Async sessions on the migrated test database (what the services use in production)."""
    engine = create_async_engine(database_url)
    yield create_session_factory(engine)
    await engine.dispose()


NewGame = Callable[..., uuid.UUID]


@pytest.fixture
def new_game(migrated_engine: Engine) -> NewGame:
    """Factory: insert a committed game (on the 1970 Challenger) and return its id."""

    def _create(
        *,
        level: int = 3,
        floor_usd: int = 27_385,
        turn_count: int = 1,
        counter_margin: str = "0.034",
        status: str = "open",
    ) -> uuid.UUID:
        game_id = uuid.uuid4()
        with migrated_engine.begin() as conn:
            conn.execute(
                insert(Game).values(
                    id=game_id,
                    car_id="dodge-challenger-rt-1970",
                    level=level,
                    mode="eval",
                    list_price_usd=38_900,
                    floor_usd=floor_usd,
                    counter_margin=Decimal(counter_margin),
                    turn_count=turn_count,
                    status=status,
                )
            )
        return game_id

    return _create


@pytest.fixture
def set_turn(migrated_engine: Engine) -> Callable[[uuid.UUID, int], None]:
    """Simulate the seller reserving the next buyer turn."""

    def _set(game_id: uuid.UUID, turn: int) -> None:
        with migrated_engine.begin() as conn:
            conn.execute(
                text("UPDATE games SET turn_count = :t WHERE id = :g"), {"t": turn, "g": game_id}
            )

    return _set
