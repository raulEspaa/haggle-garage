# Deploy checklist: first public release (2026-10-11)

**Public URL:** https://haggle-api-38346102533.europe-west1.run.app · images tagged with the
deployed commit (`/health` reports it) · region `europe-west1` · database Neon (Postgres 17,
`eu-central-1`) · Gemini on Vertex AI.

Every guardrail below was checked **from outside**, against production, with the command's
result recorded. Re-run after every deploy that touches auth, limits or headers.

## 1. Only the api is public

| Check | Command (abridged) | Result |
|-------|--------------------|--------|
| Invokers | `gcloud run services get-iam-policy <service>` | api: `allUsers` · seller: only `haggle-api` SA · mcp: only `haggle-seller` SA |
| Seller, no token | `curl $SELLER/.well-known/agent-card.json` | **403** |
| Seller A2A, no token | `curl -X POST $SELLER/` | **403** |
| MCP, no token | `curl -X POST $MCP/mcp` (tools/list) | **403** |
| MCP, forged bearer | `Authorization: Bearer eyJ…e30.x` | **401** (Cloud Run rejects the token) |
| MCP, valid Google identity but no app token | `Authorization: Bearer $(gcloud auth print-identity-token)` | **401** from our `TokenAuthMiddleware`: IAM passed, the second layer still refuses |
| Seller with a valid token for the service | same, owner identity | 200 (the service itself is healthy) |

Two independent layers on the MCP server: Google IAM (who may reach the service) and the
application token (which scope: `seller` or `catalog`).

## 2. Least-privilege database roles

Created by `haggle-provision-roles` (passwords piped into Secret Manager, never displayed).
Tested locally with the three services running under their own roles (three levels played to a
deal, floor claim and walk-away; 0 permission errors) and in `packages/core/tests/test_provision.py`:

| Role | Must fail | Result |
|------|-----------|--------|
| `haggle_seller` | `SELECT floor_usd FROM games` | `InsufficientPrivilege` |
| `haggle_seller` | `SELECT * FROM deals` / `negotiation_events` | `InsufficientPrivilege` |
| `haggle_seller` | `seller_game_context` at level 3 | allowed, `floor_usd = NULL` |
| `haggle_api` | `INSERT INTO deals` | `InsufficientPrivilege` |
| `haggle_mcp` | `DELETE FROM games`, `UPDATE games SET floor_usd` | `InsufficientPrivilege` |

## 3. Abuse limits

| Check | Result |
|-------|--------|
| 5 games per IP per day | 6th game → **429** `Too many games`, `Retry-After: 3600` |
| Spoofed `X-Forwarded-For` (a different fake IP per request) | still **429**: the api trusts only the hop appended by Google's front end (`TRUSTED_PROXY_HOPS=1`) |
| Daily game budget | `HAGGLE_API_DAILY_BUDGET_USD=2.00` (api, refuses new games and messages) and `HAGGLE_SELLER_DAILY_BUDGET_USD=2.00` (seller, refuses turns), read from the live service config. The 503 path is covered by `test_spent_budget_closes_the_demo`; not triggered live (it would mean spending $2). |
| Max instances | 2 per service (`autoscaling.knative.dev/maxScale`) |
| GCP budget alert | 10 EUR/month, e-mails at 50 / 90 / 100 % (alert only, not a cap) |

## 4. Browser security

| Header on `/` | Value |
|---------------|-------|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'` |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `no-referrer` |

HTTPS is enforced by Cloud Run, and every `*.app` domain is on browsers' HSTS preload list.

The CSP proved itself on the first deploy: the page linked its assets as `http://` (the app runs
behind Google's TLS proxy) and the browser refused to load them on the `https` page. Fixed with
relative URLs, plus a regression test.

## 5. Load

30 concurrent requests, from a laptop in Spain:

| Endpoint | Result | p50 | p95 |
|----------|--------|-----|-----|
| `GET /api/cars` (database read) | 30 × 200 | 0.40 s | 0.52 s |
| `GET /` (rendered page) | 30 × 200 | 0.27 s | 0.40 s |

One negotiation turn end to end (api → seller → MCP → Vertex AI): 4.9–8.9 s.

## 6. Observability

Production traces reach Langfuse as one tree per turn: `invocation [haggle-seller]` →
`evaluate_offer` → `MCP send tools/call` → `mcp.evaluate_offer` → `policy.decide`. This
required CPU to stay allocated on the seller and MCP services (`cpu_idle = false`): with
request-based CPU, the background span exporter never got to run.

## 7. Infrastructure matches the code

`terraform plan -detailed-exitcode` after the deploy: **exit 0, "No changes. Your
infrastructure matches the configuration."** (A temporary `LANGFUSE_DEBUG` set with gcloud
while debugging was reverted by `terraform apply`.)
