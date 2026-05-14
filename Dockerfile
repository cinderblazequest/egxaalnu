# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Multi-stage Dockerfile for СПАС — AI assistant for first aid (Telegram bot).
# Goals:
#  * tiny final image (no apt cache, no build toolchain),
#  * non-root runtime user,
#  * deterministic deps (pip --no-cache-dir),
#  * built-in HEALTHCHECK against the bot's /health endpoint.
# ---------------------------------------------------------------------------
ARG PYTHON_VERSION=3.12

# --- builder ---------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

# --- runtime ---------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

# ca-certificates: HTTPS to Telegram / GigaChat / OSM Overpass.
# tini (re-exec as PID 1): forwards SIGTERM cleanly so asyncio shutdown runs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tini curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 spas \
 && useradd --system --uid 10001 --gid spas --create-home --shell /bin/bash spas

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=spas:spas . .

USER spas

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent --max-time 4 http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "bot"]
