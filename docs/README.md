# Haggle Garage — Phase 1: Plan & Architecture

> Working name: **Haggle Garage** (package prefix `haggle`). Renaming is an open decision.
> Author: Raúl · Phase 1 drafted 2026-10-08 · Status: **Draft for review**
> Phase 1 contains no implementation code. It covers documents, diagrams and interface contracts.

A web game where a **seller agent** (Google ADK + Gemini) sells an iconic 1960s–1980s American car with a **secret per-game floor price**.
A human player, or a **buyer agent** (LangGraph, three personas), tries to lower the price or extract the floor.
Three security levels show how the protection improves, from "floor in the prompt" to "the model never sees the floor".
The project measures each level with simulated negotiations and a prompt-injection attack set.

## Reading order

| # | Document | Answers |
|---|----------|---------|
| 1 | [01-vision-and-scope.md](01-vision-and-scope.md) | What we build, what we don't, how we know it worked. Over-engineering review. |
| 2 | [02-architecture.md](02-architecture.md) | Components, turn sequence, deployment, game state machine, failure modes. |
| 3 | [03-contracts.md](03-contracts.md) | MCP tool schemas, A2A messages, REST endpoints, data model. |
| 4 | [adr/](adr/README.md) | Decision records with alternatives and reasons. |
| 5 | [05-delivery-plan.md](05-delivery-plan.md) | 8-week plan, definition of done, learning goals, cut list. |
| 6 | [06-evaluation-plan.md](06-evaluation-plan.md) | Metrics, datasets, leak detection. |
| 7 | [07-threat-model.md](07-threat-model.md) | Prompt injection, demo abuse, home-server exposure. |
| 8 | [08-risks-and-costs.md](08-risks-and-costs.md) | Project risks and cost estimate. |
| 9 | [09-repo-and-tooling.md](09-repo-and-tooling.md) | Repository layout, package manager, linter, tests, CI. C#→Python map. |
| 10 | [10-sources.md](10-sources.md) | Verification log: every version/API/price claim with its source and status. |

## Key decisions at a glance

| Topic | Decision | ADR |
|-------|----------|-----|
| Repository | Monorepo, **uv workspace**, one lockfile, one Dockerfile per service | [0001](adr/0001-monorepo-uv-workspace.md) |
| Home MCP ingress | **Cloudflare Tunnel + Access service token**. Tailscale stays for admin access only | [0002](adr/0002-home-mcp-ingress.md) |
| LLM access | **Gemini API (AI Studio)**: free-tier project for dev, prepaid project with a hard spend cap for the demo | [0003](adr/0003-gemini-api-vs-vertex.md) |
| Tracing | **Langfuse Cloud Hobby (EU)**. No self-hosting | [0004](adr/0004-langfuse-cloud.md) |
| Database | **Neon Postgres free tier + pgvector**, shared by all services. Local Docker Postgres for dev | [0005](adr/0005-neon-postgres.md) |
| Agent topology | Seller is an A2A **server** (`to_a2a`). Buyer is an A2A **client**. No LangGraph Agent Server | [0006](adr/0006-agent-topology.md) |
| Guardrails | "Model talks, code decides": a guard ladder per level, with pricing decided in the MCP policy engine | [0007](adr/0007-guard-ladder.md) |
| Trusted context | Game id goes in an HTTP header set by code. It is never an LLM-filled tool argument | [0008](adr/0008-trusted-context-headers.md) |
| Web UI | Server-rendered page + vanilla JS. No SPA | [0009](adr/0009-server-rendered-ui.md) |
| Inventory data | **Real iconic cars** with sourced facts; prices and dealer notes fictional (supersedes 0010) | [0011](adr/0011-real-iconic-cars.md) |

## Verification labels used in these docs

- **[verified 2026-10-08]**: checked today against official docs, PyPI or the vendor pricing page. See [10-sources.md](10-sources.md).
- **[unverified]**: not confirmed from an official source. Treat it as an assumption.
- **[spike]**: the API exists, but its exact behaviour must be proven in the Week 2 tracer bullet before we depend on it.

## Assumptions (made because they didn't block the design; confirm or override)

| ID | Assumption |
|----|-----------|
| A1 | Demo UI and agents speak **English**. The attack set includes Spanish and other languages, because language switching is a classic bypass. |
| A2 | Prices are in **USD**, as whole dollars (integers). |
| A3 | Region **europe-west1** for Cloud Run, Neon in AWS **eu-central-1**, Langfuse **EU**. |
| A4 | Models (configurable per role): seller `gemini-3.1-flash-lite`, buyer `gemini-3.1-flash-lite`, judge `gemini-3.8-flash`, embeddings `gemini-embedding-2` at 768 dims. Week 6 evaluates the seller model as a variable. |
| A5 | Players are anonymous: no accounts, no leaderboard. |
| A6 | Each game samples a **non-round** floor (for example 27,385) from the car's policy range. |
| A7 | Tool names are in English in code: `evaluar_oferta` → `evaluate_offer`, `cerrar_trato` → `close_deal`, `consultar_ficha` → `lookup_model_sheet`. |
| A8 | Public GitHub repo with CI on GitHub Actions. Cloud deploys run `terraform apply` from your machine. CI-driven deploys are a stretch goal. |
| A9 | You own or will buy a domain that you can put on Cloudflare (about 10 USD/year). If not, ADR-0002 describes the Tailscale Funnel fallback. |
| A10 | Python **3.13**. |
| A11 | A game has at most **12 buyer turns** and expires after **30 minutes** idle. |
| A12 | At **Levels 1–2 the LLM decides concessions** (that is the vulnerable design under study). **Closing is validated in code at every level.** At Level 3 the code also decides prices. |

## Open decisions (yours to make)

1. **Domain for Cloudflare Tunnel** (recommended), or Tailscale Funnel with app-level auth only. → ADR-0002
2. **Monthly LLM spend cap** for the public demo (proposal: 10 USD prepaid + AI Studio monthly cap, 1.00 USD/day soft budget ≈ 60 games/day). → 07 §5, 08
3. **Demo language**: English only (A1), or bilingual.
4. **Confirm A12**: the "model talks, code decides" principle applies fully only at L3. At L1–L2 only closing is code-validated, by design.
5. **Public "AI vs AI" mode** in the demo (should-have; costs about 2× a human game), or CLI/evals only.
6. **Project and repo name.**
7. **Transcript retention** in the public demo (proposal: 30 days, then delete; IPs stored only as salted hashes).
8. **Game balance**: floor-guess success threshold (proposal ±1.5%) and minimum counter margin (proposal 3%). → 03
9. **Deploys**: manual `terraform apply` (default), or CI with Workload Identity Federation (stretch).
10. **Later, not MVP**: a public A2A endpoint for "bring your own buyer agent".
