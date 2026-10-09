# ADR-0006: Seller = A2A server, buyer = A2A client, no LangGraph Agent Server

- **Status:** Proposed. Confirm after spikes S2/S6.
- **Date:** 2026-10-08

## Context

The brief says seller and buyer communicate over A2A. Re-confirmed on 2026-10-08:

- **ADK exposes agents with `to_a2a()`**: `from google.adk.a2a.utils.agent_to_a2a import to_a2a`; parameters `agent, host, protocol, port, agent_card, runner, lifespan`; serves `/.well-known/agent-card.json`; install `google-adk[a2a]`. **Experimental.** Supports a2a-sdk 0.3.x and 1.x with auto-detection. **[verified]**
- **ADK consumes remote agents with `RemoteA2aAgent`**: `from google.adk.agents.remote_a2a_agent import RemoteA2aAgent`; parameters `name, description, agent_card` (URL, object or file), `use_legacy=False` for the newer A2A extension. **Experimental.** **[verified]**
- **LangGraph Agent Server has an A2A endpoint** at `/a2a/{assistant_id}`. Requires `langgraph-api >= 0.4.21` (≥ 0.13.0 recommended). Speaks A2A 1.0 JSON-RPC and accepts 0.3 method names. The graph state needs a `messages` key. `contextId` maps to `thread_id` and must be a UUID. **[verified]**
- **But** self-hosting a *standalone* Agent Server requires `LANGGRAPH_CLOUD_LICENSE_KEY` (validated at startup against `beacon.langchain.com`) plus **Postgres and Redis**. Secondary sources say an Enterprise plan is needed **[verified: key + Postgres + Redis; plan requirement unverified]**. `langgraph dev` is for local development.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. Buyer is an A2A client, seller is an A2A server** (buyer drives the loop) | One A2A hop. Buyer stays a plain library (runs in the CLI, evals, or inside the api). Matches the brief. | Buyer is not discoverable as an agent. |
| **B. Referee pattern:** api is an A2A client of both, buyer served by the LangGraph Agent Server | Symmetric. The referee owns turn caps for both sides. | Agent Server self-hosting needs a license key + Postgres + Redis. A second server to deploy. |
| **C. Buyer exposed with our own a2a-sdk server wrapper** | Symmetric without Agent Server. | Extra code for no MVP feature. |
| **D. No A2A** (direct function calls) | Simplest. | Drops a requirement and a learning goal. |

## Decision

**A.** The seller is the only A2A server. The api (for human players) and the buyer (for agent games) are both A2A clients, using `a2a-sdk` 1.x `create_client(...)` with a custom `httpx.AsyncClient` that adds the Google ID token.

The seller is the **authority** for turns (atomic reservation) and transcripts, so caps hold whoever the client is. The api still gates games, rate limits and budget, because only the api can create games.

## Why

It keeps one protocol hop and one server to secure, while still showing A2A interoperability across frameworks (LangGraph → ADK). That is the interesting claim.

## Where `RemoteA2aAgent` and Agent Server would fit (not MVP)

- "Bring your own buyer": publish the seller's A2A endpoint with per-key quotas. Third parties connect with any A2A client.
- An ADK "coach" agent that consumes the seller via `RemoteA2aAgent` to suggest moves to human players.
- Exposing the buyer through `langgraph dev` locally to try the Agent Server A2A endpoint as a learning exercise (1–2 h, Could).

## Consequences

- The A2A experimental status is contained behind `seller/a2a_app.py` (server) and `haggle_core/a2a_client.py` (client).
- Contract tests validate the DataPart payload (`haggle.seller_turn.v1`) so upgrades can't silently break the buyer.
