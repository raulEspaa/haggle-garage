"""Async engine and session factories for the services.

Services handle many concurrent requests, so they use the async API. One-off scripts
(seed, migrations) use plain sync engines: async brings nothing there.
The same driver (psycopg 3) serves both styles.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from haggle_core.settings import get_settings


def create_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or get_settings().database_url.get_secret_value()
    # pool_pre_ping: Neon scales to zero, so pooled connections can go stale.
    return create_async_engine(url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: objects stay readable after commit (no surprise lazy reloads).
    return async_sessionmaker(engine, expire_on_commit=False)
