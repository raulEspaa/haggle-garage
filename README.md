# Haggle Garage

Negotiate with an AI used-car dealer, or make it leak its secret minimum price.
A portfolio project about agents (Google ADK, LangGraph), protocols (MCP, A2A), RAG, evals and
LLM security, deployed on Cloud Run.

> **Status:** Week 6 of 8. Measured: L1 states its secret floor in 22% of simulated games; L2 and L3 in 0%, and both stop all 44 scripted attacks ([results](docs/results/README.md)).

## Quickstart (local)

Requirements: [uv](https://docs.astral.sh/uv/), Docker (for Postgres), GNU make.

```bash
uv sync                 # create .venv from uv.lock (installs Python 3.13 if needed)
make db-up              # Postgres 17 + pgvector in Docker
cp .env.example .env
make migrate seed       # schema + 3 iconic cars (Camaro Z/28, Challenger R/T, Grand National)
make check              # lint, types, tests
make ingest             # embed the model sheets (Gemini on Vertex AI: gcloud ADC, see .env.example)
docker compose up --build   # mcp + seller + api: play at http://127.0.0.1:8080
```

## Repository map

| Path | What |
|------|------|
| `packages/core` | Shared settings, domain enums, DB models, seed loader |
| `services/api` | FastAPI public API and web page: games, demo limits, strict CSP |
| `services/mcp` | MCP server: `evaluate_offer`, `close_deal` (policy engine + deal validation) |
| `services/buyer` | LangGraph buyer agent: personas, appraisal over MCP, code guard, A2A client (`make buyer`) |
| `evals` | Eval suite: leak detector, LLM judge, scripted attacks, simulated games, reports (`make eval-smoke`) |
| `services/seller` | ADK seller agent exposed over A2A, guards as callbacks, terminal game (`make play`) |
| `spikes/` | Throwaway experiments that de-risked the design (`make spike`) |
| `db/` | Alembic migrations, seed data, Postgres init scripts |
| `infra/terraform` | GCP: Artifact Registry, Cloud Run, service accounts |
| `docs/` | Architecture, ADRs, plans ([start here](docs/README.md)) |
| `docs/learning/` | Step-by-step build journal: what was done each week and why |
