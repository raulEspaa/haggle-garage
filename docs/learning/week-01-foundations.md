# Week 1: Foundations and walking skeleton

> **Goal:** the thinnest slice that goes all the way from code to a public URL, with every
> quality gate already in place. Features come later. The *path to production* is built first.
> This is called a **walking skeleton**.

**Status of the Definition of Done** ([05-delivery-plan.md](../05-delivery-plan.md#week-1-foundations-and-walking-skeleton-9-h)):

| Done when… | Status |
|------------|--------|
| CI blocks a PR with a failing test | ✅ workflow written. Needs your GitHub repo to run (§11) |
| `alembic upgrade head` + seed works | ✅ verified against Postgres 16 + pgvector (§4, §5) |
| `terraform destroy && apply` recreates the service | ⏳ code validated (`terraform validate`). Needs your GCP project (§11) |
| A test budget alert email arrived | ⏳ your turn (§11) |

---

## 0. Tools

| Tool | What it is | Installed how |
|------|-----------|---------------|
| **uv** 0.12.23 | Package manager + virtualenv manager + Python installer (Rust, very fast) | `pipx install uv` (user-level, no sudo) |
| **Python 3.13.16** | Installed and managed *by uv*, not by the system | `uv python install 3.13` |
| git 2.53 | Already present | — |
| Docker, Terraform, gcloud | Need sudo → **you** install them (§11) | — |

Your system Python is 3.14. The project pins **3.13** in `.python-version`, so uv uses its own
3.13 for this project and never touches the system interpreter. That is the same idea as
`global.json` pinning an SDK version in .NET.

---

## 1. The uv workspace (≈ a .NET solution)

**Files:** [`pyproject.toml`](../../pyproject.toml), [`packages/core/pyproject.toml`](../../packages/core/pyproject.toml), [`services/api/pyproject.toml`](../../services/api/pyproject.toml), `uv.lock`

### Concepts

| Python / uv | .NET equivalent |
|-------------|-----------------|
| `pyproject.toml` | `.csproj` (metadata + dependencies + tool config) |
| workspace root with `[tool.uv.workspace] members = [...]` | `.sln` |
| `[tool.uv.sources] haggle-core = { workspace = true }` | `<ProjectReference>` |
| `uv.lock` (one for the whole workspace) | `packages.lock.json` |
| `.venv/` | the restored `bin/obj` + NuGet cache, per project |
| `uv run <cmd>` | `dotnet run` / running inside the right environment |

The root is a **virtual project** (`[tool.uv] package = false`): it is never built or deployed.
It only holds the dev tools and their configuration (ruff, mypy, pytest).

### Commands used (and what each did)

```bash
uv init --lib     --name haggle-core packages/core   # library, src/ layout, py.typed marker
uv init --package --name haggle-api  services/api    # app with an entry point
# uv noticed the workspace root and registered both members automatically.

uv add --package haggle-core sqlalchemy "psycopg[binary]" pgvector pydantic pydantic-settings pyyaml
uv add --package haggle-api  fastapi "uvicorn[standard]" haggle-core
uv add --dev haggle-core haggle-api alembic ruff mypy types-pyyaml pytest pytest-asyncio \
             pytest-cov hypothesis httpx2 pre-commit
```

`uv add` does three things: it resolves the newest compatible versions, writes a **lower bound**
(`sqlalchemy>=2.1.4`) into the right `pyproject.toml`, and updates `uv.lock` with **exact** pins
and hashes for every transitive dependency. Lower bounds go in `pyproject.toml` and exact pins
go in the lockfile. Commit both.

**Why `src/` layout?** Code lives in `src/haggle_core/`, not at the package root. Tests can then
only import the *installed* package, never the raw folder by accident. That catches packaging
mistakes (a missing file in the wheel) on your machine instead of in Docker.

**Why `requires-python = ">=3.13,<3.14"`?** This is an application, not a library. Restricting
the range keeps the resolver from solving for Python versions we never run.

> 💡 **Surprise found while building:** SQLAlchemy is at **2.1**, mypy at **2.4**, FastAPI at
> **0.143**. And Starlette now warns that its `TestClient` wants **`httpx2`** (the successor of
> httpx, maintained by the Pydantic team) instead of `httpx`. We switched to `httpx2` so the test
> run has zero warnings.

---

## 2. Configuration with pydantic-settings (≈ `IOptions<T>`)

**File:** [`settings.py`](../../packages/core/src/haggle_core/settings.py)

- Every setting is a typed field. The env var `HAGGLE_DATABASE_URL` fills `database_url`.
- `SecretStr` makes `repr(settings)` print `**********`, so the DB password can't leak into a log
  line by accident. You must call `.get_secret_value()` explicitly. A test proves this
  ([`test_settings.py`](../../packages/core/tests/test_settings.py)).
- `env: Literal["local", "prod"]`: an invalid value (e.g. `staging`) fails at startup. Fail fast
  is better than half-working in prod.
- `@lru_cache` on `get_settings()` gives a process-wide singleton (≈ `AddSingleton`).
- A local `.env` file is read for convenience. It is **gitignored**. Copy
  [`.env.example`](../../.env.example).

---

## 3. Database models with SQLAlchemy 2.x (≈ EF Core)

**Files:** [`domain.py`](../../packages/core/src/haggle_core/domain.py), [`db/base.py`](../../packages/core/src/haggle_core/db/base.py), [`db/models.py`](../../packages/core/src/haggle_core/db/models.py), [`db/session.py`](../../packages/core/src/haggle_core/db/session.py)

### Typed mappings

```python
class Car(Base):
    __tablename__ = "cars"
    id: Mapped[str] = mapped_column(primary_key=True)
    trim: Mapped[str | None]  # nullable because of `| None`
    year: Mapped[int] = mapped_column(SmallInteger)
```

`Mapped[...]` is to SQLAlchemy what a typed property is to EF Core. mypy understands it. The
nullability comes from the type: `str | None` means NULL is allowed.

### Decisions you should be able to defend

| Decision | Why |
|----------|-----|
| **Money as `int` (whole USD)** | Floats can't represent 0.1 exactly. Ratios use `NUMERIC` → `Decimal`. |
| **TEXT, not VARCHAR(n)** (`type_annotation_map` in `base.py`) | Same performance in Postgres. No migration needed when a string gets longer. |
| **Enums as TEXT + CHECK** built from Python `StrEnum`s (`one_of()`) | Python enums stay the single source of truth, and the DB enforces the same values. Native Postgres ENUMs need special DDL to add values. |
| **Naming convention** (`ck_games_level_range`, `fk_turns_game_id_games`…) | Alembic needs deterministic names to drop or alter constraints later. Also makes error messages readable. |
| **DB-level CHECKs** (level 1–3, floor < list price, turn_count ≤ cap) | Defense in depth: even buggy code or a manual SQL session cannot store an invalid game. |
| **`deals` primary key = `game_id`** | "At most one deal per game" is a *structural* guarantee, not an `if` in code. |
| **`Identity(always=True)`** for bigint ids | The modern SQL standard (`GENERATED ALWAYS AS IDENTITY`) instead of `serial`. |
| **UUIDv4 for `games.id`** | Unguessable (122 random bits). Reused as A2A `contextId` and Langfuse session id. |

### Async for services, sync for scripts

`session.py` builds an **async** engine (FastAPI, ADK and MCP are all async; one blocked thread
would stall every request). Migrations and the seed script use a plain **sync** engine. A
one-off script gains nothing from async. The same driver (**psycopg 3**) supports both.

C# mental model: `async def` ≈ `async Task`, `await` ≈ `await`. The big difference: Python has
**one** event loop thread. Calling a blocking function (e.g. `time.sleep`, a sync DB call) inside
`async def` freezes *everything*. Ruff's `ASYNC` rules catch some of these.

---

## 4. Migrations with Alembic (≈ EF Core migrations)

**Files:** [`alembic.ini`](../../alembic.ini), [`db/migrations/env.py`](../../db/migrations/env.py), [`versions/20261008_0001_initial_schema.py`](../../db/migrations/versions/20261008_0001_initial_schema.py)

```bash
uv run alembic init db/migrations                                  # scaffold
uv run alembic revision --autogenerate -m "initial schema" --rev-id 0001
uv run alembic upgrade head      # apply
uv run alembic downgrade base    # undo everything
uv run alembic check             # fails if models and DB disagree ("drift")
```

### Autogenerate is a *draft*, not the truth

Alembic compares your models to the live database and writes a migration. It **cannot know**
everything. I edited three things by hand, and you will always have to review migrations the
same way:

1. `CREATE EXTENSION IF NOT EXISTS vector` must run **before** the `VECTOR(768)` column.
2. The generated code referenced `pgvector.sqlalchemy.vector.VECTOR` without importing it.
   Replaced with `from pgvector.sqlalchemy import Vector`.
3. **Views are not in the ORM metadata.** The `seller_game_context` view was added by hand. It
   returns `floor_usd = NULL` when `level = 3`. That is the database-level half of "the L3
   seller cannot know the floor" ([03-contracts.md §5](../03-contracts.md#5-database-access)).

### Other details

- **No URL in `alembic.ini`** (it would end up in git). `env.py` reads it from settings.
- **Post-write hooks** run `ruff format` then `ruff check --fix` on every new migration. The
  order matters: formatting first fixes line lengths that the linter would complain about.
- **Round trip tested:** upgrade → downgrade → upgrade, then `alembic check` reported
  *"No new upgrade operations detected"*. A test now does this check on every CI run.

---

## 5. Seed data: YAML + Pydantic + upsert

**Files:** [`db/seed/cars.yaml`](../../db/seed/cars.yaml), [`seed.py`](../../packages/core/src/haggle_core/seed.py)

- **Fictional** brand *Vantor* (Kestrel, Brigand, Halberd), per [ADR-0010](../adr/0010-fictional-car-models.md):
  the LLM can't answer from memory, so RAG is measurable later.
- `yaml.safe_load`, **never** `yaml.load`: the unsafe loader can instantiate arbitrary Python
  objects from a file. That is a classic deserialization vulnerability.
- Pydantic validates before anything touches the DB:
  - `extra="forbid"`: a typo like `list_prize_usd` is an error, not silently ignored.
  - Cross-field rules (`floor_max_usd < list_price_usd`) live in `@model_validator`s.
- **Idempotent upsert:** `INSERT … ON CONFLICT (id) DO UPDATE`. Running `make seed` twice gives
  3 cars, not 6 (verified, and covered by a test).
- **One transaction** (`engine.begin()`): either every car is written or none is.

Usage: `uv run haggle-seed`. The command exists because of `[project.scripts]` in core's
`pyproject.toml`.

---

## 6. The API skeleton (FastAPI)

**File:** [`services/api/src/haggle_api/main.py`](../../services/api/src/haggle_api/main.py)

- **App factory** `create_app()`: every test gets a fresh app. No shared global state.
- `/healthz` is a **liveness** probe: "is the process alive?". It deliberately does **not** query
  the database. If Neon is asleep, Cloud Run must not kill healthy containers. A *readiness*
  check ("can I serve traffic?") is a different thing, added later if needed.
- **Host binding:** `uv run haggle-api` listens on `127.0.0.1` (not visible to your LAN). The
  container listens on `0.0.0.0` because Docker networking requires it. Ruff's security rule
  `S104` would flag a hardcoded `0.0.0.0`. Here the choice is explicit per environment.
- `PORT` comes from the environment because **Cloud Run injects it**.
- FastAPI generates OpenAPI for free: `GET /openapi.json`, and `/docs` for the Swagger UI.

---

## 7. Tests with pytest (≈ xUnit)

**Files:** [`packages/core/tests/`](../../packages/core/tests/), [`services/api/tests/`](../../services/api/tests/)

| pytest | xUnit |
|--------|-------|
| plain `assert x == y` (pytest rewrites it to show both values) | `Assert.Equal` |
| `@pytest.fixture` | constructor / `IClassFixture` |
| fixture `scope="session"` | `ICollectionFixture` (shared by all tests) |
| `@pytest.mark.parametrize` | `[Theory] [InlineData]` |
| `pytest.raises(X, match=...)` | `Assert.Throws<X>` |
| `monkeypatch.setenv` | setting env vars + restoring them in `Dispose` |

### The database test pattern

[`conftest.py`](../../packages/core/tests/conftest.py) is where shared fixtures live.

1. **Safety net:** DB tests refuse to run unless the database name ends in `_test`, because the
   fixture **drops the whole schema**. Pointing tests at a real DB by mistake is a classic
   disaster.
2. **Skip vs fail:** locally, no Postgres → the 7 DB tests are *skipped* with "Run `make db-up`".
   In CI `HAGGLE_REQUIRE_DB=1` turns that into a *failure*, so a broken CI database can't
   silently skip half the suite.
3. **Built by migrations, not by `create_all()`:** the test schema comes from
   `alembic upgrade head`, exactly like production. Tests therefore also test the migrations.
4. **Rollback per test:** the `conn` fixture opens a transaction and **always rolls back**. Tests
   can't leak data into each other.

What the DB tests prove: no schema drift, idempotent seed, CHECK constraints reject invalid
games, **the view hides the floor at level 3**, and only one deal per game.

### Results

```
without Postgres : 19 passed, 7 skipped
with Postgres    : 26 passed (warnings treated as errors), coverage 94%
```

> 🔧 **How I validated the DB without Docker:** I used `pgserver` (a pip package that bundles
> Postgres 16 + pgvector) in a throwaway environment *outside* the repo. The project itself uses
> the official `pgvector/pgvector:pg17` image. Run `make db-up && make test-db` once Docker is
> installed. It should give the same 26 passes.

---

## 8. Quality gates: ruff, mypy, pre-commit, gitleaks

**Files:** [`pyproject.toml`](../../pyproject.toml) (tool sections), [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)

- **ruff** = linter + formatter (replaces flake8, black, isort, bandit). Rules enabled: `E,F`
  basics, `I` imports, `B` likely bugs, `UP` modern syntax, **`S` security (bandit)**,
  **`ASYNC`** blocking calls in async code, `PT` pytest style, `SIM`, `RUF`.
  - Gotcha met: ruff didn't know `haggle_core` was *our* code and sorted it among third-party
    imports. Fixed with `known-first-party` in `[tool.ruff.lint.isort]`.
- **mypy `strict = true`**: the closest thing to the C# compiler's guarantees. Untyped functions
  are errors. The `pydantic.mypy` plugin understands Pydantic models.
- **pre-commit** runs on every `git commit`: whitespace/YAML/TOML checks, private-key detection,
  ruff, and **gitleaks** (scans staged changes for secrets *before* they enter git history,
  where they would stay forever).
  - Hooks are **frozen to commit SHAs** (`pre-commit autoupdate --freeze`). A tag can be moved
    by an attacker who compromises a repo, a commit SHA cannot. It's the same reason CI actions
    are pinned by SHA.

```bash
make precommit-install          # once per clone (already done in this one)
uv run pre-commit run --all-files
```

---

## 9. Docker image

**Files:** [`services/api/Dockerfile`](../../services/api/Dockerfile), [`.dockerignore`](../../.dockerignore), [`compose.yaml`](../../compose.yaml)

Multi-stage build, following uv's official Docker guide:

1. **builder** stage. uv is copied in from its official image, pinned to `0.12.23`.
   - Layer 1 installs **third-party deps only** (`--no-install-workspace`). It uses *bind mounts*
     of the lockfile and pyprojects, so it is rebuilt only when dependencies change, not on every
     code edit.
   - Layer 2 copies **only the members this service needs** (`core` + `api`) and installs them
     with `--no-editable`: real wheels inside `.venv`, so the source tree isn't needed at
     runtime.
2. **runtime** stage: a clean `python:3.13-slim-trixie` + the `.venv`. **Non-root user**. The
   git SHA is baked in as `HAGGLE_GIT_SHA`, so `/healthz` tells you which build is running.

`.dockerignore` keeps `.git`, `.env`, tests, docs and infra out of the build context. Smaller
builds, and no secrets in layers.

`compose.yaml` binds Postgres to **`127.0.0.1:5432`**, not `0.0.0.0`: a dev database with a
trivial password should not be reachable from your LAN.

> ⏳ **Not yet verified:** the Docker build itself (no Docker on this machine). First thing to run
> once installed: `make docker-api && docker compose up api`, then `curl localhost:8080/healthz`.

---

## 10. CI with GitHub Actions

**Files:** [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/dependabot.yml`](../../.github/dependabot.yml)

Three parallel jobs on every PR and push to `main`:

| Job | Does |
|-----|------|
| `python` | `uv sync --locked` (fails if `uv.lock` is stale) → ruff → mypy → pytest, against a real **Postgres service container** |
| `secrets` | gitleaks over the **full git history** (`fetch-depth: 0`) |
| `terraform` | `fmt -check`, `init -backend=false`, `validate` (no cloud credentials needed) |

Security details worth knowing:

- `permissions: contents: read`: the workflow token can't push, comment or release.
- Actions **pinned by commit SHA** (`actions/checkout@3d3c42e… # v7.0.1`).
- `persist-credentials: false`: the git token isn't left on disk for later steps.
- **No cloud or LLM credentials** in GitHub at all (threat T24).
- `concurrency` cancels outdated runs on the same branch.

Dependabot opens weekly PRs for uv, Actions, Docker and Terraform. Minor/patch Python bumps are
grouped into one PR.

---

## 11. Terraform (≈ infrastructure as C# code, but declarative)

**Files:** [`infra/terraform/`](../../infra/terraform/)

### Concepts in 6 lines

- **Provider** (`hashicorp/google`): plugin that talks to the GCP API. Pinned `~> 8.0`. The
  exact version (**8.6.0**) and hashes are in `.terraform.lock.hcl`. Commit it.
- **Resource**: something that should exist (`google_cloud_run_v2_service.api`).
- **State**: Terraform's memory of what it created. Stored in a **GCS bucket** (remote,
  versioned), never in git.
- **Plan / apply**: `plan` shows the diff between code and reality. `apply` executes it.
- **Partial backend config**: the bucket name is passed at `init`, not hardcoded.
- **Variables / outputs**: inputs (`project_id`) and results (`api_url`).

### What gets created

| Resource | Notes |
|----------|-------|
| `google_project_service` ×3 | Enables the Run, Artifact Registry and IAM APIs (disabled by default in new projects) |
| Artifact Registry `haggle` | **Cleanup policies**: keep the last 3 images, delete anything older than 14 days. Storage over 0.5 GB costs money. |
| Service account `haggle-api` | The service's identity. **Zero permissions** this week (least privilege). |
| Cloud Run `haggle-api` | min 0 / max 3 instances, `cpu_idle` (billed only while serving), startup CPU boost |
| IAM `allUsers → run.invoker` | Makes *this* service public. The seller and MCP will **not** get this. |

**Chicken-and-egg problem:** Cloud Run needs an image, but the registry that will hold our image
is created by the same Terraform. Solution: the first `apply` uses Google's public sample image
(the default of `var.api_image`). Then you push ours and apply again.

Validated locally with Terraform **1.16.5**: `fmt` clean, `validate` → *Success*.

---

## 12. Your turn ✋ (needs sudo or your accounts)

### 12.1 Install the tools (≈ 20 min)

Follow **[setup-tools.md](setup-tools.md)**: Docker, Terraform, gcloud and gh from the vendors'
apt repositories (all verified for Ubuntu 26.04), plus git identity, gh and gcloud logins.
`make doctor` tells you what is still missing. Then verify the local stack end to end:

```bash
make db-up && make migrate seed && make test-db     # expect 26 passed
make docker-api && docker compose up api            # then: curl localhost:8080/healthz
```

### 12.2 Accounts and guardrails (≈ 45 min)

1. **GCP project** (e.g. `haggle-prod-<random>`). The new account gets the 300 USD / 90-day trial.
   Put a **calendar reminder for day 80**: upgrade billing or Cloud Run stops at day 90.
2. **Budget alert:** Billing → Budgets & alerts → 10 USD, thresholds 50/90/100% → email.
3. **AI Studio:**
   - `haggle-dev`: API key on the **free tier**, synthetic data only.
   - `haggle-prod`: billing enabled, **prepay ~10 USD**, **monthly spend cap** on the Spend
     page. Nothing uses it until Week 3, but set the cap *before* creating keys.
4. **Langfuse Cloud** (EU region): create the org and the `haggle` project. Keys get used in
   Week 3.
5. **Neon**: can wait until Week 7.

### 12.3 First deploy (≈ 30 min)

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud auth application-default login      # credentials Terraform uses (ADC)

# One-time: bucket for Terraform state. US region = inside the always-free tier. Versioned.
gcloud storage buckets create gs://<PROJECT_ID>-tfstate --location=us-central1 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://<PROJECT_ID>-tfstate --versioning

cd infra/terraform
cp terraform.tfvars.example terraform.tfvars        # set project_id
terraform init -backend-config="bucket=<PROJECT_ID>-tfstate"
terraform apply                                     # first apply: Google's sample image
curl "$(terraform output -raw api_url)"             # sample "hello" page

# Build and push OUR image, then point Cloud Run at it
REPO=$(terraform output -raw image_repository)
gcloud auth configure-docker europe-west1-docker.pkg.dev
cd ../.. && make docker-api
SHA=$(git rev-parse --short HEAD)
docker tag haggle-api:$SHA $REPO/api:$SHA && docker push $REPO/api:$SHA
cd infra/terraform && terraform apply -var="api_image=$REPO/api:$SHA"
curl "$(terraform output -raw api_url)/healthz"     # {"status":"ok","service":"api","version":"<sha>"}

# Definition of done: prove the stack is reproducible
terraform destroy && terraform apply -var="api_image=$REPO/api:$SHA"
```

### 12.4 Commit and push

Everything is staged but **not committed**. That is your call:

```bash
git status
git commit -m "Week 1: uv workspace, DB schema, seed, API skeleton, CI, Terraform"
# create an empty public repo on GitHub, then:
git remote add origin git@github.com:<you>/haggle-garage.git
git push -u origin main
```

On GitHub, go to Settings → Branches and protect `main` (require the `ci` checks to pass).

---

## 13. Exercises (≈ 1 h, do them yourself)

1. **Migration practice:** add a nullable `vin_synthetic` column to `cars`. Generate a migration
   with `--autogenerate --rev-id 0002`, read it, run upgrade/downgrade, and check that
   `test_migrations_match_the_models` passes. Then delete it (`downgrade -1` + remove the file).
2. **Constraint practice:** write a DB test proving `turn_count` can't exceed `turn_cap`.
3. **Break the build on purpose:** make a test fail on a branch, open a PR, and watch CI block it.
   This is a Week 1 "done when" item.
4. **Explain out loud** (interview drill): why do DB tests refuse databases not ending in `_test`?
   Why is the floor hidden by a *view* and not just by "not putting it in the prompt"?

---

## 14. Glossary

| Term | Meaning |
|------|---------|
| Walking skeleton | Minimal end-to-end slice deployed to production, before any features |
| Lockfile | Exact versions + hashes of every dependency, for reproducible installs |
| Virtual project | uv workspace root that isn't itself a package |
| Migration | Versioned, reversible script that changes the DB schema |
| Drift | Models and database schema disagree |
| Idempotent | Running it twice has the same effect as once |
| Liveness probe | "Is the process alive?" Must not depend on external services |
| Remote state | Terraform's record of reality, stored outside the repo, versioned |
| Least privilege | Every identity gets only the permissions it needs, nothing more |
