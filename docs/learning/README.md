# Learning journal

One file per week. Each file explains **what was built, the commands used, and why**, with
pointers to the code. The goal is that you can rebuild every piece yourself and defend every
choice in an interview.

| Week | File | Theme |
|------|------|-------|
| 1 | [week-01-foundations.md](week-01-foundations.md) | uv workspace, SQLAlchemy + Alembic, tests, quality gates, Docker, CI, Terraform |
| 2 | [week-02-tracer-bullet-and-policy.md](week-02-tracer-bullet-and-policy.md) | ADK ↔ MCP ↔ A2A spike, Boulware policy + Hypothesis, MCP server v2, contract snapshots |
| 3 | [week-03-seller-agent-and-rag.md](week-03-seller-agent-and-rag.md) | RAG with pgvector, ADK seller with 3 levels, callbacks as guards, two fail-open bugs, Langfuse |
| 4 | [week-04-api-and-web-ui.md](week-04-api-and-web-ui.md) | FastAPI public API, demo limits, single flight, strict CSP page, six bugs found only in Docker |
| 5 | [week-05-buyer-agent-langgraph.md](week-05-buyer-agent-langgraph.md) | LangGraph buyer: state, reducers, structured output, code guard, personas, one trace across 3 processes |
| 6 | [week-06-evals.md](week-06-evals.md) | Leak detector, LLM judge + κ, 44 attacks, 81-game matrix, Wilson CIs, a run that lied, L2 prompt v1→v3 |
| 7 | [week-07-cloud-deploy.md](week-07-cloud-deploy.md) | Cloud Run ×3, IAM + ID tokens, Secret Manager, Neon roles per service, four production bugs |
| 8 | [week-08-retrospective.md](week-08-retrospective.md) | Cutting on purpose, a final eval that reproduces, a false alarm in the eval, docs that tell the truth, retrospective |

How to use them:

1. Read a section, then open the files it links.
2. Re-type, don't copy-paste, the small exercises at the end of each week.
3. The plan, what shipped, the costs and future work: [`../05-delivery.md`](../05-delivery.md).
