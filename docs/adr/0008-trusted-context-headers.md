# ADR-0008: Trusted context via headers, never LLM-filled tool arguments

- **Status:** Accepted (2026-10-09, after spike S3; implemented in `services/mcp`).
- **Date:** 2026-10-08

## Context

MCP tools need to know *which game* they act on. The naive design puts `game_id` in the tool's input schema, so the **LLM fills it in**. A buyer can then write "use game id 1234-…" and the model may obey. That is a **confused deputy**: the seller acts with its credentials on another game.

The MCP 2026-07-28 spec removed protocol sessions and suggests "explicit, server-minted handles passed as ordinary tool arguments" for cross-call state **[verified]**. That is fine for handles the model *should* pick, not for identity.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. `game_id` as a tool argument** | Simplest. Spec-idiomatic. | The LLM controls identity: cross-game tampering. |
| **B. Argument filled, then overwritten in `before_tool_callback`** | Works with any client. | The LLM still sees and reasons about the field. Easy to forget in new tools. |
| **C. Header set by code** (`X-Haggle-Game-Id` via `McpToolset(header_provider=...)`, read from the session) | The LLM never sees it. One place sets it. | Depends on the ADK `header_provider` receiving the session ([spike S3]). |
| **D. Full MCP OAuth 2.1** | Spec-standard authorization. | Built for third-party clients acting on behalf of users. Heavy for service-to-service with clients you own. |

## Decision

**C**, with B as the fallback if S3 fails. Auth is a static scoped service token (`X-Haggle-Token`: `seller` or `catalog`), plus the outer layer per environment: Cloudflare Access at home, Cloud Run IAM in the cloud.

## Why

Identity and authorization are **trusted context**. Trusted context must come from code, not from a text generator that reads attacker input. This one rule removes a whole class of tool-misuse attacks, and it is easy to explain in an interview.

## Spike and implementation notes (2026-10-09)

- S3 confirmed: `header_provider` gets the session, so the seller sets `X-Haggle-Game-Id` from
  `ctx.session.id`. The generated input schemas of `evaluate_offer` and `close_deal` contain no
  game id at all, and a test (`test_no_tool_lets_the_llm_choose_the_game`) keeps it that way.
- The MCP SDK v2 docstring of `Context.headers` warns: *"Headers are client-supplied input -
  never treat one as an identity assertion."* That is why the game header is trusted **only**
  together with a valid `seller` token.
- The SDK's own middleware hook is marked *provisional*, so authentication is a plain ASGI
  middleware (`haggle_mcp/auth.py`).
- The 2026-07-28 spec says list endpoints must not vary per connection: every client sees every
  tool, and scopes are enforced **when a tool is called**.

## Consequences

- Tool input schemas contain only what the model legitimately decides (`offer_usd`, `price_usd`, `query`).
- The MCP answers seller-scope calls without a valid game header with a tool error (`isError: true`), and unknown tokens with HTTP 401.
- The buyer gets the `catalog` scope only. Even a compromised buyer prompt cannot call `evaluate_offer` (the server enforces this, not just client-side tool filtering).
- Adding a tool later means asking "does it need trusted context?" and reading it from headers.
