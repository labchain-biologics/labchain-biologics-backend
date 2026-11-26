# syntax=docker/dockerfile:1
# Titerlane Biologics API server image (AGPL-3.0-only).
# Build:  docker build -t titerlane-biologics-backend .
# Run:    see docs/self-hosting.md (migrations run as a separate one-shot container).

ARG PYTHON_VERSION=3.11

FROM ghcr.io/astral-sh/uv:0.13.10 AS uv

FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

# Dependencies first (cached layer), from the committed lock file only.
COPY pyproject.toml uv.lock ./
COPY sdk/pyproject.toml sdk/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package titerlane-biologics

# Then the application itself, installed as a regular (non-editable) package. No uv cache
# here: uv keys a local package's built wheel on pyproject.toml, so a cached wheel would
# ship stale application code.
COPY README.md LICENSE ./
COPY app/ app/
RUN uv sync --locked --no-dev --no-editable --no-cache --package titerlane-biologics

FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="Titerlane Biologics API" \
      org.opencontainers.image.description="Multi-omics LIMS and Nextflow orchestration API" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/titerlane-biologics/titerlane-biologics-backend"

# Pick up Debian security fixes published after the base image was built.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 titerlane \
    && useradd --system --uid 10001 --gid titerlane --no-create-home --shell /usr/sbin/nologin titerlane

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    SECRETS_DIR=/run/secrets \
    S3_ENDPOINT_URL=""

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY alembic.ini ./
COPY alembic/ alembic/
COPY LICENSE ./

USER titerlane:titerlane
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# A single worker: the AWS Batch run monitor runs inside the API process (see docs).
# --proxy-headers honours X-Forwarded-* from the IPs in FORWARDED_ALLOW_IPS (default 127.0.0.1).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
