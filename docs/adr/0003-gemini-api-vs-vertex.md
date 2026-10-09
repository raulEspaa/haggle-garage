# ADR-0003: Gemini API (AI Studio) over Vertex AI / Gemini Enterprise Agent Platform

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

The public demo can be abused: strangers type into it and costs scale with their usage. The GCP account is new. You want minimal spend and **a hard ceiling**, not just alerts.
Note: **Vertex AI was rebranded as "Gemini Enterprise Agent Platform"** (announced at Cloud Next, April 2026). Secondary sources say the API endpoints are unchanged **[unverified on an official page]**. Below, "Vertex" means that platform.

## Facts (verified 2026-10-08 unless marked)

| | Gemini API (AI Studio) | Vertex / Agent Platform |
|---|---|---|
| Auth | API key | IAM / ADC. Keyless on Cloud Run via the service account. |
| Free tier | Yes, for most Flash/Flash-Lite models. **Free-tier content may be used to improve Google products.** | No free tier |
| GCP 300 USD trial credit | **Cannot be used** for Gemini API in AI Studio | Usable (not excluded; only AI Studio and partner models are) **[inferred]** |
| Hard spend cap | **Project Spend Caps** (monthly, set in AI Studio, enforced with ~10 min delay). **Prepay** credits (min 5 USD). Tier 1 billing-account cap 250 USD. | Cloud Billing **budgets alert only**. An Aug 2026 blog mentions project spend caps for Gemini Enterprise; whether they cover Agent Platform API calls is **[unverified]**. |
| Same SDK | `google-genai`; ADK switches backend by env var (`GOOGLE_GENAI_USE_VERTEXAI`) **[per ADK docs, not re-fetched]** | Same |
| Pricing | e.g. `gemini-3.1-flash-lite` 0.25 / 1.50 USD per 1M in/out tokens | Assumed equal for the same model **[unverified: page truncated]** |

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. Gemini API everywhere** (dev on a free-tier project, demo on a separate prepaid project with a spend cap) | Hard ceiling via prepay + project spend cap. Free dev iterations. Simplest setup. | API key to protect. Trial credit doesn't apply. |
| **B. Vertex everywhere** | Keyless (IAM). Trial credits pay for it during 90 days. | No simple hard cap: an abused demo can burn the trial credit, and when the trial ends **all resources stop**. After upgrading there is no cap. |
| **C. Gemini API for dev, Vertex for prod** | Keyless prod. | Two code paths to debug. Prod still has no hard cap. |

## Decision

**A.** Two AI Studio projects:

- `haggle-dev`: free tier, **synthetic data only**, used locally.
- `haggle-prod`: paid Tier 1 with **prepay (start with 10 USD)** + **monthly project spend cap**, used by the deployed demo and the eval runs. Paid-tier content is not used to improve products, which matters because strangers type into the demo.

Keep the code backend-agnostic: one env var flips to Vertex if you later want keyless auth.

## Why

For a public toy with an anonymous audience, **a hard cap beats keyless auth**. Leaking a key that is capped at 10 USD is a bounded incident. An uncapped keyless setup under abuse is not.

## Consequences

- Store the key in Secret Manager. Restrict it to the Generative Language API. Never ship it to the browser (the browser only talks to our API). Rotate it if logged.
- Enforcement has a ~10 min lag, so the API also keeps its own **daily soft budget** from `llm_usage` ([07](../07-threat-model.md)).
- You may need to **upgrade the GCP billing account** from Free Trial to paid to enable the paid tier. Upgrading keeps the remaining trial credit for other services **[unverified]**.
- **Calendar item:** the GCP Free Trial ends 90 days after signup. Upgrade before then or Cloud Run stops.
- `gemini-3.8-flash` promotional pricing ends 2026-12-31 (it doubles on 2027-01-01). The judge cost goes up after the project ends, which is fine.

## Week 3 finding

On the Gemini API backend, ADK cannot combine tools with a response schema natively (it does
only on Vertex AI). It adds an internal `set_model_response` tool and the model delivers its
final JSON by calling it. Output guards must therefore inspect that tool call too, not only text
responses (`haggle_seller/agent.py::_review_reply`). Switching to Vertex would change the path,
and both are tested (`ScriptedLlm(native_schema=...)`).

## Revisit if

- Agent Platform gets a documented hard project cap for model calls, or you want to demonstrate IAM-only auth: switch with one env var.
