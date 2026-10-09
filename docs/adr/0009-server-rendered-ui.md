# ADR-0009: Server-rendered web UI, no SPA framework

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

The UI is one page: pick a level, chat, see offers, claim the floor, see the reveal. Optionally, watch an AI-vs-AI match stream. You are not targeting frontend roles, and time is tight.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. Jinja2 template + vanilla JS (`fetch`, `EventSource`)** served by FastAPI | No build step. One container. ~200 lines of JS. | Less "modern-looking" code. |
| **B. HTMX** | Even less JS. | One more concept to learn. SSE support needs an extension. |
| **C. React/Vite SPA** | Familiar to recruiters. | Build tooling, a second deploy artifact, CORS. A week you don't have. |
| **D. Streamlit/Gradio** | Fastest prototype. | Harder to apply rate limits and CSP. Looks like a notebook, not a product. |

## Decision

**A.** One HTML page, a small JS file and a CSS file (Pico.css or similar classless CSS from a CDN pinned with SRI, or vendored).

## Consequences

- **Output handling rule:** model text is inserted with `textContent` only. A strict **Content-Security-Policy** (`default-src 'self'`, no inline scripts) stops the classic "LLM output → XSS" chain (OWASP LLM05 Improper Output Handling).
- The game token lives in memory/`sessionStorage` for the tab's lifetime.
