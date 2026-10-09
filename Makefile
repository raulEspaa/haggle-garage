# Developer entry points. Run `make` (or `make help`) to list them.
.DEFAULT_GOAL := help
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

.PHONY: help sync fmt lint types test test-db check db-up db-down db-reset migrate seed api \
        docker-api docker-mcp mcp seller play spike precommit-install tf-check doctor test-llm ingest

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ----------------------------------------------------------------------------- setup
doctor: ## Check that every required tool is installed and configured
	@for t in uv git make docker terraform gcloud gh; do \
		if command -v $$t >/dev/null 2>&1; then \
			printf "  \033[32m✓\033[0m %-10s %s\n" $$t "$$($$t --version 2>&1 | head -1)"; \
		else printf "  \033[31m✗\033[0m %-10s not installed (docs/learning/setup-tools.md)\n" $$t; fi; \
	done
	@if docker compose version >/dev/null 2>&1; then echo "  ✓ docker compose plugin"; \
		else echo "  ✗ docker compose plugin missing"; fi
	@if docker info >/dev/null 2>&1; then echo "  ✓ docker daemon reachable without sudo"; \
		else echo "  ✗ docker daemon not reachable without sudo (log out and back in after usermod)"; fi
	@if gcloud auth application-default print-access-token >/dev/null 2>&1; then \
		echo "  ✓ gcloud application-default credentials (used by Terraform)"; \
		else echo "  ✗ no gcloud ADC: run gcloud auth application-default login"; fi
	@if gh auth status >/dev/null 2>&1; then echo "  ✓ gh authenticated"; \
		else echo "  ✗ gh not authenticated: run gh auth login"; fi
	@if [ -n "$$(git config user.email)" ]; then echo "  ✓ git identity: $$(git config user.name) <$$(git config user.email)>"; \
		else echo "  ✗ git identity not set (git config --global user.name/user.email)"; fi

# ----------------------------------------------------------------------------- python
sync: ## Create/refresh .venv exactly as described by uv.lock
	uv sync

fmt: ## Auto-format and auto-fix lint issues
	uv run ruff format .
	uv run ruff check --fix .

lint: ## Lint + formatting check (no changes)
	uv run ruff check .
	uv run ruff format --check .

types: ## Static type checking (mypy strict)
	uv run mypy

test: ## Run tests (DB tests are skipped if Postgres is down)
	uv run pytest

test-db: ## Run tests and FAIL if Postgres is not reachable (what CI does)
	HAGGLE_REQUIRE_DB=1 uv run pytest --cov=haggle_core --cov=haggle_api

test-llm: ## Tests that call Gemini (costs tokens; needs GOOGLE_API_KEY in .env). Never in CI
	set -a && . ./.env && set +a && HAGGLE_REQUIRE_DB=1 uv run pytest -m llm -v

ingest: ## Embed db/sheets/*.md into pgvector (Gemini embeddings)
	uv run haggle-ingest

check: lint types test ## Everything CI checks for Python

# ----------------------------------------------------------------------------- database
db-up: ## Start local Postgres + pgvector and wait until healthy
	docker compose up -d --wait db

db-down: ## Stop local Postgres (data is kept in a Docker volume)
	docker compose down

db-reset: ## DELETE local DB data and recreate schema + seed
	docker compose down -v
	$(MAKE) db-up migrate seed

migrate: ## Apply Alembic migrations to HAGGLE_DATABASE_URL
	uv run alembic upgrade head

seed: ## Load the synthetic inventory (idempotent)
	uv run haggle-seed

# ----------------------------------------------------------------------------- run / build
api: ## Run the API locally with auto-reload on http://127.0.0.1:8080
	uv run haggle-api

mcp: ## Run the MCP server locally on http://127.0.0.1:8100/mcp (needs HAGGLE_MCP_*_TOKEN)
	uv run haggle-mcp

seller: ## Run the seller agent (A2A) on http://127.0.0.1:8200 (needs `make mcp` running)
	uv run haggle-seller

play: ## Play in the terminal: make play LEVEL=3 CAR=dodge-challenger-rt-1970
	uv run haggle-play --level $(or $(LEVEL),3) --car $(or $(CAR),dodge-challenger-rt-1970)

spike: ## Week 2 tracer bullet: ADK -> MCP -> A2A with a scripted model (no LLM, no cost)
	ADK_SUPPRESS_A2A_EXPERIMENTAL_FEATURE_WARNINGS=true uv run python spikes/w02_tracer_bullet.py

docker-mcp: ## Build the mcp container image
	docker build -f services/mcp/Dockerfile --build-arg GIT_SHA=$(GIT_SHA) -t haggle-mcp:$(GIT_SHA) .

docker-api: ## Build the api container image
	docker build -f services/api/Dockerfile --build-arg GIT_SHA=$(GIT_SHA) -t haggle-api:$(GIT_SHA) .

precommit-install: ## Install the git pre-commit hooks
	uv run pre-commit install

# ----------------------------------------------------------------------------- infra
tf-check: ## terraform fmt + validate (needs no cloud credentials)
	terraform -chdir=infra/terraform fmt -check -recursive
	terraform -chdir=infra/terraform init -backend=false -input=false
	terraform -chdir=infra/terraform validate
