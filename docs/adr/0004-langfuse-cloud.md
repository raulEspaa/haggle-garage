# ADR-0004: Langfuse Cloud (Hobby) over self-hosted Langfuse

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

We need traces for two frameworks (ADK via OpenTelemetry, LangGraph via callbacks), scores attached to traces (leak, deal, margin), and datasets/experiments for the attack set. Your home server has 16 GB RAM in total and already runs other LXC services.

## Facts (verified 2026-10-08)

- **Langfuse Cloud Hobby:** free, **50k units/month**, **30 days** data access, **2 users**, region US/EU/JP. Includes datasets, experiments, LLM-as-judge evaluators, scores and annotation (1 queue). Next tier: Core, 29 USD/month.
- **Self-hosted (current major v4):** web + worker + **Postgres + ClickHouse + Redis/Valkey + S3/MinIO**. Docker Compose is recommended at **≥ 4 cores, 16 GiB RAM, 100 GiB disk** and documented as **not for production** (no HA, no backups).
- **Integrations:** ADK via `openinference-instrumentation-google-adk` (OTel) + `langfuse` SDK. LangGraph via `from langfuse.langchain import CallbackHandler`, with `metadata.langfuse_session_id`.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. Langfuse Cloud Hobby (EU)** | Zero ops. Free. All eval features you need. | 30-day retention. 50k units/month. Data leaves your infra (synthetic, fine). |
| **B. Self-hosted at home** | Unlimited retention. Infra learning. | Would use the whole mini PC. A **second home service exposed to Cloud Run** (traces must flow in). Ops burden. Not production-grade per its own docs. |
| **C. Self-hosted on GCP** | No home exposure. | ClickHouse + Postgres + Redis on GCP costs real money monthly. |
| **D. No tracing tool** (logs only) | Nothing to set up. | You lose the most visible "AI engineer" skill and the experiment UI. |

## Decision

**A.** Use the EU region. Export eval results to the repo too (JSONL + Markdown report), because retention is 30 days.

## Why

Observability is a tool here, not the product. Self-hosting would spend your scarcest resources (time and RAM) and add a second attack surface at home.

## Consequences

- Budget units: one 10-turn simulated game ≈ 100 units (estimate, **[unverified]** unit accounting). A full eval run ≈ 11k units. Sample demo traffic (25%) if you approach 50k.
- Put Langfuse keys in Secret Manager. Never log prompts that contain the floor at L1/L2 outside Langfuse. This is acceptable: synthetic, per-game.

## Revisit if

- You need more than 30 days of history for the final README. Snapshot the reports instead of upgrading.
