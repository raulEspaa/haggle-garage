# 05 — Delivery: plan vs outcome, costs, tooling and sources

The project was planned as **8 weeks × ~9 h** (73.5 h, kept under the 64–80 h available because
the unknowns were real: experimental A2A, MCP SDK v2, new Python habits). This document records
what was planned, what shipped, what was cut, what it cost, and the tooling and sources behind it.
It replaces the Phase 1 delivery plan, risk and cost estimate, tooling plan and verification log.

**Rules of the road (kept all eight weeks):**

1. **Vertical slices.** Each week ends with something that runs, not half of every layer.
2. **Deploy early.** A hello-world on Cloud Run in week 1 removed cloud surprises from week 7.
3. **Spike before you build** on experimental APIs (the week 2 tracer bullet).
4. **Checkpoints decide the cuts** (§2), and the README says what was cut.
5. Every bug an eval finds becomes a **regression case** (`evals/datasets/regressions.yaml`).

## 1. Plan vs shipped, week by week

Each week's journal in [`learning/`](learning/README.md) holds its Definition of Done with evidence.

| Week | Goal | Done when… | Outcome |
|------|------|------------|---------|
| 1 | Foundations and walking skeleton | CI blocks a failing PR; `alembic upgrade head` + seed work; Terraform deploys a public `/health`; budget alerts exist | ✅ uv workspace, CI, Postgres + pgvector, Terraform state in GCS, Cloud Run hello-world ([journal](learning/week-01-foundations.md)) |
| 2 | Tracer bullet and policy engine | ADK ↔ MCP ↔ A2A proven; property tests pass 1,000 examples per invariant; `close_deal` below the floor is refused; MCP tools answer 401 without a token | ✅ spikes S1–S4, S6; Hypothesis found a counter equal to the floor ([journal](learning/week-02-tracer-bullet-and-policy.md)) |
| 3 | Seller agent and RAG | Each level playable over A2A; L3 never quotes a non-code price; traces grouped per game | ✅ ADK seller with guards as callbacks, pgvector RAG, Langfuse ([journal](learning/week-03-seller-agent-and-rag.md)) |
| 4 | API and web UI. **Checkpoint A: playable** | A game completes at all 3 levels in the browser; tests cover limits, single-flight, tokens; no `innerHTML` | ✅ FastAPI + server-rendered page with a strict CSP ([journal](learning/week-04-api-and-web-ui.md)) |
| 5 | Buyer agent with LangGraph | 9 runs (3 personas × 3 levels) without errors; buyer and seller traces share a session; guard tests pass | ✅ one trace per game across buyer → seller → MCP ([journal](learning/week-05-buyer-agent-langgraph.md)) |
| 6 | Evals. **Checkpoint B: measurable** | One command runs the suite; `invalid_closes == 0` asserted; judge κ reported; run cost recorded | ✅ 81 games + 264 attack runs for $1.86; κ = 0.84 ([journal](learning/week-06-evals.md), [results](results/README.md)) |
| 7 | Cloud deployment. **Checkpoint C: public** | A stranger can play; `terraform plan` shows no drift; every guardrail has written evidence | ✅ [public URL](https://haggle-api-38346102533.europe-west1.run.app), [deploy checklist](results/deploy-checklist.md) ([journal](learning/week-07-cloud-deploy.md)) |
| 8 | Portfolio | Final eval report linked; README reads in 5 minutes; ADRs closed; next steps listed | ✅ ([retrospective](learning/week-08-retrospective.md)) |

Hours were not logged week by week, so there is no honest planned-vs-actual hours table. Every
week finished within its slot except week 8, which was re-scoped (§2).

## 2. Cuts and changes

| Change | When | Why | What remains |
|--------|------|-----|--------------|
| **Home MCP + Cloudflare Tunnel + failover** (planned for week 8) — cut | Week 8 | Cut list item #1: the most work for the least value once the cloud MCP was proven in production. It also needed a domain and a 24/7 home server | [ADR-0002](adr/0002-home-mcp-ingress.md) is **Deferred**: designed, not built. The Cloud Run MCP is the only backend |
| **"Watch AI vs AI" in the web UI** (`POST /api/matches`, a *Should*) — cut | Weeks 5–8 | Cut list item #2. The buyer runs from the CLI (`make buyer`) and in the evals, which is where it earns its keep | The endpoint stays in [03-contracts](03-contracts.md) as a design |
| **Gemini API (AI Studio) → Gemini on Vertex AI** | Week 5 | The free tier was too slow for the eval matrix, and the 300 USD trial credit can't pay for AI Studio | [ADR-0013](adr/0013-gemini-on-vertex-ai.md). No hard spend cap, so the demo has its own limits |
| Public demo limits: $1/day soft budget → **$2/day**; prepaid cap → **budget alert + our own gates** | Week 7 | Vertex AI has no prepaid cap; the limits moved into the api and the seller | [deploy checklist §3](results/deploy-checklist.md#3-abuse-limits) |
| Fictional brand → **real iconic cars** | Week 2 | More fun to play, facts are sourceable | [ADR-0011](adr/0011-real-iconic-cars.md) (supersedes 0010) |
| Buyer MCP client: `langchain-mcp-adapters` → **MCP SDK client** | Week 5 | The adapter requires `mcp<2` | [ADR-0012](adr/0012-buyer-mcp-sdk-client.md) |

Nothing on the **never cut** list was cut: code-validated closing, turn cap + budget + rate
limits, the L1-vs-L2-vs-L3 eval report, the deterministic leak detector, a README with results.

## 3. Costs: estimated vs measured

| Item | Phase 1 estimate | Measured |
|------|------------------|----------|
| Full eval run (81 games + attacks) | ≈ 5 USD | **1.86 USD** (264 attack runs) |
| Simulated game (seller + buyer + judge) | ≈ 0.04 USD | **0.013–0.032 USD** median (L1–L3; L3 is the most expensive) |
| All eval runs over the project | ~25 USD | **≈ 5 USD** (smoke, full, L2 iterations, regressions, final) |
| Public demo LLM spend | ≤ 10 USD/month (prepaid cap) | capped by our gates at **2 USD/day**, plus a 10 EUR/month alert |
| Cloud Run, Artifact Registry, Secret Manager | ≈ 1–2 USD/month | within free tiers and the trial credit |
| Neon, Langfuse | 0 (free tiers) | 0 |
| Domain, AI Studio prepay | ≈ 20 USD | **0**: not needed after the cuts and the move to Vertex AI |
| **Out of pocket** | ≈ 35–45 USD | **0 USD** so far: everything ran on the 300 USD GCP trial credit |

Token prices are in [`haggle_core/llm_costs.py`](../packages/core/src/haggle_core/llm_costs.py);
eval costs are estimated from token counts, and the GCP billing report is the ground truth.

**Calendar:** the trial credit ends around **early January 2027**. Upgrade the billing account
before then or every resource stops. `gemini-3.8-flash` (the judge) doubles its price on
2027-01-01.

## 4. Risks: what actually happened

| Risk (Phase 1) | What happened |
|----------------|---------------|
| Fast-moving, experimental APIs (ADK A2A, MCP SDK v2, A2A 1.0) | **Materialised, contained.** ADK pinned OpenTelemetry below FastAPI's needs; a2a-sdk's auto-instrumentation broke ADK; ADK switched to a different structured-output path on Vertex and looped on a tool. The tracer bullet and exact pins kept each one a one-day fix |
| `mcp` version conflict inside one lockfile | Did not happen: ADK accepts `mcp<3`. `langchain-mcp-adapters` did conflict (ADR-0012) |
| AI-generated code you don't understand | Mitigated by the weekly journals: every week explains its code, with exercises |
| Game balance | L3 deal rate 78 %, seller surplus 56 %: harder but playable |
| Noisy eval results | Handled with 3 seeds, Wilson CIs and paired comparisons; claims are worded to match the sample size |
| GCP trial ends at day 90 | Open: see the calendar note above |
| Model deprecation / price changes | Model ids are config; the judge's price change is on the calendar |
| Cold starts | Measured: a negotiation turn takes 4.9–8.9 s end to end; cold starts add a few seconds |
| Langfuse / Neon free limits | Not reached |
| Home outage | Moot: home MCP cut |
| **Unplanned:** the eval budget gate | A full run hit the local seller's daily budget and scored "closed for today" as 0 % attack success. Now the suite checks the budget before starting and flags runs with > 5 % errors |
| **Unplanned:** cloud-only failures | 403 from ID-token audiences, `http://` asset links behind TLS, traces lost to CPU throttling. All found by testing from outside ([week 7](learning/week-07-cloud-deploy.md#6-what-broke-on-the-way-and-how-it-was-found)) |

## 5. Repository and tooling

Layout ([ADR-0001](adr/0001-monorepo-uv-workspace.md)): one uv workspace, one lockfile, one
Dockerfile per service. The [README](../README.md#repository-map) has the map.

**Dependency rules:**

| Module | May import | Must not import |
|--------|-----------|-----------------|
| `haggle-core` | pydantic, SQLAlchemy, httpx, a2a-sdk (client) | ADK, LangGraph, the MCP server SDK |
| `haggle-buyer` | core, LangGraph, langchain-google-genai, MCP SDK client | seller, mcp |
| `haggle-seller` | core, google-adk | mcp, buyer (it talks to the MCP server over the protocol) |
| `haggle-mcp` | core, mcp SDK, pgvector | seller, buyer |
| `haggle-api` | core, FastAPI, a2a-sdk | seller, mcp (A2A only) |
| `haggle-evals` | everything (read side) | — |

The policy engine lives in `haggle_core.policy` as **pure functions**: the MCP server uses it, and
so do the evals.

| Concern | Choice | Rejected |
|---------|--------|----------|
| Python | **3.13** | 3.14 (fresh, wheel gaps) |
| Packages, venvs, Python install | **uv** workspaces | Poetry, pip + requirements |
| Lint + format | **ruff** (`E,F,I,B,UP,S,ASYNC,PT,SIM,RUF`) | flake8 + black + isort |
| Types | **mypy** strict | `ty` (still beta) |
| Tests | **pytest**, pytest-asyncio, **Hypothesis**, httpx2, respx | unittest |
| Settings | **pydantic-settings** | raw `os.environ` |
| Retries | **tenacity** | hand-rolled loops |
| Pre-commit | ruff, **gitleaks**, large-file and hygiene hooks | — |
| Containers | multi-stage, uv image to build, `python:3.13-slim` runtime, non-root | one fat image |
| IaC | **Terraform** 1.16, `hashicorp/google` 8.x, state in GCS | Pulumi, modules (overkill) |
| CI | **GitHub Actions**: lint, format, types, tests against a real Postgres service, `terraform validate`, gitleaks | Cloud Build |

**Testing strategy:** unit tests for pure logic (policy invariants with Hypothesis, leak detector
fixtures, guards with scripted `LlmResponse`, so no LLM); integration tests with a real Postgres;
contract snapshots of the MCP tool schemas; evals with real LLMs outside CI. In ADK, a
`before_model_callback` that returns an `LlmResponse` **skips the model call**: that is how every
guard is tested deterministically, for free.

**Conventions:** every network call has a timeout; retries only on idempotent calls or 5xx/429.
Money in whole dollars (integers), time in UTC. Prompts are versioned files and
`prompt_version` is stored per game. Secrets never go in `.env.example`, Dockerfiles, Terraform
variables or Terraform state.

## 6. C# / Java → Python cheat sheet

| You know | Python equivalent here |
|----------|------------------------|
| `.sln` + `.csproj` / Maven multi-module | uv workspace + member `pyproject.toml` |
| `ProjectReference` | `[tool.uv.sources] haggle-core = { workspace = true }` |
| NuGet `packages.lock.json` | `uv.lock` |
| `dotnet format` + Roslyn analyzers | `ruff format` + `ruff check` |
| Nullable reference types / compiler | type hints + mypy (`X \| None`) |
| records, DataAnnotations | Pydantic v2 models (`BaseModel`, `Field(...)`) |
| ASP.NET Core minimal APIs + DI | FastAPI + `Depends(...)` |
| `IOptions<T>` / appsettings.json | pydantic-settings + env vars |
| EF Core + migrations | SQLAlchemy 2 (async) + Alembic |
| `Task` / `async`/`await` | `asyncio` coroutines. **No** blocking I/O inside `async def` |
| `HttpClient` | `httpx.AsyncClient` (always set timeouts) |
| Polly | tenacity |
| xUnit / JUnit, `[Theory]` | pytest, `@pytest.mark.parametrize` |
| Moq / Mockito | `unittest.mock`, respx for HTTP |
| FsCheck / jqwik | Hypothesis |
| `interface` | `typing.Protocol` (structural typing) |
| `enum` | `enum.StrEnum` |
| `DefaultAzureCredential` + managed identity | Application Default Credentials + a Cloud Run service account |

## 7. Key versions and verified facts

Pinned in `uv.lock` and `.terraform.lock.hcl`. These ecosystems change monthly: re-check before
upgrading.

| Package | Version | Note |
|---------|---------|------|
| `google-adk` | 2.11.0 | A2A support is *experimental*. Pins `opentelemetry-api <= 1.42.1`, which caps FastAPI at 0.141.x |
| `a2a-sdk` | 1.2.2 | Spec 1.0, protobuf models. Its OpenTelemetry auto-instrumentation is disabled in each package |
| `mcp` | 2.3.0 | v2 renamed `FastMCP` → `MCPServer`; spec 2026-07-28 (stateless) |
| `langgraph` | 1.2.14 | with `langchain-google-genai` 4.4.0 |
| `langfuse` | 4.15.6 | ADK via `openinference-instrumentation-google-adk`; LangGraph via `CallbackHandler` |
| SQLAlchemy / Alembic / pgvector | 2.1.4 `[asyncio]` / 1.20.0 / 0.5.0 | SQLAlchemy 2.1 no longer installs `greenlet` by default |
| Terraform / `hashicorp/google` | 1.16.5 / 8.6.0 | |

Facts that were only learned by running the code:

| Fact | Where it mattered |
|------|-------------------|
| With tools + `output_schema`, ADK uses a native path on Vertex AI and a `set_model_response` tool on the Gemini API; the native path looped on Flash-Lite | `SellerGemini` keeps the tool path everywhere ([ADR-0013](adr/0013-gemini-on-vertex-ai.md)) |
| If an `McpToolset` fails to load, ADK logs an error and runs **without** those tools | L3 fails closed when its pricing tool is missing |
| `gemini-embedding-2`: a list of strings in one `embed_content` call is **one** content → one vector | Embed one document per call |
| `gemini-embedding-2` on Vertex works on `global`/`us`, 404 on `europe-west1` | `GOOGLE_CLOUD_LOCATION=global` |
| The 300 USD trial credit can't pay for the Gemini API in AI Studio, but does pay for Gemini on Vertex | ADR-0013 |
| Langfuse `GET /api/public/traces` returns 410 for new orgs; use `/api/public/v2/observations` | Trace checks in the evals |
| Cloud Run ID tokens must carry the service URL or a **custom audience** | `custom_audiences` in Terraform |

Main sources: [ADK docs](https://adk.dev/) (A2A, MCP tools, callbacks, sessions) ·
[A2A specification](https://a2a-protocol.org/latest/specification/) ·
[MCP specification](https://modelcontextprotocol.io/specification/versioning) and
[Python SDK v2](https://py.sdk.modelcontextprotocol.io/whats-new/) ·
[LangGraph](https://docs.langchain.com/) ·
[Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) ·
[GCP free trial](https://docs.cloud.google.com/free/docs/free-cloud-features) ·
[Cloud Run service-to-service auth](https://cloud.google.com/run/docs/authenticating/service-to-service) ·
[Neon pricing](https://neon.com/pricing) · [Langfuse](https://langfuse.com/docs) ·
[OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/) ·
Faratin, Sierra & Jennings (1998), *Negotiation decision functions for autonomous agents* (the
Boulware concession tactic).

## 8. Future work

1. **Home MCP with failover** ([ADR-0002](adr/0002-home-mcp-ingress.md)): an LXC behind a
   Cloudflare Tunnel, a sticky-per-game backend selector and a chaos test.
2. **"Watch AI vs AI"** in the web UI, streaming a buyer-agent game over SSE.
3. **Bring your own buyer agent:** a public A2A endpoint with its own limits.
4. **CI-driven deploys** with Workload Identity Federation (deploys are manual today).
5. **Human-reviewed judge labels** (`make eval-label`): the calibration labels are still drafts.
6. **More seller models as a variable** in the eval matrix (e.g. `gemini-3.5-flash-lite`).
7. **Transcript retention job:** delete games older than 30 days, as the `/about` privacy note
   promises. Today it's a manual delete; the first public games turn 30 days old on 2026-11-10.
