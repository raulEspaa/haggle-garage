"""HTTP entry point: app factory, wiring and lifecycle.

`create_app()` builds the app; dependencies (database, seller client) are created in the
lifespan and stored on `app.state`. Tests pass their own seller client (a fake), the same
way you would register a test double in an ASP.NET Core DI container.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from haggle_api.errors import install_error_handlers
from haggle_api.games import GameService
from haggle_api.routes import api, page_router
from haggle_api.security import SecurityHeadersMiddleware
from haggle_api.settings import ApiSettings, get_api_settings
from haggle_core.a2a_client import A2ASellerClient, SellerClient
from haggle_core.db.session import create_engine, create_session_factory
from haggle_core.settings import get_settings
from haggle_core.tracing import setup_langfuse

PACKAGE_DIR = Path(__file__).parent
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["api"] = "api"
    version: str


def create_app(
    settings: ApiSettings | None = None,
    seller: SellerClient | None = None,
    database_url: str | None = None,
) -> FastAPI:
    """App factory: tests build a fresh app instead of sharing a module-level global."""
    settings = settings or get_api_settings()
    core = get_settings()
    local = core.env == "local"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_langfuse()
        engine = create_engine(database_url)
        client = seller or A2ASellerClient(settings.seller_url, settings.seller_timeout_s)
        app.state.settings = settings
        app.state.games = GameService(engine, create_session_factory(engine), settings, client)
        yield
        await client.aclose()
        await engine.dispose()

    app = FastAPI(
        title="Haggle Garage API",
        version="0.1.0",
        lifespan=lifespan,
        # Interactive docs only locally: in prod they'd need a looser CSP (CDN scripts).
        docs_url="/docs" if local else None,
        redoc_url=None,
        openapi_url="/openapi.json" if local else None,
    )
    install_error_handlers(app)
    app.add_middleware(SecurityHeadersMiddleware, exempt_prefixes=DOCS_PATHS if local else ())

    @app.get("/health", tags=["ops"])
    async def health() -> Health:
        # Liveness only: it must not touch the database. A sleeping Neon database
        # should not make Cloud Run think the container is broken.
        # Not "/healthz": Cloud Run reserves some paths ending in "z" (week 1 journal).
        return Health(version=core.git_sha)

    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    app.include_router(api)
    app.include_router(page_router(templates))
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    return app


def run() -> None:
    """`uv run haggle-api`: local development server with auto-reload.

    Listens on 127.0.0.1 by default, so it is not exposed to your LAN.
    The container overrides the host to 0.0.0.0 (see Dockerfile).
    """
    load_dotenv()
    uvicorn.run(
        "haggle_api.main:create_app",
        factory=True,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
        reload=True,
    )
