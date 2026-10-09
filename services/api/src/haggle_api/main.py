"""HTTP entry point.

Week 1 is a "walking skeleton": the thinnest slice that goes all the way to production
(code → container → Cloud Run → public URL). Features are added on top in later weeks.
"""

import os
from typing import Literal

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from haggle_core.settings import get_settings


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["api"] = "api"
    version: str


def create_app() -> FastAPI:
    """App factory: tests build a fresh app instead of sharing a module-level global."""
    settings = get_settings()
    app = FastAPI(title="Haggle Garage API", version="0.1.0")

    @app.get("/health", tags=["ops"])
    async def health() -> Health:
        # Liveness only: it must not touch the database. A sleeping Neon database
        # should not make Cloud Run think the container is broken.
        return Health(version=settings.git_sha)

    return app


app = create_app()


def run() -> None:
    """`uv run haggle-api`: local development server with auto-reload.

    Listens on 127.0.0.1 by default, so it is not exposed to your LAN.
    The container overrides the host to 0.0.0.0 (see Dockerfile).
    """
    uvicorn.run(
        "haggle_api.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),  # Cloud Run injects PORT
        reload=True,
    )
