# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# 1. Dashboard (React SPA) → src/spondex/server/static
# ---------------------------------------------------------------------------
FROM node:22-alpine AS dashboard
WORKDIR /app/src/dashboard
COPY src/dashboard/package.json src/dashboard/package-lock.json ./
RUN npm ci
COPY src/dashboard/ ./
# vite.config.ts writes to ../spondex/server/static
RUN npm run build

# ---------------------------------------------------------------------------
# 2. Python deps + package (uv)
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, for layer caching.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock README.md LICENSE .gitignore ./
COPY src/spondex ./src/spondex
COPY --from=dashboard /app/src/spondex/server/static ./src/spondex/server/static
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------------------------------------------------------------------------
# 3. Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" spondex \
 && useradd --uid "${UID}" --gid "${GID}" --home-dir /data --no-create-home --shell /usr/sbin/nologin spondex \
 && mkdir -p /data \
 && chown spondex:spondex /data

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    SPONDEX_HOME=/data \
    SPONDEX_DASHBOARD_HOST=0.0.0.0 \
    SPONDEX_HEADLESS=1

USER spondex
WORKDIR /data
VOLUME ["/data"]
EXPOSE 9847

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import socket; socket.socket(socket.AF_UNIX).connect('/data/daemon.sock')"]

STOPSIGNAL SIGTERM
CMD ["spondex", "run"]
