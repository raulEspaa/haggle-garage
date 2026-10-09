# 05 — Delivery Plan (8 weeks × ~9 h)

Budget: **~73 h planned** of the 64–80 h available. Planned hours stay below the maximum on purpose, because the unknowns are real (experimental A2A, MCP SDK v2, new Python habits).

**Rules of the road**

1. **Vertical slices.** Each week ends with something that runs, not "half of every layer".
2. **Deploy early.** A hello-world on Cloud Run in Week 1 removes cloud surprises from Week 7.
3. **Spike before you build** on experimental APIs (Week 2 tracer bullet).
4. **Three checkpoints** decide when to cut (§3). Cutting on schedule is a skill. Say so in the README.
5. Every bug found by an eval becomes a **regression case** (eval-driven development).

## 1. Week by week

### Week 1: Foundations and walking skeleton (~9 h)

| Task | h |
|------|---|
| GitHub repo, uv workspace skeleton, Python 3.13, ruff/mypy/pytest config, pre-commit (ruff, gitleaks) | 1.0 |
| GitHub Actions CI: lint, format check, types, tests on every PR | 1.0 |
| `compose.yaml` with `pgvector/pgvector`. SQLAlchemy models + Alembic initial migration (all tables in [03 §4](03-contracts.md#4-data-model)) | 2.0 |
| Seed script: 3 fictional cars + pricing policies | 1.0 |
| Accounts and guardrails: GCP project + **budget alerts 50/90/100%**. AI Studio `haggle-dev` (free) and `haggle-prod` (prepay 10 USD + spend cap). Langfuse Cloud EU. Neon project. Calendar reminder: trial ends at day 90. | 1.5 |
| Terraform bootstrap: GCS state bucket, Artifact Registry (cleanup policy), Cloud Run "hello" (`/healthz`) | 2.5 |

- **Deliverable:** green CI. `docker compose up db` + `alembic upgrade head` + seed works. A public `…run.app/healthz` created by `terraform apply`.
- **Done when:** a PR with a failing test is blocked by CI, `terraform destroy && terraform apply` recreates the service, and a test budget alert email has arrived.
- **You learn:** uv/pyproject (≈ .sln/.csproj), ruff, pytest (≈ xUnit), async SQLAlchemy (≈ EF Core), Alembic (≈ EF migrations), Terraform basics, Cloud Run.
- *If Terraform eats more than 3 h: deploy hello-world with `gcloud run deploy` and move Terraform to Week 7.*

### Week 2: Tracer bullet and policy engine (~9 h)

| Task | h |
|------|---|
| **Spike S1–S3, S6** ([02 §11](02-architecture.md#11-spikes-de-risk-before-building-on-them)): dummy MCP tool (SDK v2) ← ADK agent with `McpToolset(header_provider)` ← `to_a2a(runner=DatabaseSessionService)` ← a2a-sdk client, 2 messages with the same `contextId`. Write findings into ADR-0001/0006/0008. | 2.5 |
| Policy engine as pure functions (Boulware target, decide, rounding) + unit tests + **Hypothesis** property tests for invariants I1–I5 | 2.0 |
| MCP server: `evaluate_offer`, `close_deal` (events, deals, idempotency, generic reasons), scoped token middleware, `/healthz` | 2.5 |
| Contract tests: snapshot of `tools/list` schemas. Tool calls through the SDK `Client` in-process | 1.0 |
| Write model sheets #1 and #2 (background task) | 1.0 |

- **Deliverable:** the integration path ADK ↔ MCP ↔ A2A is proven (or fallbacks chosen and recorded). The MCP server has 2 real tools.
- **Done when:** property tests pass 1,000 examples per invariant, `close_deal` below the floor returns `not_accepted`, and MCP Inspector can call both tools with a valid token and gets 401 without one.
- **You learn:** MCP (2026-07-28 stateless model), A2A basics, ADK wiring, property-based testing (≈ FsCheck).

### Week 3: Seller agent and RAG (~9.5 h)

| Task | h |
|------|---|
| Sheet #3. Ingestion: chunk by section, embed with `gemini-embedding-2` (768 dims), store in pgvector with an HNSW index | 1.0 |
| `lookup_model_sheet` + 10 smoke retrieval questions | 1.0 |
| Seller `LlmAgent`: instruction provider per level, `SellerTurn` output schema, toolset per level, prompts L1/L2/L3 v1 as versioned files | 2.0 |
| Callbacks: `before_agent` (load context, atomic turn reservation), `before_model` (budget), `before_tool` (offer-in-message, L1–L2 close evidence), `after_tool` (record code-issued numbers), `after_model` (price guard, leak filter, canary). Write turns and `llm_usage`. | 2.5 |
| Callback unit tests with scripted `LlmResponse` (no real LLM) | 1.0 |
| Langfuse via OpenInference ADK instrumentor. Session = `game_id` | 1.0 |
| Manual play in `adk web` at each level. Note every leak you get: these seed the attack set | 1.0 |

- **Deliverable:** a seller that plays all 3 levels over A2A with traces.
- **Done when:** a scripted A2A client completes a 5-turn game per level, 10 manual price-manipulation attempts at L3 never produce a non-code price, and the traces are grouped per game.
- **You learn:** ADK agents/tools/callbacks/sessions, structured output, embeddings, pgvector, OpenTelemetry.

### Week 4: API and web UI (~9 h). Checkpoint A: playable locally

| Task | h |
|------|---|
| FastAPI endpoints ([03 §3](03-contracts.md#3-rest-api-api-service)): cars, levels, games (sample non-round floor, templated greeting), messages (single-flight, input hygiene), floor-guess, end. Problem Details errors. | 2.5 |
| A2A client wrapper: timeouts, retry on 5xx only (tenacity), ID-token hook for the cloud | 1.5 |
| Guards: salted IP hash, per-IP and global limits (Postgres counts), daily soft budget, game expiry | 1.5 |
| One-page UI: Jinja2 + vanilla JS, `textContent` only, strict CSP, end-of-game reveal | 2.0 |
| Compose all services. Integration tests (seller mocked with respx). 3 manual end-to-end games | 1.5 |

- **Deliverable:** the full game in the browser via `docker compose up`.
- **Done when:** a game completes at all 3 levels locally, tests cover the rate limit, single-flight and token checks, and `grep innerHTML` finds nothing in the UI code.
- **You learn:** FastAPI + `Depends` (≈ ASP.NET Core DI), Pydantic v2 (≈ records + DataAnnotations), httpx async, CSP basics.

### Week 5: Buyer agent with LangGraph (~9 h)

| Task | h |
|------|---|
| Persona YAMLs: stingy, hurried, manipulator (tactics linked to attack categories) | 1.0 |
| `StateGraph`: fetch_listing → appraise (MCP `catalog` scope via langchain-mcp-adapters) → plan_move (`BuyerMove`) → **guard** (code: never above walk-away, offers non-decreasing) → send (A2A) → observe (DataPart) → route → report (floor estimate) | 3.0 |
| CLI: create a game through the api, run, print the transcript and outcome | 1.0 |
| Tests: guard unit tests, graph test with a fake chat model and a mocked seller | 1.5 |
| Langfuse `CallbackHandler`, `langfuse_session_id = game_id` | 1.0 |
| *(Should)* `POST /api/matches` SSE + "watch AI vs AI" in the UI | 1.5 |

- **Deliverable:** `uv run haggle-buyer --car kestrel-440-1970 --level 2 --persona manipulator`.
- **Done when:** 9 runs (3 personas × 3 levels) finish without errors, buyer and seller traces share a session, and the guard tests pass.
- **You learn:** LangGraph state, reducers, conditional edges; structured output; one MCP server consumed from a second framework.

### Week 6: Evals (~10 h). Checkpoint B: measurable

| Task | h |
|------|---|
| Deterministic leak detector + labeled fixtures (digits, spelled out en/es, reversed, base64, percentages) | 2.0 |
| Calibration set (~60 labeled utterances, labeled by you) + LLM judge (`gemini-3.8-flash`, JSON schema) + agreement report (accuracy, Cohen's κ) | 1.5 |
| Attack dataset v1: ≥ 40 attacks, ≥ 10 categories, OWASP LLM mapping. Scripted attacker runner. | 2.0 |
| Simulation matrix runner: 3 cars × 3 levels × 3 personas × 3 seeds = 81 games, concurrency limit, cost tracking | 2.0 |
| Metrics with Wilson 95% CIs, Markdown report, scores to Langfuse | 1.5 |
| First full run. Triage the top 3 failures into regression cases. Prompt v2 for L2. | 1.0 |

- **Deliverable:** `docs/results/eval-report-<date>.md` comparing L1/L2/L3.
- **Done when:** one command runs the suite, `invalid_closes == 0` is asserted, the judge κ is reported, and the cost of the run is recorded.
- **You learn:** eval design, red-team datasets, judge calibration, statistics on small samples.

### Week 7: Cloud deployment and public guardrails (~9 h). Checkpoint C: public

| Task | h |
|------|---|
| Dockerfiles: multi-stage, uv, non-root, slim base. Check image sizes. | 1.5 |
| Terraform: service accounts (api/seller/mcp), 3 Cloud Run services (api public; seller and mcp IAM-only; max instances; startup CPU boost), `run.invoker` bindings, Secret Manager + accessor bindings, budget | 3.0 |
| Neon: roles and grants ([03 §5.3](03-contracts.md#53-roles-and-grants)), migrations, connection strings to Secret Manager | 1.0 |
| AI Studio prod: spend cap and prepay confirmed. Key restricted. Model ids via env. | 1.0 |
| Verify in prod: seller and mcp return 403 without auth, rate limit, budget gate, CSP. Small burst test (30 concurrent requests). Record evidence in `docs/results/deploy-checklist.md`. | 1.5 |
| `/about` page: how it works + privacy note | 1.0 |

- **Deliverable:** the public URL.
- **Done when:** a stranger can play, `terraform plan` shows no drift, and every guardrail has written evidence.
- **You learn:** Cloud Run IAM service-to-service auth (ID tokens), Secret Manager, Terraform state/resources, container hardening.

### Week 8: Home MCP, failover and portfolio (~9 h)

| Task | h |
|------|---|
| Unprivileged LXC (1 vCPU, 1 GB): MCP under systemd + `cloudflared` service. Proxmox firewall egress allow-list. Access app + Service Auth policy + token. | 2.0 |
| `McpBackendSelector` (sticky per game, switch on failure). Record `mcp_backend`. Chaos test. | 1.5 |
| Full eval run against prod. Update the report. | 1.5 |
| README (pitch, GIF, architecture, results table, threat model summary, ADR links), 2-min video, LinkedIn/blog draft | 3.0 |
| Retrospective. ADRs to Accepted/Superseded. "Next steps" list. | 1.0 |

- **Deliverable:** the portfolio-ready repo + demo.
- **Done when:** stopping the home MCP leaves new games working through Cloud Run, the README reads in 5 minutes, and the final report is linked.
- **You learn:** LXC hardening, Cloudflare Zero Trust, resilience patterns, technical storytelling.

## 2. Hours summary

| W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | Total |
|----|----|----|----|----|----|----|----|-------|
| 9 | 9 | 9.5 | 9 | 9 | 10 | 9 | 9 | **73.5** |

## 3. Checkpoints and cut list

| Checkpoint | End of | Test | If it fails |
|------------|--------|------|-------------|
| **A. Playable** | W4 | A full game in the browser locally | Cut items 2, 3 and 5 now. Move AI-vs-AI out. |
| **B. Measurable** | W6 | An eval report exists | Matrix to 1 car × 3 levels × 2 personas. Skip the judge (item 3). |
| **C. Public** | W7 | Public URL with guardrails verified | Spend W8 on deploy. Cut item 1 (home MCP). |

**Cut list (in this order; the first cuts save the most for the least value lost):**

| # | Cut | Saves | What remains |
|---|-----|-------|--------------|
| 1 | Home MCP + tunnel + failover | ~4 h | Cloud Run MCP only. ADR-0002 stays as "designed, not built". |
| 2 | AI-vs-AI mode in the web UI | ~1.5 h | CLI and evals only. |
| 3 | LLM judge | ~1.5 h | Deterministic detector + floor-extraction error. |
| 4 | Buyer appraisal through MCP | ~1 h | Appraisal from the public listing via the api. |
| 5 | Third persona ("hurried") | ~1 h | Stingy + manipulator. |
| 6 | Terraform for secrets and IAM | ~2 h | Terraform for AR + Cloud Run. Secrets by hand, documented. |
| 7 | `DatabaseSessionService` | ~1 h | In-memory sessions + seller `max-instances=1`. The transcript is still in our DB. |
| 8 | Per-service DB roles | ~1 h | One app role. L3 "can't read the floor" holds for the prompt only. Documented. |

**Never cut:** code-validated closing, turn cap + budget + rate limits, the L1-vs-L2-vs-L3 eval report, the deterministic leak detector, a README with results.

## 4. Weekly ritual (15 min, Sunday)

1. Tick the "Done when" boxes honestly.
2. Log actual hours vs plan in `docs/journal.md`.
3. Decide on the next checkpoint's cut early. Don't wait for the deadline.
4. Write 3 bullet points: "what I learned / what surprised me / what I'd do differently". This becomes the blog post.
