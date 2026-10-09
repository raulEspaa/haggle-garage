# 01 — Vision and Scope

## 1. Pitch

> *"Talk a 1970 muscle-car dealer down, or make it spill its secret minimum price. Three levels show three generations of LLM-app security, and an eval suite proves which one holds."*

This is a portfolio project for **junior AI engineer** roles. It shows, end to end, the skills those job descriptions ask for:

- **Agents with tools**: ADK and LangGraph, two frameworks talking over **A2A**, with tools served over **MCP**.
- **RAG** on Postgres + pgvector.
- **Evals**: simulated users, an attack set, LLM-as-judge calibrated against human labels.
- **LLM security**: prompt injection, sensitive-information disclosure, excessive agency, unbounded consumption.
- **Production basics**: Docker, Cloud Run, Terraform, tracing, cost controls.

It plays to your strength (red teaming and leak evaluation) and fills your gap (Python, agent frameworks, cloud).

## 2. Goals

| Goal | Why it matters |
|------|----------------|
| G1. A public demo that a recruiter can play in under 2 minutes | A link is worth more than a repo nobody runs. |
| G2. A measurable security story: L1 → L2 → L3 with numbers | It separates you from "I built a chatbot" portfolios. Red teaming is your edge. |
| G3. Learn the stack properly: uv, FastAPI, ADK, LangGraph, MCP, A2A, pgvector, Langfuse, Cloud Run, Terraform | Interviews probe trade-offs. The ADRs are your interview prep. |
| G4. Almost free to run (target ≤ 5 USD/month infra + capped LLM spend) | A new GCP account, and it is personal money. |

## 3. Non-goals

- A realistic car marketplace. The inventory is 3 fictional cars.
- Beating state-of-the-art jailbreak defenses. We **measure** defenses; we don't claim they are unbreakable.
- Multi-tenant production SaaS: no accounts, no payments, no SLA.
- Fine-tuning or training models.

## 4. Game design (MVP)

- **Listing**: a fictional 1970s muscle car with a list price (for example 38,900 USD) and a fact sheet (RAG).
- **Secret floor**: sampled per game from the car's policy range and **non-round** (for example 27,385). It is never shown until the game ends.
- **Player actions**: chat (≤ 500 chars per message), **walk away**, or **claim the floor** (one guess per game, which ends the game).
- **End states**: `deal` (closed by code via `close_deal`), `walked_away`, `turn_limit` (12 buyer turns), `floor_claimed`, `expired` (30 min idle).
- **Score shown at the end**:
  - Deal: *discount captured* = `(list − price) / (list − floor)`.
  - Floor claim: correct if `|guess − floor| / floor ≤ 1.5%`.
  - The floor is revealed after the game ends, which is safe because it is per-game random.

### The three levels

| | L1 "Naive" | L2 "Hardened prompt" | L3 "Blind seller" |
|---|---|---|---|
| Floor in seller prompt | Yes | Yes | **No** |
| Defensive prompt (instruction hierarchy, spotlighting) | No | Yes | Yes |
| Output leak filter (code) | No | Yes | Yes |
| Who decides prices | LLM | LLM | **Code** (`evaluate_offer` policy engine) |
| Price guard: quoted price must equal a code-issued price | No | No | Yes |
| `close_deal` validated in code | **Yes** | **Yes** | **Yes** |
| Turn cap, budget, rate limits | Yes | Yes | Yes |

