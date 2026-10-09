"""Expose the seller over A2A (ADR-0006).

ADK's `to_a2a()` is labelled experimental; it is used only here, so an API change touches one
file. Sessions live in Postgres (schema `adk`, migration 0003): the A2A contextId becomes the
ADK session id (spike S2), which is our game id.
"""

import logging
import os

import uvicorn
from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.applications import Starlette

from haggle_core.db.session import create_engine, create_session_factory
from haggle_core.settings import get_settings
from haggle_seller.agent import build_seller_agent
from haggle_seller.repository import SellerRepository
from haggle_seller.settings import SellerSettings, get_seller_settings
from haggle_seller.tracing import setup_tracing

APP_NAME = "haggle-seller"


def build_app(settings: SellerSettings | None = None) -> Starlette:
    settings = settings or get_seller_settings()
    setup_tracing()  # before the agent exists, so every span is captured
    database_url = get_settings().database_url.get_secret_value()

    repo = SellerRepository(create_session_factory(create_engine(database_url)))
    agent = build_seller_agent(settings, repo)

    # A dedicated engine whose search_path is the `adk` schema: ADK creates its tables there.
    adk_engine = create_async_engine(
        database_url, connect_args={"options": "-c search_path=adk"}, pool_pre_ping=True
    )
    runner = Runner(
        app_name=APP_NAME, agent=agent, session_service=DatabaseSessionService(db_engine=adk_engine)
    )
    return to_a2a(agent, host=settings.host, port=settings.port, runner=runner)


def run() -> None:
    """`uv run haggle-seller`: A2A server on 127.0.0.1:8200 (needs the MCP server running)."""
    load_dotenv()  # GOOGLE_API_KEY, LANGFUSE_* and HAGGLE_* from .env
    os.environ.setdefault("ADK_SUPPRESS_A2A_EXPERIMENTAL_FEATURE_WARNINGS", "true")
    logging.basicConfig(level=logging.INFO)
    settings = get_seller_settings()
    uvicorn.run(build_app(settings), host=settings.host, port=settings.port)
