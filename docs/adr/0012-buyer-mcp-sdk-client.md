# ADR-0012: The buyer calls MCP with the official SDK client, not langchain-mcp-adapters

- **Status:** Accepted (2026-10-09, week 5)
- **Date:** 2026-10-09

## Context

The plan (docs/05, week 5) had the LangGraph buyer read the reference sheets through
`langchain-mcp-adapters`, which turns MCP tools into LangChain tools.

When installing it on 2026-10-09:

- `langchain-mcp-adapters` **0.3.2** (latest, 2026-08-06) requires **`mcp<2.0.0`**. No release
  supports the MCP Python SDK v2 **[verified on PyPI]**.
- This workspace runs **`mcp` 2.3.0**: the MCP server is built on SDK v2 (stateless HTTP,
  `Context.headers`, built-in tracing), and the seller's ADK toolset uses it too.
- A uv workspace has **one lockfile** (ADR-0001): two services cannot pin different major
  versions of the same package.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. Official SDK v2 client** (`mcp.Client` + `streamable_http_client`) in a small `McpCatalog` class | No new dependency. Same SDK as the server. Typed results (`structured_content` → our `SheetResultsOut`). One session for several queries | ~40 lines of our own code. No automatic "MCP tool → LangChain tool" conversion |
| B. Downgrade the whole workspace to `mcp` 1.x | Adapters work as documented | Loses SDK v2 features the server depends on; a step back for one library |
| C. Take the buyer out of the workspace (own lockfile) | Each service pins what it wants | Two lockfiles, two venvs, CI and Docker builds get more complex. Defeats ADR-0001 |
| D. Vendor or fork the adapter | Keeps the LangChain tool interface | Maintenance burden for an unofficial fork |

## Decision

**A.** `haggle_buyer/catalog.py` opens one MCP session with the `catalog` token, calls
`lookup_model_sheet` for each query and validates the result with the shared Pydantic contract.

## Why

The buyer does not need the model to *choose* tools: the appraisal step always looks up the same
three things (price guide, known issues, what drives value). So a plain function is enough, and
deterministic retrieval is cheaper and easier to test than a tool-calling loop. "One MCP server,
two agent frameworks" still holds: ADK through its `McpToolset`, LangGraph through the SDK client.

## Consequences

- The `catalog` scope is enforced by the server (ADR-0008), whatever client is used.
- If the buyer ever needs tool-calling over MCP, wrap `McpCatalog.lookup` in a LangChain
  `StructuredTool` (a few lines) rather than adding the adapter.

## Revisit when

`langchain-mcp-adapters` publishes a release that supports `mcp>=2`.
