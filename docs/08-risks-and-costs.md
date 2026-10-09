# 08 — Project Risks and Cost Estimate

## 1. Project risks

Probability (P) and impact (I) are rated H/M/L.

| ID | Risk | P/I | Mitigation | Early warning |
|----|------|-----|------------|---------------|
| R1 | **Scope exceeds ~73 h** | H/H | Checkpoints A/B/C and an ordered cut list ([05 §3](05-delivery-plan.md#3-checkpoints-and-cut-list)). Planned at ~92% of capacity. | Week 2 overruns by more than 2 h |
| R2 | **Fast-moving, experimental APIs**: ADK A2A is *experimental*, MCP SDK v2 renamed `FastMCP` → `MCPServer` with no compatibility shim, A2A moved to 1.0 | H/M | Week 2 tracer bullet. Exact pins in `uv.lock`. Thin adapters. Contract tests. Upgrade only at the start of a week. | Spike S1–S6 fails |
| R3 | `mcp` version conflict between ADK's MCP client and the MCP v2 server inside one lockfile | M/M | ADR-0001 escape hatch (separate uv project for `services/mcp`). | `uv lock` fails or S1 fails |
| R4 | Python inexperience slows Weeks 1–3 | M/M | C#→Python map ([09](09-repo-and-tooling.md#5-c--java--python-cheat-sheet)). Type hints everywhere + mypy. Small modules. Tests first for pure logic. | PRs over 400 lines |
| R5 | **Learning goal undermined**: AI-generated code you don't fully understand | M/M | Rule: you hand-write the policy engine, guards and leak detector. Assistants for boilerplate only. Explain each PR in your own words. | You can't explain a file without reading it |
| R6 | Game balance: L3 too stingy (no deals) or too generous | M/M | Tunable `β`, margin range, lowball ratio. Playtest with 2–3 friends at the end of W4. Deal-rate metric. | Deal rate < 40% or surplus share < 0.2 |
| R7 | Noisy eval results (LLM nondeterminism, small n) | H/L | ≥ 3 seeds, Wilson CIs, compare large deltas (L1 vs L3), pinned model ids. | CI width > the difference you claim |
| R8 | **GCP Free Trial ends at day 90 and stops all resources** | M/H | Calendar reminder. Upgrade the billing account to paid before day 90. Keep the budget alerts. | — |
| R9 | Model deprecation / price change (the 2.5 family is already "access limited"; 3.8 Flash promo pricing ends 2026-12-31) | M/L | Model ids in config. Re-run the eval smoke on change. | Deprecation emails |
| R10 | Cold starts make the demo feel broken | M/M | Pre-warm on page load, startup CPU boost, "waking up the dealer…" UI. Measure it. | Cold p95 > 15 s |
| R11 | Home outage (power, ISP, Proxmox maintenance) | H/L | Per-game fallback to Cloud Run MCP. | Health check failures |
| R12 | Langfuse units exceed 50k/month | L/L | Sample demo traces at 25%. Evals keep 100%. | Langfuse usage page |
| R13 | Neon free limits or cold-start latency | L/L | Pre-warm. Tiny data. The upgrade path is pay-as-you-go. | Latency on first query |
| R14 | Life happens (burnout, busy weeks) | M/H | Built-in slack. Cut early, not late. Checkpoint rituals. | Two weeks under 6 h |
| R15 | Legal/brand: real brands, scraped data, personal data | L/M | Real models used descriptively, no logos, "not affiliated" notice (ADR-0011). Synthetic prices and listings, privacy note, 30-day retention. | — |

## 2. Cost estimate

Prices **[verified 2026-10-08]** unless marked. Region europe-west1. Demo traffic assumed: **~300 human games/month**.

### 2.1 Unit costs (Gemini API, paid tier, standard)

| Model | Input / output per 1M tokens (USD) | Used for |
|-------|-----------------------------------|----------|
| `gemini-3.1-flash-lite` | 0.25 / 1.50 | seller, buyer (default) |
| `gemini-3.5-flash-lite` | 0.30 / 2.50 | seller variant in evals |
| `gemini-3.8-flash` | 0.75 / 3.75 until 2026-12-31, then 1.50 / 7.50 | judge, strong seller variant |
| `gemini-embedding-2` | 0.20 per 1M text tokens | RAG (3 sheets ≈ 5k tokens ≈ 0.001 USD) |

Per game (token counts are **estimates**; replace them with measured values after Week 6):

| Unit | Assumption | Cost |
|------|-----------|------|
| Human game (seller only) | 8 turns × 2 LLM calls × ~3k input + ~150 output | **≈ 0.016 USD** |
| Simulated game (seller + buyer + judge) | ~105k input + 8k output + judge | **≈ 0.04 USD** |
| Full eval run | 81 games + 240 attack runs | **≈ 5 USD** |

### 2.2 Monthly run cost (after launch)

| Item | Free allowance | Expected usage | USD/month |
|------|---------------|----------------|-----------|
| Cloud Run (3 services, scale to zero) | 180k vCPU-s, 360k GiB-s, 2M requests/month | ~30k vCPU-s | **0** |
| Artifact Registry | 0.5 GB | ~1–1.5 GB with cleanup policy | ~0.10 **[unit price unverified]** |
| Secret Manager | 6 active versions, 10k accesses | ~9 versions | ~0.20 **[unit price unverified]** |
| Cloud Storage (Terraform state) | 5 GB-months, **US regions only** | < 1 MB | 0 (place the bucket in `us-central1`) |
| Cloud Logging | free allotment **[unverified]** | small | 0 |
| Neon Free | 1 GB, 100 CU-h/project | < 100 MB | **0** |
| Langfuse Hobby | 50k units | ~30k | **0** |
| Cloudflare Zero Trust Free + Tunnel | up to 50 users | 1 service token | **0** |
| Domain | — | — | ~0.85 (≈ 10 USD/year, TLD-dependent, **[unverified]**) |
| Gemini (demo) | — | 300 × 0.016 | **≈ 5**, hard-capped at **10** |
| **Total** | | | **≈ 1–2 USD infra + ≤ 10 USD LLM** |

### 2.3 Project budget (8 weeks)

| Item | USD |
|------|-----|
| Development LLM calls (AI Studio **free tier**, synthetic data) | 0 |
| ~5 full eval runs + smokes | ~25 |
| Initial prepay for `haggle-prod` | 10 (it is the cap, not necessarily spent) |
| GCP infra over 2 months | ~2–4 (covered by the 300 USD trial credit, which **does not** apply to Gemini API) |
| Domain (yearly) | ~10 |
| **Expected total out of pocket** | **≈ 35–45 USD**, worst case bounded by caps |

### 2.4 Cost scenarios for the public demo

| Scenario | What happens | Monthly LLM |
|----------|--------------|-------------|
| Quiet (50 games) | — | < 1 USD |
| Normal (300 games) | — | ≈ 5 USD |
| Shared on LinkedIn (2,000 attempts in a day) | Per-IP limits + 60 games/hour global + 1 USD/day soft budget → ~60 games served that day, the rest get "come back tomorrow" | ≈ 1 USD that day |
| Abuser with rotating IPs | Global limits + daily budget stop it. The hard cap is the backstop. | ≤ 10 USD (cap) |

### 2.5 Cost hygiene checklist

- [ ] Budget alerts at 50/90/100% on the GCP billing account.
- [ ] AI Studio `haggle-prod`: prepay + monthly spend cap set. Free tier used only for `haggle-dev`.
- [ ] Artifact Registry cleanup policy (keep the last 3 images per service).
- [ ] Cloud Run `min-instances = 0` everywhere. `max-instances` set.
- [ ] Terraform state bucket in `us-central1` (always-free GCS is US-only).
- [ ] Calendar: Free Trial day 90 → upgrade billing. Cloudflare service token expiry. Gemini 3.8 Flash price change (2027-01-01).
