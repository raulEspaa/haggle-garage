"""MCP server tests: auth, health, contract snapshot and an end-to-end call over real HTTP."""

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from starlette.testclient import TestClient

from haggle_mcp.server import build_app, build_server
from haggle_mcp.settings import McpSettings

SETTINGS = McpSettings(
    seller_token=SecretStr("seller-test-token"), catalog_token=SecretStr("catalog-test-token")
)
SNAPSHOT = Path(__file__).parent / "snapshots" / "tools.json"
UNUSED_DB = "postgresql+psycopg://nobody@localhost:1/none_test"  # engines connect lazily


# ----------------------------------------------------------------------------- no database
def test_mcp_endpoint_rejects_requests_without_a_token() -> None:
    with TestClient(build_app(SETTINGS, UNUSED_DB)) as client:
        response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response.status_code == 401


def test_mcp_endpoint_rejects_unknown_tokens() -> None:
    with TestClient(build_app(SETTINGS, UNUSED_DB)) as client:
        response = client.post("/mcp", json={}, headers={"X-Haggle-Token": "guess"})

    assert response.status_code == 401


def test_health_is_public_and_reports_the_backend() -> None:
    with TestClient(build_app(SETTINGS, UNUSED_DB)) as client:
        body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["service"] == "mcp"
    assert body["backend"] == "local"


async def test_tool_contract_matches_snapshot() -> None:
    """Fails when a tool's name, description or schema changes. If the change is intended,
    regenerate with UPDATE_SNAPSHOTS=1 and review the diff: it is a contract change."""
    tools = await build_server(None, SETTINGS).list_tools()  # type: ignore[arg-type]
    current = {
        t.name: {
            "description": t.description,
            "input_schema": t.input_schema,
            "output_schema": t.output_schema,
            "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None,
        }
        for t in tools
    }
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")

    assert current == json.loads(SNAPSHOT.read_text())


async def test_no_tool_lets_the_llm_choose_the_game() -> None:
    # ADR-0008: trusted context comes from headers, never from LLM-filled arguments.
    for tool in await build_server(None, SETTINGS).list_tools():  # type: ignore[arg-type]
        assert "game_id" not in json.dumps(tool.input_schema)


# ----------------------------------------------------------------------------- end to end
@pytest.fixture
async def server_url(database_url: str, migrated_engine: object) -> AsyncIterator[str]:
    config = uvicorn.Config(
        build_app(SETTINGS, database_url), host="127.0.0.1", port=0, log_level="warning"
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 (uvicorn exposes no 'started' event)
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    await task


async def call(url: str, headers: dict[str, str], tool: str, args: dict[str, object]) -> object:
    async with (
        httpx2.AsyncClient(headers=headers) as http,
        Client(streamable_http_client(url, http_client=http)) as client,
    ):
        return await client.call_tool(tool, args)


@pytest.mark.db
async def test_seller_can_evaluate_an_offer_over_http(
    server_url: str, new_game: Callable[..., uuid.UUID]
) -> None:
    headers = {"X-Haggle-Token": "seller-test-token", "X-Haggle-Game-Id": str(new_game())}

    result = await call(server_url, headers, "evaluate_offer", {"offer_usd": 30_000})

    assert not result.is_error  # type: ignore[attr-defined]
    assert result.structured_content["decision"] == "counter"  # type: ignore[attr-defined]


@pytest.mark.db
async def test_catalog_scope_cannot_call_seller_tools(
    server_url: str, new_game: Callable[..., uuid.UUID]
) -> None:
    headers = {"X-Haggle-Token": "catalog-test-token", "X-Haggle-Game-Id": str(new_game())}

    result = await call(server_url, headers, "evaluate_offer", {"offer_usd": 30_000})

    assert result.is_error  # type: ignore[attr-defined]


@pytest.mark.db
async def test_missing_game_header_is_an_error(server_url: str) -> None:
    result = await call(
        server_url, {"X-Haggle-Token": "seller-test-token"}, "evaluate_offer", {"offer_usd": 30_000}
    )

    assert result.is_error  # type: ignore[attr-defined]
