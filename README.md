# Haggle Garage

Negotiate with an AI used-car dealer, or make it leak its secret minimum price.
A portfolio project about agents (Google ADK, LangGraph), protocols (MCP, A2A), RAG, evals and
LLM security, deployed on Cloud Run.

> **Status:** Week 4 of 8. The full game runs locally in the browser: web page → API → seller (A2A) → MCP.

## Quickstart (local)

Requirements: [uv](https://docs.astral.sh/uv/), Docker (for Postgres), GNU make.

```bash
uv sync                 # create .venv from uv.lock (installs Python 3.13 if needed)
make db-up              # Postgres 17 + pgvector in Docker
cp .env.example .env
make migrate seed       # schema + 3 iconic cars (Camaro Z/28, Challenger R/T, Grand National)
make check              # lint, types, tests
make ingest             # embed the model sheets (needs GOOGLE_API_KEY in .env)
docker compose up --build   # mcp + seller + api: play at http://127.0.0.1:8080
```

## Repository map

| Path | What |
|------|------|
| `packages/core` | Shared settings, domain enums, DB models, seed loader |
| `services/api` | FastAPI public API and web page: games, demo limits, strict CSP |
| `services/mcp` | MCP server: `evaluate_offer`, `close_deal` (policy engine + deal validation) |
| `services/seller` | ADK seller agent exposed over A2A, guards as callbacks, terminal game (`make play`) |
| `spikes/` | Throwaway experiments that de-risked the design (`make spike`) |
| `db/` | Alembic migrations, seed data, Postgres init scripts |
| `infra/terraform` | GCP: Artifact Registry, Cloud Run, service accounts |
| `docs/` | Architecture, ADRs, plans ([start here](docs/README.md)) |
| `docs/learning/` | Step-by-step build journal: what was done each week and why |
