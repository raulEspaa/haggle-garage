# 10 — Sources and Verification Log

All checks were made on **2026-10-08** against official docs, PyPI or vendor pricing pages, unless noted. These ecosystems change monthly. **Re-check this table at the start of Week 1 and before every dependency upgrade.**

Status: **V** = verified from an official source · **P** = partially verified (official source, but some detail was missing or truncated) · **U** = unverified (secondary source or assumption) · **S** = verify in the Week 2 spike.

## 1. Re-confirmation of the claims in the brief

| Claim | Status | Detail | Source |
|-------|--------|--------|--------|
| ADK exposes agents with `to_a2a()` | **V** | `from google.adk.a2a.utils.agent_to_a2a import to_a2a`. Params `agent, host, protocol, port, agent_card, runner, lifespan`. Card at `/.well-known/agent-card.json`. `pip install google-adk[a2a]`. Marked *experimental*. Supports a2a-sdk 0.3.x and 1.x (auto-detected). | [ADK A2A quickstart (exposing)](https://adk.dev/a2a/quickstart-exposing/) |
| ADK consumes remote agents with `RemoteA2aAgent` | **V** | `from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH`. Params `name, description, agent_card`, `use_legacy=False` for the new A2A extension, `config=A2aRemoteAgentConfig`. *Experimental*. | [ADK A2A quickstart (consuming)](https://adk.dev/a2a/quickstart-consuming/), [A2A extension](https://adk.dev/a2a/a2a-extension/) |
| LangGraph Agent Server has an A2A endpoint | **V** | `/a2a/{assistant_id}`, `langgraph-api >= 0.4.21` (≥ 0.13.0 recommended). A2A 1.0 JSON-RPC + 0.3 method names. State needs `messages`. `contextId` → `thread_id` (UUID). Card: `GET /.well-known/agent-card.json?assistant_id=…` | [A2A endpoint in Agent Server](https://docs.langchain.com/langsmith/server-a2a) |
| …and it is easy to self-host | **V (no)** | A standalone server needs `LANGGRAPH_CLOUD_LICENSE_KEY` + Postgres + Redis + egress to `beacon.langchain.com`. "Enterprise plan required" comes from secondary sources (**U**). | [Self-host standalone servers](https://docs.langchain.com/langsmith/deploy-standalone-server) |
| ADK includes user simulation for evals | **V** | Scenarios with `starting_prompt`, `conversation_plan`, optional `user_persona` (EXPERT/NOVICE/EVALUATOR). `user_simulator_config` (`model`, `max_allowed_invocations`, …). ADK Python ≥ 1.18.0. Use with metrics that don't need expected responses (`hallucinations_v1`, `safety_v1`, `per_turn_user_simulator_quality_v1`). | [ADK user simulation](https://adk.dev/evaluate/user-sim/), [ADK evaluate](https://adk.dev/evaluate/) |

## 2. Versions

| Item | Value | Status | Source |
|------|-------|--------|--------|
| google-adk | 2.11.0 (2026-10-02). Deps: `mcp >=1.24,<3`, `a2a-sdk >=0.3.4,<2`, `google-genai >=2.19,<3`. Python ≥ 3.10 | V | [PyPI google-adk](https://pypi.org/project/google-adk/) |
| a2a-sdk | 1.2.2 (2026-10-05). 1.0.0 released 2026-04-20. Implements spec 1.0 with 0.3 compat | V | [PyPI a2a-sdk](https://pypi.org/project/a2a-sdk/), [a2a-python](https://github.com/a2aproject/a2a-python) |
| a2a-sdk client API | `create_client(agent, client_config=ClientConfig(httpx_client=…, streaming=…))`, `ClientFactory`, `Client.send_message(request) -> AsyncIterator[StreamResponse]` | V | [a2a.client API](https://a2a-protocol.org/latest/sdk/python/api/a2a.client.html) |
| A2A spec | 1.0.0. Task states incl. `TASK_STATE_INPUT_REQUIRED`, `TASK_STATE_REJECTED`. Clients MAY send `contextId`; agents MAY accept it. Two breaking changes vs 0.3 (kind discriminator removed, extended card field moved) | P | [A2A specification](https://a2a-protocol.org/latest/specification/) |
| langgraph | 1.2.14 (2026-10-06) | V | [PyPI langgraph](https://pypi.org/project/langgraph/) |
| langchain-mcp-adapters | 0.3.2 (2026-08-06). `MultiServerMCPClient`, transports stdio/http/sse, headers | V | [PyPI langchain-mcp-adapters](https://pypi.org/project/langchain-mcp-adapters/) |
| mcp (Python SDK) | 2.3.0 (2026-10-02). 2.0.0 on 2026-07-28 renamed `FastMCP` → `MCPServer` (`from mcp.server import MCPServer`). New `Client`. Serves 2026-07-28 and 2025-11-25 clients | V | [PyPI mcp](https://pypi.org/project/mcp/), [What's new in v2](https://py.sdk.modelcontextprotocol.io/whats-new/), [python-sdk](https://github.com/modelcontextprotocol/python-sdk) |
| MCP spec | Current **2026-07-28**: stateless (no `initialize`), no `Mcp-Session-Id`, `server/discover`, roots/sampling/logging deprecated, `x-mcp-header`, OTel trace context in `_meta` | V | [Versioning](https://modelcontextprotocol.io/specification/versioning), [Changelog 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/changelog) |
| ty (Astral) | Beta, 0.0.x releases through 2026 | V | [astral-sh/ty](https://github.com/astral-sh/ty) |
| Terraform google provider | **8.6.0**, installed by `terraform init` with constraint `~> 8.0` (Week 1) | V | [terraform-provider-google releases](https://github.com/hashicorp/terraform-provider-google/releases) |
| Terraform CLI | 1.16.5 (HashiCorp checkpoint API, SHA256-verified download) | V | [Terraform install](https://developer.hashicorp.com/terraform/install) |
| Week 1 resolved versions | uv 0.12.23, SQLAlchemy 2.1.4, psycopg 3.3.6, pgvector-python 0.5.0, Pydantic 2.14.0, pydantic-settings 2.15.0, FastAPI 0.143.0, uvicorn 0.54.0, Alembic 1.20.0, mypy 2.4.0, ruff 0.16.10, pytest 9.1.1 | V | `uv.lock` |
| httpx2 | Replaces `httpx` for Starlette's `TestClient` (otherwise `StarletteDeprecationWarning`). Maintained by the Pydantic org. 2.13.1 | V | [httpx2](https://github.com/pydantic/httpx2) |
| Dependabot | Supports `package-ecosystem: uv` | V | [Dependabot options](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference) |
| gitleaks-action | v3.0.0. No license needed for personal accounts | V | [gitleaks-action](https://github.com/gitleaks/gitleaks-action) |
| Langfuse self-host major | v4 | P | [Langfuse self-hosting](https://langfuse.com/self-hosting) |

## 3. ADK APIs used by the design

| API | Status | Source |
|-----|--------|--------|
| `McpToolset` + `StreamableHTTPConnectionParams(url, headers, timeout, sse_read_timeout)`, `tool_filter`, `tool_name_prefix`, `require_confirmation` | V | [ADK MCP tools](https://adk.dev/tools-custom/mcp-tools/), [Advanced MCP config](https://adk.dev/tools-custom/mcp-tools/advanced/) |
| `McpToolset(header_provider=async fn(ReadonlyContext) -> dict)`, with access to `context.session.id` and `context.state` | V (behavior: **S3**) | [Advanced MCP config](https://adk.dev/tools-custom/mcp-tools/advanced/) |
| Callbacks: before/after agent, model, tool. Returning `LlmResponse` from `before_model_callback` skips the LLM. Returning a value from `before_tool_callback` skips the tool | V | [Types of callbacks](https://adk.dev/callbacks/types-of-callbacks/) |
| `DatabaseSessionService(db_url="postgresql+asyncpg://…")`, extra `google-adk[db]`, schema changed in 1.22.0 | V | [ADK sessions](https://adk.dev/sessions/session/) |
| `output_schema` together with tools on Gemini 3.x | P (official page + secondary sources). **S5** | [ADK LLM agents](https://adk.dev/agents/llm-agents/) |
| Per-session tool list (`tool_filter` predicate / custom `BaseToolset.get_tools(ctx)`) | U → **S4** | — |
| `contextId` → ADK session id mapping in `to_a2a` | U → **S2** | — |
| Backend switch `GOOGLE_GENAI_USE_VERTEXAI` | U (known from ADK docs, not re-fetched) | — |

## 4. Gemini models and prices (Gemini API, paid tier, standard, per 1M tokens)

| Model | Input / output | Notes | Status |
|-------|----------------|-------|--------|
| `gemini-3.8-flash` | 0.75 / 3.75 until 2026-12-31, then 1.50 / 7.50 | Latest stable Flash. Free tier available | V |
| `gemini-3.5-flash-lite` | 0.30 / 2.50 | Recommended Flash-Lite | V |
| `gemini-3.1-flash-lite` | 0.25 / 1.50 | Stable | V |
| `gemini-3.1-pro-preview` | 2.00 / 12.00 (≤ 200k) | No free tier | V |
| `gemini-2.5-*` | — | "Access limited" | V |
| `gemini-embedding-2` | 0.20 per 1M text tokens | Default 3072 dims, 128–3072 supported (768/1536/3072 recommended), auto-renormalized, task as an in-prompt instruction, 8192 max input tokens | V |
| Free tier data use | Free: content used to improve products. Paid: not used | — | V |
| Vertex / Agent Platform prices | Assumed equal to the Gemini API | Page truncated | U |

Sources: [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing), [Models](https://ai.google.dev/gemini-api/docs/models), [Embeddings](https://ai.google.dev/gemini-api/docs/embeddings).

## 5. Billing, caps and free tiers

| Fact | Status | Source |
|------|--------|--------|
| AI Studio **Project Spend Caps** (monthly, ~10 min enforcement lag, overages possible for long-running tasks). Tier caps: Tier 1 = 250 USD. Prepay min 5 USD | V | [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing), [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/more-control-over-gemini-api-costs/) |
| Tier 1 spend-based limit: 10 USD per rolling 10 minutes (429 beyond) | V | [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) |
| Free-tier rate limits are shown only in AI Studio (not on the page) | V | [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) |
| GCP Free Trial: 300 USD / 90 days. **Not usable for Gemini API in AI Studio**. Resources stop when it ends (30-day grace). No quota increases during the trial | V | [GCP free features](https://docs.cloud.google.com/free/docs/free-cloud-features), [Gemini API billing](https://ai.google.dev/gemini-api/docs/billing) |
| Always Free: Cloud Run 2M requests, 360k GiB-s, 180k vCPU-s, 1 GB egress (North America). Artifact Registry 0.5 GB. Secret Manager 6 versions + 10k accesses. GCS 5 GB (US regions only). Cloud Build 2,500 min | V | [GCP free features](https://docs.cloud.google.com/free/docs/free-cloud-features) |
| Cloud Run unit prices beyond the free tier | U (page truncated) | [Cloud Run pricing](https://cloud.google.com/run/pricing) |
| Vertex AI rebranded **Gemini Enterprise Agent Platform** (Cloud Next, April 2026). Endpoints unchanged | U (secondary sources) | [AIwire](https://www.hpcwire.com/aiwire/2026/04/23/google-unveils-gemini-enterprise-agent-platform/), [Wikipedia](https://en.wikipedia.org/wiki/Gemini_Enterprise_Agent_Platform) |
| Project-level spend caps for Gemini Enterprise (Aug 2026). Coverage of Agent Platform API calls unclear | P | [Google Cloud blog](https://cloud.google.com/blog/products/ai-machine-learning/flexible-billing-and-cost-controls-for-agents-on-google-cloud) |
| Neon Free: 1 GB/project, 100 CU-h/project/month, scale-to-zero after 5 min (not disableable), 10 branches, pgvector on all plans | V | [Neon pricing](https://neon.com/pricing) |
| Cloud SQL smallest instance ≈ 8–10 USD/month | U | — |

## 6. Observability

| Fact | Status | Source |
|------|--------|--------|
| Langfuse Hobby: 50k units/month, 30 days, 2 users, US/EU/JP, datasets + experiments + LLM-as-judge. Core 29 USD/month | V | [Langfuse pricing](https://langfuse.com/pricing) |
| Self-host components: web, worker, Postgres, ClickHouse, Redis/Valkey, S3. Compose: ≥ 4 cores / 16 GiB / 100 GiB, not for production | V | [Self-hosting](https://langfuse.com/self-hosting), [Docker Compose](https://langfuse.com/self-hosting/deployment/docker-compose) |
| ADK integration via `openinference-instrumentation-google-adk` (OTel) | V | [Langfuse × Google ADK](https://langfuse.com/integrations/frameworks/google-adk) |
| LangGraph via `from langfuse.langchain import CallbackHandler`. `langfuse_session_id` in metadata | V | [Langfuse × LangChain/LangGraph](https://langfuse.com/integrations/frameworks/langchain) |
| Unit accounting per trace/observation | U | — |

## 7. Networking

| Fact | Status | Source |
|------|--------|--------|
| Tailscale Funnel: **beta**. Ports 443/8443/10000 only. `*.ts.net` names. Non-configurable bandwidth limits. TLS terminated on the node (relays can't decrypt). All plans. Needs MagicDNS + HTTPS certs + `funnel` node attribute | V | [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) |
| Tailscale on Cloud Run: userspace networking, `--socks5-server=localhost:1055`, ephemeral auth key, `ALL_PROXY` | V | [Tailscale on Cloud Run](https://tailscale.com/kb/1108/cloudrun), [Userspace networking](https://tailscale.com/kb/1112/userspace-networking) |
| Cloudflare Tunnel: outbound-only connections from `cloudflared` | V | [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/) |
| Quick Tunnels: testing only, no uptime guarantee, **no SSE**, 200 in-flight requests, random hostname | V | [Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/) |
| Access service tokens: `CF-Access-Client-Id` / `CF-Access-Client-Secret`, policy action **Service Auth**, configurable expiry | V | [Service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/) |
| Zero Trust Free plan up to 50 users | P (Cloudflare marketing pages via search) | [Cloudflare Zero Trust pricing](https://www.cloudflare.com/plans/) |
| Named tunnels with public hostnames need a domain (zone) on Cloudflare | U (common knowledge, not explicitly read) | — |
| SSE through named tunnels | U → verify in Week 8 | — |

## 8. Other references

- OWASP Top 10 for LLM Applications 2025 (LLM01–LLM10), used for threat and attack mapping: <https://genai.owasp.org/llm-top-10/> (not re-fetched; check whether a newer edition exists).
- Faratin, Sierra & Jennings (1998), *Negotiation decision functions for autonomous agents*: the source of the Boulware concession tactic.
- uv workspaces (`[tool.uv.workspace]`, `{ workspace = true }`, `--package`, when not to use them) — **V**: <https://docs.astral.sh/uv/concepts/projects/workspaces/>
