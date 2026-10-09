# 09 — Repository Structure and Tooling

## 1. Layout (uv workspace, see [ADR-0001](adr/0001-monorepo-uv-workspace.md))

```text
haggle-garage/
├── README.md                      # pitch, demo link, GIF, results table, architecture, ADR links
├── pyproject.toml                 # workspace root: [tool.uv.workspace], dev tools, ruff/mypy/pytest config
├── uv.lock                        # ONE lockfile for every member
├── .python-version                # 3.13
├── Makefile                       # up, down, lint, types, test, seed, ingest, e2e, eval-smoke, eval-full
├── compose.yaml                   # db (pgvector), mcp, seller, api
├── .pre-commit-config.yaml        # ruff, ruff-format, gitleaks, basic hygiene hooks
├── .github/
│   ├── workflows/ci.yml           # PR + main: lint, types, tests, terraform fmt/validate, gitleaks
│   └── dependabot.yml             # uv, github-actions, docker
├── packages/
│   ├── core/                      # haggle-core: contracts (Pydantic), DB models, settings, policy engine (pure), a2a client wrapper
│   └── buyer/                     # haggle-buyer: LangGraph graph, personas/*.yaml, CLI (library used by api + evals)
├── services/
│   ├── api/                       # haggle-api: FastAPI, templates/, static/, Dockerfile
│   ├── seller/                    # haggle-seller: ADK agent, callbacks/, prompts/l1.md…l3.md, a2a_app.py, Dockerfile
│   └── mcp/                       # haggle-mcp: MCPServer tools, rag/, auth middleware, Dockerfile
├── evals/                         # haggle-evals: runner, detector, judge, report
│   └── datasets/                  # scenarios.yaml, attacks.yaml, leak_labels.jsonl, rag_questions.yaml, regressions.yaml
├── db/
│   ├── migrations/                # Alembic
│   ├── seed/                      # cars.yaml, policies.yaml (synthetic)
│   └── sheets/                    # fictional model sheets (Markdown)
├── infra/terraform/               # flat: main.tf, run.tf, iam.tf, secrets.tf, budget.tf, variables.tf, outputs.tf
├── deploy/home/                   # LXC notes, systemd units, cloudflared config template (no secrets)
└── docs/                          # these docs, results/ (eval reports, deploy checklist), journal.md
```

### Dependency rules

| Module | May import | Must not import |
|--------|-----------|-----------------|
| `haggle-core` | pydantic, SQLAlchemy, httpx, a2a-sdk (client) | ADK, LangGraph, the MCP server SDK |
| `haggle-buyer` | core, LangGraph, langchain-mcp-adapters | seller, mcp |
| `haggle-seller` | core, google-adk | mcp, buyer (it talks to the MCP over the protocol) |
| `haggle-mcp` | core, mcp SDK, pgvector | seller, buyer |
| `haggle-api` | core, buyer, FastAPI | seller, mcp (A2A only) |
| `haggle-evals` | everything (read side) | — |

The policy engine lives in `haggle_core.policy` as **pure functions** (no I/O). The MCP server uses it, and so do the evals (for the `FEE_policy` baseline). *(Optional)* enforce these rules with `import-linter` in CI.

## 2. Tooling choices

