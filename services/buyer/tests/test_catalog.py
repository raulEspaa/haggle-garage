"""The buyer's MCP client against the real MCP server (in-process, over HTTP, real Postgres)."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from pydantic import SecretStr

from haggle_buyer.catalog import CatalogUnavailableError, McpCatalog
from haggle_mcp.rag.embeddings import FakeEmbedder
from haggle_mcp.rag.sheets import load_sheets
from haggle_mcp.rag.store import ingest_sheets
from haggle_mcp.server import build_app
from haggle_mcp.settings import McpSettings

pytestmark = pytest.mark.db

SHEETS_DIR = Path(__file__).resolve().parents[3] / "db" / "sheets"
SETTINGS = McpSettings(seller_token=SecretStr("seller-t"), catalog_token=SecretStr("catalog-t"))


@pytest.fixture
async def mcp_url(database_url: str, session_factory: Any) -> AsyncIterator[str]:
    await ingest_sheets(session_factory, load_sheets(SHEETS_DIR), FakeEmbedder())
    app = build_app(SETTINGS, database_url, FakeEmbedder())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 (uvicorn exposes no 'started' event)
        await asyncio.sleep(0.02)
    yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}/mcp"
    server.should_exit = True
    await task


async def test_catalog_token_reads_the_sheets_over_one_session(mcp_url: str) -> None:
    catalog = McpCatalog(mcp_url, "catalog-t")

    hits = await catalog.lookup(
        ["Camaro Z/28 market notes price range", "Camaro Z/28 known issues"], top_k=2
    )

    assert hits
    assert len({(h.sheet_slug, h.section) for h in hits}) == len(hits)  # no duplicates


async def test_unknown_token_is_refused(mcp_url: str) -> None:
    with pytest.raises(CatalogUnavailableError):
        await McpCatalog(mcp_url, "guess").lookup(["Camaro"])


async def test_unreachable_server_is_a_catalog_error() -> None:
    with pytest.raises(CatalogUnavailableError):
        await McpCatalog("http://127.0.0.1:9/mcp", "catalog-t", timeout_s=2).lookup(["Camaro"])
