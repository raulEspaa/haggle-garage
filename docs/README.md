# Haggle Garage — documentation

A web game where a **seller agent** (Google ADK + Gemini) sells an iconic 1960s–1980s American
car with a **secret per-game floor price**. A human player, or a **buyer agent** (LangGraph, three
personas), tries to lower the price or extract the floor. Three security levels show how the
protection improves, from "floor in the prompt" to "the model never sees the floor", and the
project measures each level with simulated negotiations and a prompt-injection attack set.

**Play it:** https://haggle-api-38346102533.europe-west1.run.app · **Status:** complete (8 weeks,
2026-10). Author: Raúl.

## Reading order

| # | Document | Answers |
|---|----------|---------|
| 1 | [01-vision-and-scope.md](01-vision-and-scope.md) | What we build, what we don't, how we know it worked |
| 2 | [02-architecture.md](02-architecture.md) | Components, turn sequence, deployment, game state machine, failure modes |
| 3 | [03-contracts.md](03-contracts.md) | MCP tool schemas, A2A messages, REST endpoints, data model, database roles |
| 4 | [adr/](adr/README.md) | 13 decision records with alternatives and reasons |
| 5 | [05-delivery.md](05-delivery.md) | Plan vs shipped, cuts, costs, risks, tooling, C#→Python map, versions and sources, future work |
| 6 | [06-evaluation-plan.md](06-evaluation-plan.md) | Metrics, datasets, leak detection, judge calibration |
| 7 | [07-threat-model.md](07-threat-model.md) | Prompt injection, demo abuse, secrets and supply chain |
| — | [results/](results/README.md) | Eval reports (L1 vs L2 vs L3) and the production deploy checklist |
| — | [learning/](learning/README.md) | The build journal: one chapter per week, with C# analogies and exercises |

Documents 01–07 were written as the Phase 1 design (2026-10-08) and updated as the build went.
Where the build differed from the design, the document says so and links the ADR.

## Key decisions at a glance

| Topic | Decision | ADR |
|-------|----------|-----|
| Repository | Monorepo, **uv workspace**, one lockfile, one Dockerfile per service | [0001](adr/0001-monorepo-uv-workspace.md) |
| LLM access | **Gemini on Vertex AI** with Application Default Credentials, paid by the GCP trial credit (supersedes the AI Studio plan of [0003](adr/0003-gemini-api-vs-vertex.md)) | [0013](adr/0013-gemini-on-vertex-ai.md) |
| Agent topology | Seller is an A2A **server** (`to_a2a`). Buyer is an A2A **client**. No LangGraph Agent Server | [0006](adr/0006-agent-topology.md) |
| Guardrails | "Model talks, code decides": a guard ladder per level, with pricing decided in the MCP policy engine | [0007](adr/0007-guard-ladder.md) |
| Trusted context | The game id travels in an HTTP header set by code, never in an LLM-filled tool argument | [0008](adr/0008-trusted-context-headers.md) |
| Database | **Neon Postgres + pgvector** in production, one least-privilege role per service; Docker Postgres locally | [0005](adr/0005-neon-postgres.md) |
| Tracing | **Langfuse Cloud Hobby (EU)**, one trace per game across buyer → seller → MCP | [0004](adr/0004-langfuse-cloud.md) |
| Web UI | Server-rendered page + vanilla JS, strict CSP. No SPA | [0009](adr/0009-server-rendered-ui.md) |
| Inventory data | **Real iconic cars** with sourced facts; prices and dealer notes fictional | [0011](adr/0011-real-iconic-cars.md) |
| Buyer's MCP client | The official MCP SDK client (`langchain-mcp-adapters` requires `mcp<2`) | [0012](adr/0012-buyer-mcp-sdk-client.md) |
| Home MCP ingress | Cloudflare Tunnel + Access service token: **designed, deferred** (not built) | [0002](adr/0002-home-mcp-ingress.md) |

## Assumptions the design rests on

| ID | Assumption |
|----|-----------|
| A1 | Demo UI and agents speak **English**. The attack set includes Spanish and other languages, because language switching is a classic bypass |
| A2 | Prices are in **USD**, whole dollars (integers) |
| A3 | Region **europe-west1** for Cloud Run, Neon in AWS **eu-central-1**, Langfuse **EU**, Vertex AI location `global` |
| A4 | Models: seller and buyer `gemini-3.1-flash-lite`, judge `gemini-3.8-flash`, embeddings `gemini-embedding-2` at 768 dims |
| A5 | Players are anonymous: no accounts, no leaderboard |
| A6 | Each game samples a **non-round** floor (for example 27,385) from the car's policy range |
| A11 | A game has at most **12 buyer turns** and expires after **30 minutes** idle |
| A12 | At **Levels 1–2 the LLM decides concessions** (the vulnerable design under study). **Closing is validated in code at every level.** At Level 3 the code also decides prices |

## Verification labels

Some documents tag facts as **[verified 2026-10-08]** (checked against official docs, PyPI or a
vendor pricing page), **[unverified]** (an assumption) or **[spike]** (proven later in the week 2
tracer bullet). The facts that mattered, and the ones only learned by running the code, are in
[05-delivery.md §7](05-delivery.md#7-key-versions-and-verified-facts).
