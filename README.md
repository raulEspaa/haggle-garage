# Haggle Garage

Negotiate with an AI used-car dealer, or make it leak its secret minimum price.
A portfolio project about agents (Google ADK, LangGraph), protocols (MCP, A2A), RAG, evals and
LLM security, deployed on Cloud Run.

> **Status:** Week 1 of 8. Foundations and walking skeleton. Nothing playable yet.

## Quickstart (local)

Requirements: [uv](https://docs.astral.sh/uv/), Docker (for Postgres), GNU make.

```bash
uv sync                 # create .venv from uv.lock (installs Python 3.13 if needed)
make db-up              # Postgres 17 + pgvector in Docker
cp .env.example .env
make migrate seed       # schema + 3 fictional cars
make check              # lint, types, tests
make api                # http://127.0.0.1:8080/healthz
```

## Repository map

| Path | What |
|------|------|
| `packages/core` | Shared settings, domain enums, DB models, seed loader |
| `services/api` | FastAPI public API (health endpoint only, for now) |
| `db/` | Alembic migrations, seed data, Postgres init scripts |
| `infra/terraform` | GCP: Artifact Registry, Cloud Run, service accounts |
| `docs/` | Architecture, ADRs, plans ([start here](docs/README.md)) |
| `docs/learning/` | Step-by-step build journal: what was done each week and why |
