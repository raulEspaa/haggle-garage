# ADR-0005: Neon Postgres (free tier) as the single shared database

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

The api, seller and both MCP instances need the same data (games, floors, deals, RAG chunks). Principle P2 says the demo must not depend only on your home. So **the database cannot live at home**: if it did, the Cloud Run MCP fallback would be useless. pgvector is required.

## Facts

- **Neon Free [verified 2026-10-08]:** 100 projects. **1 GB storage per project**. **100 CU-hours per project per month**. **Scale-to-zero after 5 min** (cannot be disabled on Free). 10 branches. **pgvector included**. Next plan is pay-as-you-go (0.106 USD/CU-hour).
- **Cloud SQL:** no free tier. The smallest shared-core instance is roughly 8–10 USD/month **[unverified]**.
- **Supabase Free:** pauses inactive projects **[unverified details]**.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. Neon Free** | 0 USD. pgvector. Branching (an eval DB branch per run if you want). Standard Postgres wire protocol. | Cold start after idle. Vendor outside GCP (no IAM DB auth). |
| **B. Cloud SQL** | Same cloud, IAM auth, private IP. | Monthly cost from day 1. More Terraform. |
| **C. Postgres in a home LXC** | Free. Full control. | Demo depends on home (violates P2). Would need a second ingress path. |
| **D. Supabase Free** | Free, pgvector, extras. | Pausing behaviour. Extras you won't use. |

## Decision

**A. Neon Free** in AWS `eu-central-1` (close to `europe-west1`). Use **local Docker `pgvector/pgvector`** for development and CI, the same major version as Neon.

## Why

It is the cheapest option that satisfies P2 and pgvector, and it is plain Postgres, so the skills transfer.

## Consequences

- Connection strings (one per role) go in Secret Manager. Use Neon's pooled endpoint for the api.
- Expect a small first-query latency after idle. The page pre-warm hides most of it.
- Migrations run from your laptop (`alembic upgrade head` against Neon) in Week 7. No auto-migrate on service startup, except ADK's own session tables.

## Revisit if

- You exceed 1 GB (you won't with ~3 cars and transcripts), or you want to show IAM DB auth (move to Cloud SQL, ~10 USD/month).
