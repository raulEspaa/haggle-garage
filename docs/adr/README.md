# Architecture Decision Records

Format: a lightweight version of [MADR](https://adr.github.io/madr/). Each record has context, the options considered with pros and cons, the decision, the reasoning behind it, its consequences, and when to revisit it.
An ADR is **immutable once Accepted**. To change a decision, write a new ADR that supersedes the old one.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-monorepo-uv-workspace.md) | Monorepo with a uv workspace | Accepted (spike, 2026-10-09) |
| [0002](0002-home-mcp-ingress.md) | Home MCP ingress: Cloudflare Tunnel + Access (Tailscale for admin) | Proposed (needs domain: open decision #1) |
| [0003](0003-gemini-api-vs-vertex.md) | Gemini API (AI Studio) over Vertex AI / Agent Platform | Superseded by 0013 |
| [0004](0004-langfuse-cloud.md) | Langfuse Cloud (Hobby) over self-hosted | Proposed |
| [0005](0005-neon-postgres.md) | Neon Postgres (free) as the single shared database | Proposed |
| [0006](0006-agent-topology.md) | Seller = A2A server, buyer = A2A client, no LangGraph Agent Server | Accepted (spike, 2026-10-09) |
| [0007](0007-guard-ladder.md) | Guard ladder: the model talks, code decides | Proposed (confirm A12) |
| [0008](0008-trusted-context-headers.md) | Trusted context via headers, never LLM arguments | Accepted (spike, 2026-10-09) |
| [0009](0009-server-rendered-ui.md) | Server-rendered web UI, no SPA | Proposed |
| [0010](0010-fictional-car-models.md) | Fictional car models for synthetic data and RAG | Superseded by 0011 |
| [0011](0011-real-iconic-cars.md) | Real iconic cars (1960s-1980s) with dealer-specific synthetic data | Accepted |
| [0012](0012-buyer-mcp-sdk-client.md) | The buyer calls MCP with the official SDK client, not langchain-mcp-adapters | Accepted |
| [0013](0013-gemini-on-vertex-ai.md) | Gemini through Vertex AI with ADC, paid by the trial credit | Accepted |

Status flow: `Proposed` → `Accepted` (after your review, or after the Week 2 spike for 0001/0006/0008) → `Superseded by NNNN` when replaced.
