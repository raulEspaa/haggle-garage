# ADR-0013: Gemini through Vertex AI with ADC, paid by the trial credit

- **Status:** Accepted (2026-10-09, week 5). **Supersedes the decision of [ADR-0003](0003-gemini-api-vs-vertex.md)** (its facts and trade-offs still hold).
- **Date:** 2026-10-09

## Context

ADR-0003 chose the Gemini API (AI Studio) for its hard spend cap. In week 5:

- The free tier (15 requests/minute, shared by buyer and seller) made a 3 × 3 matrix take
  25 minutes. Week 6 needs ~80 games and ~240 attack runs.
- Upgrading AI Studio now means **prepay** (minimum 5 USD). Switching the project to prepay with
  a 0 balance made the key fail with `402 prepayment credits are depleted`.
- **The 300 USD Google Cloud trial credit cannot pay for the Gemini API in AI Studio**
  (*"The $300 credit can't pay for Gemini API in AI Studio costs"*, Google Cloud free-trial
  docs, verified 2026-10-09). The same docs only exclude AI Studio and partner models
  (model-as-a-service), not Google's own Gemini models on Vertex.
- The product owner prefers using the trial credit to prepaying.

## Facts checked on 2026-10-09 (in this project)

| Check | Result |
|-------|--------|
| `aiplatform.googleapis.com` | Enabled on `haggle-prod-417263` |
| `gemini-3.1-flash-lite` on Vertex, location `global` | Works (ADC, no key) |
| `gemini-embedding-2` on Vertex | Works on `global` and `us`; **404 on `europe-west1` and `us-central1`** |
| Same vectors as AI Studio? | **Yes**: cosine 1.00000 between stored AI Studio embeddings and Vertex re-embeddings of the same chunks. No re-ingest needed |
| Pricing on Vertex | Assumed equal to the Gemini API (`llm_costs.py`) **[unverified: pricing page truncated]**. The real cost is in the GCP billing report |

## Decision

**Vertex AI for every Gemini call** (seller, buyer, embeddings), authenticated with
**Application Default Credentials**: `gcloud auth application-default login` locally, the
service account on Cloud Run (week 7). Configuration is three environment variables, read by the
`google-genai` SDK inside ADK, LangChain and our embedder:

```
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=haggle-prod-417263
GOOGLE_CLOUD_LOCATION=global
```

The code stays backend-agnostic (`haggle_core.settings.gemini_configured()`): setting
`GOOGLE_GENAI_USE_VERTEXAI=false` plus `GOOGLE_API_KEY` switches back to AI Studio.

## Consequences

- **No API key to protect.** Locally the ADC file is mounted read-only into the compose
  containers. On Cloud Run the service account needs `roles/aiplatform.user` (week 7 Terraform).
- **No hard spend cap** (the ADR-0003 trade-off). During the trial, spend cannot exceed the
  credit. The public demo relies on our own caps: the api's daily budget and limits, the
  seller's budget gate, plus a GCP budget alert. **Revisit before the demo goes public (week 7).**
- **Calendar:** the trial ends 90 days after signup (around early January 2027). Upgrade the
  billing account before then or every resource stops.
- **ADK switches path on Vertex.** With tools and a response schema, ADK asks Gemini for both in
  one request on Vertex. Live, `gemini-3.1-flash-lite` then called `evaluate_offer` in a loop
  and never answered. The seller now uses `SellerGemini`, which keeps the `set_model_response`
  path on every backend, plus a per-turn model-call circuit breaker.
- **Env var naming:** ADK prefers `GOOGLE_GENAI_USE_ENTERPRISE` (after the Vertex rebrand), but
  `langchain-google-genai` 4.4 only reads `GOOGLE_GENAI_USE_VERTEXAI`. We keep the old name.

## Revisit when

- Before week 7's public deploy (spend cap), or when the trial credit runs low or expires.
- If `langchain-google-genai` adopts `GOOGLE_GENAI_USE_ENTERPRISE`.