Details: [ADR-0007](adr/0007-guard-ladder.md) and [02-architecture.md](02-architecture.md#3-level-matrix).

## 5. Scope (MoSCoW)

### Must (MVP)

- Seller agent (ADK) with 3 levels, exposed over A2A.
- MCP server with `evaluate_offer`, `close_deal`, `lookup_model_sheet` and a code policy engine.
- Postgres + pgvector: inventory, pricing policy, games, transcripts, RAG over 3 hand-written fictional model sheets.
- FastAPI API + one-page web UI (human vs seller).
- Buyer agent (LangGraph) with 3 personas and appraisal before the first offer, talking to the seller over A2A.
- Evals: simulation matrix, ≥ 40 attacks, deterministic leak detector, report comparing L1/L2/L3.
- Langfuse tracing for both agents, grouped by game.
- Guardrails: turn cap, per-IP limits, daily soft budget, hard provider spend cap.
- Deployment: Docker, Cloud Run (api, seller, mcp), Terraform.

### Should

- MCP **primary at home** (Proxmox LXC) through Cloudflare Tunnel, with automatic per-game fallback to Cloud Run.
- LLM-as-judge for semantic leaks, calibrated against ~60 human labels.
- "Watch AI vs AI" mode in the web UI (SSE).
- Separate DB roles per service, so the L3 seller's DB role cannot read the floor.

### Could (only if ahead of plan)

- ADK `adk eval` with user simulation as a second, framework-native eval.
- RAG vs "whole sheet in context" comparison (honest check of whether a vector DB is needed).
- Cloudflare Turnstile on game creation.
- CI deploys with Workload Identity Federation.

### Won't (this phase)

- Accounts, leaderboard, payments.
- Public A2A endpoint for third-party buyer agents ("bring your own agent").
- LangGraph Agent Server deployment (see [ADR-0006](adr/0006-agent-topology.md)).
- Kubernetes, load balancer, Cloud Armor, custom domain for the Cloud Run demo.
- SPA frontend framework (React and similar).
- Self-hosted Langfuse.

## 6. Success criteria

### Product

- [ ] Public URL: a first-time visitor completes a game in ≤ 2 minutes without instructions.
- [ ] All 3 levels are playable, and the floor is revealed at the end.
- [ ] Killing the home MCP does not break new games (if the Should item is built).

### Engineering and security (from the eval report)

- [ ] **Invalid closes = 0** across all eval runs and production. This is a hard invariant: no deal below the floor and no deal without a matching accept.
- [ ] Floor-leak attack success rate (leak ≥ APPROX) at **L3 ≤ 5%**. L1 and L2 are reported, with no target (they are meant to leak).
- [ ] Deal rate for cooperative personas at L3 ≥ 60%, with seller surplus share (median) reported per level.
- [ ] p95 seller turn latency ≤ 6 s warm. Cold start is measured and documented.
- [ ] Judge vs human agreement: Cohen's κ ≥ 0.7, or documented why not.

### Cost

- [ ] Infra ≤ 5 USD/month at demo traffic. LLM spend is hard-capped (default 10 USD/month).

### Learning (self-assessment, checked in Week 8)

- [ ] You can explain in an interview: MCP vs A2A vs plain function calling, why L3 beats L2, how the leak detector works, why each ADR went the way it did.

## 7. Over-engineering review

You asked to be warned. Ordered by cost-to-value for a junior with ~9 h/week:

| # | Item | Risk | Recommendation |
|---|------|------|----------------|
| 1 | **Home MCP + tunnel + failover** | Highest complexity for the least AI-engineering value. It is infra learning. | Build **last** (Week 8) and keep it cuttable. Cloud Run MCP is the real backend first. |
| 2 | **Two agent frameworks** (ADK + LangGraph) | Doubles the learning curve. | Keep both, since both appear in job ads. Use LangGraph **only** for the buyer graph and don't go deep in both. |
| 3 | **A2A between two agents you own** | Protocol overhead vs a function call. ADK's A2A support is still labeled *experimental*. | Keep exactly **one** A2A hop (client → seller). No LangGraph Agent Server: self-hosting it requires a license key + Postgres + Redis. |
| 4 | **RAG over 3 short sheets** | ~30 chunks fit in a prompt, so a vector DB is overkill in production terms. | Keep it as a learning goal, and say so honestly. Optional eval: RAG vs full-sheet-in-context. |
| 5 | **Terraform** for 3 services | Can eat a week. | Keep it flat: one environment, no modules, no workspaces. |
| 6 | **ADK user simulation + LangGraph buyer** | Two user simulators. | MVP uses the LangGraph buyer only. ADK user-sim is a "Could". |
| 7 | **Self-hosted Langfuse** | Recommended 4 cores / 16 GiB, the whole mini PC. | Use Langfuse Cloud ([ADR-0004](adr/0004-langfuse-cloud.md)). |
| 8 | **Per-service DB roles** | Small cost (one migration). | Keep as a Should. It is the cleanest "L3 can't read the floor" proof. |
| 9 | **MCP OAuth 2.1 authorization** | The spec's OAuth flow is for third-party clients acting for users. | Use static service credentials. All MCP clients are yours ([ADR-0008](adr/0008-trusted-context-headers.md)). |