| Concern | Choice | Why | Rejected |
|---------|--------|-----|----------|
| Python | **3.13** | Mature wheels. ADK, LangGraph and MCP need ≥ 3.10 **[verified]**. | 3.14 (fresh, wheel gaps possible) |
| Packages, venvs, Python install | **uv** (workspaces, `uv.lock`, `uv run`, `uv sync --package`) | One fast tool replaces pip + venv + pip-tools + pyenv. Workspace = solution. | Poetry (slower, no workspaces), pip + requirements |
| Lint + format | **ruff** (`check` + `format`). Rules `E,F,I,B,UP,S,ASYNC,PT,SIM,RUF` | One tool. `S` = bandit security rules. `ASYNC` catches blocking calls inside `async def`. | flake8 + black + isort |
| Types | **mypy**: strict on `core`, policy, guards, detector; lenient elsewhere | Closest to the C# compiler safety net. | `ty` (Astral): still **beta, 0.0.x** **[verified]**. Revisit later. |
| Tests | **pytest**, pytest-asyncio, pytest-cov, **Hypothesis**, **httpx2** (needed by Starlette's `TestClient` since 2026), respx (HTTP mocks, check httpx2 compatibility when first needed), syrupy (snapshots) | Industry standard. Hypothesis = FsCheck. | unittest |
| Settings | **pydantic-settings** (env vars, `.env` for local only, gitignored) | Typed config ≈ `IOptions<T>`. | raw `os.environ` |
| Logging | stdlib `logging` + JSON formatter (or structlog) | Cloud Logging parses JSON from stdout. | print |
| Retries | **tenacity** | ≈ Polly. | hand-rolled loops |
| Pre-commit | ruff, ruff-format, **gitleaks**, check-yaml, end-of-file-fixer | Catches secrets before they leave the laptop. | — |
| Tasks | **Makefile** | Preinstalled on Linux. Discoverable. | just, invoke |
| Containers | Multi-stage Dockerfile: official uv image to build, `python:3.13-slim` runtime, non-root user, `uv sync --frozen --no-dev --package <svc>` | Small, reproducible, one per service. | One fat image |
| IaC | **Terraform** 1.16, `hashicorp/google` provider **8.6.0** **[verified W1]**, state in GCS | Your stated goal. Flat files, one env. | Pulumi, modules/workspaces (overkill) |
| CI | **GitHub Actions** (free for public repos) | Standard. | Cloud Build (fine, but deploys stay manual in MVP) |
| Dependency updates | **Dependabot** (uv, actions, docker, terraform) **[uv support verified W1]** | Free, simple. | Renovate (more powerful, more config) |

## 3. CI pipeline (`.github/workflows/ci.yml`)

On every PR and on `main`:

1. `uv sync --frozen` (fails if the lockfile is stale).
2. `ruff check` · `ruff format --check`.
3. `mypy` (strict packages).
4. `pytest -m "not llm"` with a **Postgres service container** (`pgvector/pgvector`, same major version as Neon). Alembic migrations run in the fixture.
5. Contract snapshot tests (MCP tool schemas, `SellerTurn`, DataPart, OpenAPI).
6. `terraform fmt -check` · `terraform validate` (no cloud credentials needed).
7. gitleaks.
8. *(main only, optional)* `docker build` for each service (no push).

**Not in CI:** anything that needs Gemini keys (evals). Third-party actions are pinned by commit SHA. No cloud credentials in GitHub for the MVP ([07 T24](07-threat-model.md#44-secrets-cloud-and-supply-chain)).

## 4. Testing strategy

| Level | Scope | Examples | Target |
|-------|-------|----------|--------|
| Unit | Pure logic, no network | Policy invariants (Hypothesis), leak detector fixtures, guards with scripted `LlmResponse` (no LLM), buyer guard, rate-limit math | ≥ 90% line coverage on policy/detector/guards |
| Integration | One service + real Postgres | Repositories, MCP tools through the SDK `Client`, api endpoints with the seller mocked (respx) | Key paths |
| Contract | Wire formats | JSON Schema snapshots: changing one fails CI until you approve it | All public schemas |
| E2E (local) | Compose stack + scripted A2A client | `make e2e`: a 5-turn game per level with the real LLM (dev key, manual) | Before deploys |
| Evals | Behavior with real LLMs | [06](06-evaluation-plan.md) | — |

**Trick worth learning:** in ADK, a `before_model_callback` that **returns an `LlmResponse` skips the model call** **[verified]**. Use it to script the model in tests and exercise every guard deterministically for free.

## 5. C# / Java → Python cheat sheet

| You know | Python equivalent here |
|----------|------------------------|
| `.sln` + `.csproj` / Maven multi-module | uv workspace + member `pyproject.toml` |
| `ProjectReference` | `[tool.uv.sources] haggle-core = { workspace = true }` |
| NuGet `packages.lock.json` | `uv.lock` |
| `dotnet format` + Roslyn analyzers | `ruff format` + `ruff check` |
| Nullable reference types / compiler | type hints + mypy (`Optional[X]`, written `X \| None`) |
| records, DataAnnotations | Pydantic v2 models (`BaseModel`, `Field(...)`) |
| ASP.NET Core minimal APIs + DI | FastAPI + `Depends(...)` |
| `IOptions<T>` / appsettings.json | pydantic-settings + env vars |
| EF Core + migrations | SQLAlchemy 2.0 (async) + Alembic |
| `Task` / `async`/`await` | `asyncio` coroutines. **No** blocking I/O inside `async def` (ruff `ASYNC` rules catch some cases). |
| `HttpClient` | `httpx.AsyncClient` (always set timeouts) |
| Polly | tenacity |
| xUnit / JUnit, `[Theory]` | pytest, `@pytest.mark.parametrize` |
| Moq / Mockito | `unittest.mock`, respx for HTTP |
| FsCheck / jqwik | Hypothesis |
| Serilog | logging + JSON formatter |
| `interface` | `typing.Protocol` (structural typing) |
| `enum` | `enum.StrEnum` (serializes cleanly in Pydantic) |

## 6. Version baseline (checked 2026-10-08, pinned via `uv.lock`)

| Package | Version seen | Notes |
|---------|-------------|-------|
| `google-adk` | 2.11.0 (2026-10-02) | Requires `mcp >=1.24,<3`, `a2a-sdk >=0.3.4,<2` (extra `[a2a]`), `google-genai >=2.19,<3`. A2A is experimental. |
| `a2a-sdk` | 1.2.2 (2026-10-05) | Spec 1.0 + 0.3 compat. Extras `[http-server]`, `[fastapi]`. |
| `mcp` | 2.3.0 (2026-10-02) | v2: `FastMCP` → `MCPServer`, spec 2026-07-28, serves 2025-11-25 clients too. |
| `langgraph` | 1.2.14 (2026-10-06) | — |
| `langchain-mcp-adapters` | 0.3.2 (2026-08-06) | `MultiServerMCPClient`, transport `http`/`streamable_http`, custom headers. |
| `langgraph-api` | ≥ 0.4.21 for A2A | Not used in the MVP (ADR-0006). |
| `langfuse` | current major **[unverified]** | ADK via `openinference-instrumentation-google-adk`. LangGraph via `langfuse.langchain.CallbackHandler`. |
| FastAPI, SQLAlchemy, Alembic, pgvector-python, mypy | 0.143.0, **2.1.4**, 1.20.0, 0.5.0, **2.4.0** (W1) | Pinned in `uv.lock`. |
| Terraform `hashicorp/google` | 8.6.0 (W1) | Pinned in `.terraform.lock.hcl`. |

## 7. Conventions

- **Network calls:** every one has a timeout. Retries only on idempotent operations or 5xx/429.
- **Money:** integers. **Time:** UTC. **IDs:** UUIDv4 strings.
- **Prompts:** files in `services/seller/prompts/` with a version header. `prompt_version` is stored per game.
- **Commits:** small PRs (< 400 lines). The PR template has "what / why / how I tested / what I learned".
- **Branching:** trunk-based (`main` + short-lived branches). Protect `main` with required CI.
- **Secrets:** never in `.env.example`, Dockerfiles, Terraform variables with defaults, or Terraform state.
