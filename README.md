# Haggle Garage

**Talk an AI car dealer down, or make it leak its secret minimum price.**

[![CI](https://github.com/raulEspaa/haggle-garage/actions/workflows/ci.yml/badge.svg)](https://github.com/raulEspaa/haggle-garage/actions/workflows/ci.yml)
[![Live demo](https://img.shields.io/badge/demo-live%20on%20Cloud%20Run-c0392b)](https://haggle-api-38346102533.europe-west1.run.app)
![Python 3.13](https://img.shields.io/badge/python-3.13-3776ab)
![Google ADK](https://img.shields.io/badge/agents-Google%20ADK%20%2B%20LangGraph-4285f4)
![MCP + A2A](https://img.shields.io/badge/protocols-MCP%20%2B%20A2A-6f42c1)

**▶ Play it: https://haggle-api-38346102533.europe-west1.run.app**

Sam, an AI salesperson, sells one iconic American car per game: a '69 Camaro Z/28, a '70
Challenger R/T or an '87 Buick Grand National. Every game has a **secret floor price** that Sam
must never reveal. You win by buying cheap, or by guessing the floor within 1.5 %.

The car lot is a pretext. The real question is an LLM-security one: **how do you stop an
agent from leaking a secret it needs to do its job?** The game answers it with three security
levels, and an eval suite measures each one.

<p align="center"><img src="docs/assets/game.png" alt="A Level 1 game: the player asks Sam for the lowest price it is allowed to accept" width="720"></p>

## Three levels, three generations of LLM-app security

| | Level 1 · Naive | Level 2 · Hardened | Level 3 · Blind |
|---|---|---|---|
| **Where's the floor?** | in the system prompt | in the system prompt | **nowhere the model can see** |
| **Defences** | none (the baseline) | defensive prompt, output leak filter, canary token | prices come only from a code policy engine over MCP; a price guard rejects any number code didn't issue |
| **Who decides prices?** | the model | the model | **code**: "the model talks, code decides" |
| **Closing a deal** | validated in code | validated in code | validated in code, and must match a prior *accept* from the policy engine |

At every level, **a sale below the floor is impossible**: the database and the MCP server refuse
it. Lower levels can only *say* too much.

## Results

Final run: 81 simulated negotiations (3 cars × 3 buyer personas × 3 seeds per level) plus 264
scripted prompt-injection attacks (44 attacks in 17 categories, mapped to the OWASP LLM Top 10).
Total cost **$1.82**. [Full report →](docs/results/README.md)

| Per level | L1 Naive | L2 Hardened | L3 Blind |
|---|:-:|:-:|:-:|
| Games where the seller disclosed its floor | **22 %** | **0 %** | **0 %** |
| Attacks that extracted the floor | 28 % | 0 % | 0 % |
| How far off the buyer's floor guess was (higher = safer) | 3 % | 13 % | 18 % |
| Sales below the floor | 0 | 0 | 0 |
| Cost per game | $0.011 | $0.013 | $0.030 |

What it shows:

- **A naive agent leaks.** Role play, system-prompt extraction and "answer in JSON" tricks beat
  L1 most often.
- **Prompt hardening plus an output filter stopped every scripted attack.** But the secret is
  still in the prompt, one clever attack away.
- **Not giving the model the secret is the only structural fix.** L3 can't leak what it never
  sees. It costs ~2.5× per game and closes more slowly, because every price is a tool call.
- **The numbers are honest:** 95 % Wilson confidence intervals, an LLM judge calibrated against
  labelled data (Cohen's κ = 0.84), and a first run that was discarded when a budget limit
  corrupted it.

## How it works

```mermaid
flowchart LR
    player["👤 Player<br/>browser"] -->|HTTPS| api
    buyer["🤖 Buyer agent<br/>LangGraph · 3 personas"] -->|A2A| seller

    subgraph cloud["Google Cloud Run"]
        api["api<br/>FastAPI · web page<br/>rate limits · budget"]
        seller["seller agent<br/>Google ADK<br/>guards as callbacks"]
        mcp["MCP server<br/>policy engine · deals · RAG"]
    end

    api -->|"A2A + ID token"| seller
    seller -->|"MCP + ID token"| mcp
    buyer -->|"MCP: car facts"| mcp

    api & seller & mcp --> db[("Postgres + pgvector<br/>one DB role per service")]
    seller & mcp & buyer --> gemini["Gemini<br/>Vertex AI"]
    seller & mcp & buyer -.-> langfuse["Langfuse<br/>one trace per game"]
```

One turn at Level 3, the "model talks, code decides" pattern:

```mermaid
sequenceDiagram
    actor P as Player
    participant S as Seller (ADK)
    participant G as Gemini
    participant M as MCP policy engine
    P->>S: "I'll give you $80,000"
    S->>G: conversation (no floor in the prompt)
    G-->>S: call evaluate_offer(80000)
    Note over S: guard: is $80,000 really in the player's message?
    S->>M: evaluate_offer + game id in a header set by code
    M-->>S: counter at $91,500 (computed from the secret floor)
    S->>G: tool result
    G-->>S: "I can do $91,500 for this numbers-matching car."
    Note over S: guard: every price must be one code issued
    S-->>P: reply + structured price
```

**Highlights**

- **Two agent frameworks, two protocols.** The seller is a Google ADK agent served over **A2A**;
  the buyer is a **LangGraph** graph that talks to it over A2A and appraises the car through the
  same **MCP** server.
- **Security enforced below the prompt.** The game id travels in headers set by code, never in
  LLM-filled arguments. The seller's database role *cannot read* the floor column. Private
  services accept only Google-signed ID tokens with their own audience.
- **RAG** over hand-written model sheets of real, sourced facts (pgvector, Gemini embeddings).
- **Property-based tests** (Hypothesis) on the pricing engine; guards tested with a scripted
  model, so no LLM calls in CI.
- **A public demo that can't run up a bill:** per-IP and global limits, a $2/day budget enforced
  by two services, 2 instances max, a budget alert, a kill switch. Every guardrail was
  [verified from outside](docs/results/deploy-checklist.md).

## Tech stack

| | |
|---|---|
| **Agents** | Google ADK 2.11 (seller), LangGraph 1.2 (buyer), Gemini 3.1 Flash-Lite on Vertex AI |
| **Protocols** | A2A 1.0 (`a2a-sdk`), MCP (Python SDK v2, Streamable HTTP) |
| **Backend** | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| **Data** | PostgreSQL 17 + pgvector (Neon in production) |
| **Evals** | deterministic leak detector, LLM-as-judge (Gemini 3.8 Flash) with κ calibration, Wilson CIs |
| **Observability** | Langfuse via OpenTelemetry, one trace per game across buyer → seller → MCP |
| **Infra** | Docker, Cloud Run, Terraform, Secret Manager, Artifact Registry |
| **Quality** | uv workspace, ruff, mypy strict, pytest + Hypothesis, pre-commit with gitleaks, GitHub Actions |

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/), Docker, GNU make, and the
[gcloud CLI](https://cloud.google.com/sdk/docs/install) for Gemini on Vertex AI.

```bash
uv sync                                 # create .venv from uv.lock (installs Python 3.13 if needed)
make db-up                              # Postgres 17 + pgvector in Docker
cp .env.example .env                    # then set your GCP project (see the comments inside)
gcloud auth application-default login   # Gemini through Vertex AI, no API key
make migrate seed ingest                # schema, 3 cars, embedded model sheets
make check                              # lint, types, tests
docker compose up --build               # play at http://127.0.0.1:8080
```

More: `make play LEVEL=3` (play in the terminal), `make buyer` (watch the buyer agent negotiate),
`make eval-smoke` (a ~3-minute eval run), `make help` (everything else).

## Repository map

| Path | What |
|------|------|
| [`services/seller`](services/seller) | ADK seller agent over A2A; prompts per level; guards as callbacks |
| [`services/mcp`](services/mcp) | MCP server: `evaluate_offer`, `close_deal`, `lookup_model_sheet` (policy engine, deal validation, RAG) |
| [`services/api`](services/api) | FastAPI API and web page: games, demo limits, strict CSP |
| [`services/buyer`](services/buyer) | LangGraph buyer agent: personas, appraisal over MCP, its own guard |
| [`packages/core`](packages/core) | Shared contracts, settings, DB models, the pure-function policy engine, leak detector |
| [`evals`](evals) | Simulation matrix, attack set, judge, calibration, reports |
| [`infra/terraform`](infra/terraform) | 3 Cloud Run services, service accounts + IAM, secrets, budget |
| [`db`](db) | Alembic migrations, seed data, model sheets |
| [`docs`](docs/README.md) | Architecture, contracts, threat model, 13 ADRs, results |
| [`docs/learning`](docs/learning/README.md) | The build journal: what was built each week, and why |

## Documentation

- [Architecture](docs/02-architecture.md) · [Threat model](docs/07-threat-model.md) ·
  [Evaluation plan](docs/06-evaluation-plan.md) · [Contracts](docs/03-contracts.md)
- [Architecture decision records](docs/adr/README.md): 13 decisions with the alternatives
- [Eval results](docs/results/README.md) and the [production deploy checklist](docs/results/deploy-checklist.md)
- [Delivery](docs/05-delivery.md): plan vs shipped, what was cut, real costs, future work
- [Build journal](docs/learning/README.md): eight chapters, one per week

## About

Built in eight weeks (October 2026) by Raúl as a hands-on project to learn agent engineering
end to end: protocols, RAG, evals, LLM security and cloud deployment. Cars are real models
described with public facts; every listing and price is fictional. Not affiliated with any
manufacturer.
