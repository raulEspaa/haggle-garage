# Week 7: Cloud deployment and public guardrails

> **Goal:** a public URL a stranger can play, with every guardrail proven from the outside.

**Public URL: https://haggle-api-38346102533.europe-west1.run.app**

**Definition of Done** ([05-delivery.md](../05-delivery.md#1-plan-vs-shipped-week-by-week)):

| Done when… | Status |
|------------|--------|
| A stranger can play | ✅ the URL above |
| `terraform plan` shows no drift | ✅ exit 0, "No changes" |
| Every guardrail has written evidence | ✅ [`docs/results/deploy-checklist.md`](../results/deploy-checklist.md) |

---

## 1. The shape in the cloud

```
browser ──https──▶ haggle-api      (public: allUsers)            SA haggle-api
                      │ A2A + Google ID token (aud "haggle-seller")
                      ▼
                   haggle-seller   (IAM: only haggle-api)        SA haggle-seller ──▶ Vertex AI
                      │ MCP + ID token (aud "haggle-mcp") + app token
                      ▼
                   haggle-mcp      (IAM: only haggle-seller)     SA haggle-mcp    ──▶ Vertex AI
                      │
                      ▼
                   Neon Postgres (one role per service) · Secret Manager · Langfuse
```

**One service account per service** is the cloud version of least privilege: each container
runs with its own Google identity, and every permission is granted to that identity:

| Identity | May |
|----------|-----|
| `haggle-api` | invoke the seller; read 4 secrets |
| `haggle-seller` | invoke the MCP server; call Vertex AI; read its secrets |
| `haggle-mcp` | call Vertex AI (embeddings); read its secrets |

No API key exists anywhere: Gemini is reached through Vertex AI with the service's own identity
(ADR-0013).

---

## 2. Service-to-service auth: ID tokens

A private Cloud Run service checks every request for `Authorization: Bearer <token>`, where the
token is a JWT **signed by Google** for an identity with `roles/run.invoker`, and whose `aud`
(audience) names the target. On Cloud Run the caller gets it from the metadata server
(`google.oauth2.id_token.fetch_id_token`), cached for its hour of validity
([`haggle_core/gcp_auth.py`](../../packages/core/src/haggle_core/gcp_auth.py)).

| Caller → callee | How the token is attached |
|-----------------|---------------------------|
| api → seller | the A2A client's request hook (also covers the agent-card fetch) |
| seller → MCP | an `httpx.Auth` on the MCP HTTP client itself. A header provider would miss the session handshake and `tools/list`, and at L3 a missing tool fails closed (week 3) |

C# analogy: like calling a protected Azure API with a managed identity token
(`DefaultAzureCredential`), where the audience is the API's app ID URI.

---

## 3. Secrets without leaking them

- Terraform creates **secret containers** only. Values are added outside Terraform, so they
  never land in its state file (which anyone with bucket access could read).
- `infra/scripts/bootstrap-secrets.sh` generates random tokens with `openssl` and pipes them
  into `gcloud secrets versions add --data-file=-`: **stdin**, not arguments (arguments show up
  in `ps` and shell history).
- `haggle-provision-roles` creates the database roles and pipes their connection strings the
  same way. Each run **rotates** the passwords.
- Cloud Run resolves `secret_key_ref` when a container starts. Each service account can read
  only its own secrets.

---

## 4. The database: Neon and one role per service

The plan's roles ([03 §5.3](../03-contracts.md#53-roles-and-grants)) became
[`haggle_core/provision.py`](../../packages/core/src/haggle_core/provision.py), with
**column-level** grants where it matters:

- The **seller cannot read `games.floor_usd` at all**, not even by mistake or by a prompt
  injection that reaches its SQL. Its only window on a game is the view `seller_game_context`,
  which returns `NULL` for the floor at level 3. *Security enforced by the database, not by the
  prompt.*
- Postgres checks privileges per column for `UPDATE … SET` and for every column read in `WHERE`
  and `RETURNING`; `SELECT … FOR UPDATE` needs UPDATE on at least one column. So the grant list
  follows each service's actual queries.

**Tested before production:** the three services ran locally, each with its own role, and played
all three levels. That run found a missing grant (ADK's existing session tables in schema `adk`),
which would have broken the seller in the cloud.

Neon's direct and pooled endpoints differ only by `-pooler` in the host. The app uses the
direct one with small SQLAlchemy pools (3 + 2 overflow per instance).

---

## 5. Terraform: order matters

1. `make deploy-infra`: APIs, service accounts, **empty** secrets, IAM, budget, registry
   (a `-target`ed apply: services can't exist yet).
2. `make deploy-secrets` and `haggle-provision-roles --to-secret-manager`: give secrets values.
   Cloud Run refuses a revision that references a secret with no version.
3. `make deploy`: build the three images tagged with the **git commit** (a dirty tree is
   refused), push, `terraform apply`.

**Deterministic URLs** (`https://haggle-<service>-<project number>.<region>.run.app`) are known
before a service exists, so the api can point at the seller and the seller at the MCP server
without a dependency cycle in Terraform.

**Bootstrap.** One API had to be enabled by hand: the Cloud Resource Manager API, which Terraform
needs in order to enable APIs once `user_project_override` is on (required by the budget
resource). Like the state bucket in week 1, the very first piece can't build itself.

---

## 6. What broke on the way, and how it was found

| # | Symptom | Cause | Fix |
|---|---------|-------|-----|
| 1 | Seller couldn't use ADK's session tables | Missing grants, found by running locally under the new roles | Grants on existing tables of schema `adk` |
| 2 | **403** on every api → seller call | ID tokens carried the deterministic URL as audience; Cloud Run accepts the service URL or a **custom audience**. Diagnosed by elimination: bindings present, service returns 200 with a valid token and 403 without, client proven to send the header (local test server) | `custom_audiences = ["haggle-seller"]` / `["haggle-mcp"]` |
| 3 | Public page with **no CSS and no JS** | Behind Google's TLS proxy the app sees `http://`, so `url_for()` built `http://` asset links; the browser blocked them on an `https` page, and so did the CSP | Relative asset URLs + regression test |
| 4 | **No traces** from production | With request-based CPU (`cpu_idle = true`) Cloud Run throttles the CPU when the response is sent; the OpenTelemetry exporter runs in the background. Proved by elimination: the same image exported fine on a laptop; `LANGFUSE_DEBUG` showed spans processed but not shipped | `cpu_idle = false` on seller and MCP (they still scale to zero) |

Two habits that paid off: **reproduce outside the cloud** (a local test server for #2, the prod
image on a laptop for #4) and **change one thing at a time**, reverting debugging changes with
Terraform so the plan ends with no drift.

---

## 7. Guardrails, with evidence

All in [`docs/results/deploy-checklist.md`](../results/deploy-checklist.md):

- seller and MCP: **403** without a token; a forged token **401**; a valid Google identity
  without the app token **401** (two independent layers);
- 6th game from one IP: **429**, and spoofing `X-Forwarded-For` doesn't help;
- CSP, `X-Frame-Options`, `nosniff`, `no-referrer` on every page;
- 30 concurrent requests: 30 × 200, p95 0.5 s;
- daily game budget $2 (api and seller), 2 instances max, 10 EUR/month alert.

**About spending:** Vertex AI has no hard cap. The real limits are ours: the $2/day game budget
(about 150 human turns), 2 instances per service, and the per-IP limits. The GCP budget is only
an alert.

---

## 8. Your turn

1. Play at the URL from your phone (another IP): reach a deal at L3, then try to make L1 leak.
2. In the Cloud Run console, open `haggle-seller` → *Security*: see that it requires
   authentication, and → *Revisions*: see the image tag = the git commit.
3. Run `make deploy` after a small change (e.g. a word in `about.html`): what changes in the
   plan?
4. **Interview drill:** why isn't a private Cloud Run service reachable with just a valid Google
   login, and what does the audience claim protect against?

## 9. Glossary

| Term | Meaning |
|------|---------|
| Service account | A non-human Google identity; each Cloud Run service runs as one |
| ID token / audience | A Google-signed JWT proving who the caller is; `aud` says which service it is for |
| `run.invoker` | The IAM role that allows calling a Cloud Run service |
| Secret Manager | Versioned secret storage; Cloud Run injects versions as env vars |
| Request-based CPU | CPU only while a request is being served (cheap; no background work) |
| Drift | Differences between what Terraform describes and what exists in the cloud |
| Bootstrap | The first pieces that can't be created by the tool they enable |
