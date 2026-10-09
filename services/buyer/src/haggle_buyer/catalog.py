"""The buyer reads the reference sheets through the SAME MCP server as the seller.

It authenticates with the `catalog` token, whose scope only allows `lookup_model_sheet`
(docs/03-contracts.md §1.2): the pricing tools refuse it.

Why not langchain-mcp-adapters? Its latest release (0.3.2) requires `mcp<2`, and this workspace
runs the MCP SDK v2 (one lockfile for all services). The official SDK client is a few lines
(ADR-0012).
"""

from typing import Protocol

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from haggle_core.contracts import SheetHitOut, SheetResultsOut


class CatalogUnavailableError(Exception):
    pass


class SheetLookup(Protocol):
    async def lookup(self, queries: list[str], top_k: int = 3) -> list[SheetHitOut]: ...


class McpCatalog:
    def __init__(self, url: str, token: str, timeout_s: float = 20.0) -> None:
        self._url = url
        self._token = token
        self._timeout_s = timeout_s

    async def lookup(self, queries: list[str], top_k: int = 3) -> list[SheetHitOut]:
        """Run several searches over ONE MCP session; drop duplicate chunks."""
        hits: dict[tuple[str, str], SheetHitOut] = {}
        try:
            async with (
                httpx2.AsyncClient(
                    headers={"X-Haggle-Token": self._token}, timeout=self._timeout_s
                ) as http,
                Client(streamable_http_client(self._url, http_client=http)) as client,
            ):
                for query in queries:
                    result = await client.call_tool(
                        "lookup_model_sheet", {"query": query, "top_k": top_k}
                    )
                    if result.is_error:
                        raise CatalogUnavailableError("lookup_model_sheet returned an error")
                    for hit in SheetResultsOut.model_validate(result.structured_content).results:
                        hits.setdefault((hit.sheet_slug, hit.section), hit)
        except CatalogUnavailableError:
            raise
        except Exception as exc:  # network, auth, protocol: the appraisal falls back to the listing
            raise CatalogUnavailableError(type(exc).__name__) from exc
        return list(hits.values())
