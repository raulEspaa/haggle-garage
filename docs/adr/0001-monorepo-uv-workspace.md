# ADR-0001: Monorepo with a uv workspace

- **Status:** Accepted (2026-10-09, after spike S1).
- **Date:** 2026-10-08

## Context

Five deployable or runnable units (api, seller, mcp, buyer, evals) share contracts (Pydantic models, DB models). One person, little time. You come from .NET, where a solution with several projects is normal.
The agent frameworks are heavy and move fast: ADK 2.11 pins `mcp >=1.24,<3` and `a2a-sdk >=0.3.4,<2` **[verified 2026-10-08]**.

## Options

| Option | Pros | Cons |
|--------|------|------|
| **A. One Python package**, one image, several entry points | Simplest tooling. One venv. | Every image carries ADK + LangGraph + everything (bigger, slower cold starts). No enforced boundaries. |
| **B. Monorepo + uv workspace** (one `uv.lock`, one `pyproject.toml` per member) | Clear boundaries. Consistent versions. One `uv sync`. Per-service images via `uv sync --package <name>`. Same mental model as `.sln` + `.csproj`. | All members must agree on every shared dependency version. |
| **C. Polyrepo** (one repo per service) | Total isolation. | Contract changes span repos. 4× CI and setup. Bad for a solo 8-week project. |
| **D. Monorepo, independent uv projects** (no workspace, path dependencies) | Each service can pin different versions. | Several lockfiles. Easier for versions to drift. |

## Decision

**B**, with **D as the escape hatch**. If spike S1 shows that the MCP server's `mcp` 2.x and ADK's MCP client cannot share one resolution, move `services/mcp` out of the workspace into an independent uv project. Nothing else changes.

## Why

- A single lockfile removes a whole class of "works on my machine" bugs while you are still learning Python packaging.
- It maps directly onto what you know: workspace = solution, member `pyproject.toml` = `.csproj`, `{ workspace = true }` = `ProjectReference`, `uv.lock` = `packages.lock.json`.
- Recruiters reading the repo see clear service boundaries.

## Consequences

- The `haggle-core` package must stay **framework-free** (Pydantic, SQLAlchemy only). Otherwise every service pulls ADK.
- Dockerfiles copy the whole workspace but install only one member (`uv sync --frozen --no-dev --package haggle-seller`).
- Dependabot/Renovate PRs update one lockfile. CI runs all tests on every bump.

## Spike S1 result (2026-10-09)

ADK 2.11.0, MCP SDK 2.3.0 and a2a-sdk 1.2.2 share one lockfile. The escape hatch was **not**
needed for `mcp`. The conflict that did appear was transitive: ADK pins
`opentelemetry-api <= 1.42.1`, FastAPI 0.143 requires `>= 1.44`. uv resolved it *silently* by
picking ADK 1.10.0 until `google-adk>=2.11` was forced. Lesson: **put lower bounds on the
frameworks you care about**, otherwise a resolver may "solve" a conflict by downgrading them.
FastAPI now resolves to 0.141.1.

## Revisit if

- S1 fails (apply D for `mcp`), or two frameworks pin incompatible `pydantic` / `opentelemetry` versions.
