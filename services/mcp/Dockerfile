# syntax=docker/dockerfile:1
# Build from the REPOSITORY ROOT (the workspace lockfile lives there):
#   docker build -f services/mcp/Dockerfile -t haggle-mcp:local .

ARG PYTHON_VERSION=3.13

# ----------------------------------------------------------------------------- builder
# Resolves and installs everything into /app/.venv. Nothing from this stage ships
# except that virtualenv.
FROM python:${PYTHON_VERSION}-slim-trixie AS builder

# Pin uv for reproducible builds (same version as local development).
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Layer 1: third-party dependencies only. Rebuilt only when the lockfile or a pyproject
# changes, not on every code edit. Bind mounts avoid copying files into the layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=packages/core/pyproject.toml,target=packages/core/pyproject.toml \
    --mount=type=bind,source=services/mcp/pyproject.toml,target=services/mcp/pyproject.toml \
    uv sync --frozen --no-install-workspace --package haggle-mcp

# Layer 2: our code. Only the workspace members this service needs.
COPY pyproject.toml uv.lock ./
COPY packages/core packages/core
COPY services/mcp services/mcp

# --no-editable installs real wheels into the venv, so the runtime image needs no source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --package haggle-mcp

# ----------------------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

ARG GIT_SHA=dev

# Never run as root inside the container.
RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HAGGLE_GIT_SHA=${GIT_SHA} \
    PORT=8100

USER app
EXPOSE 8100

# Cloud Run sends traffic to $PORT. Inside a container we must listen on all interfaces.
CMD ["sh", "-c", "exec uvicorn haggle_mcp.server:build_app --factory --host 0.0.0.0 --port ${PORT}"]
