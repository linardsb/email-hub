# syntax=docker/dockerfile:1

# Multi-stage build for optimized production image

# Stage 1: Builder - Install dependencies
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-install-project --no-dev

COPY . .

RUN uv sync --locked --no-editable --no-dev

# Fix shebangs to use container python (UV_LINK_MODE=copy preserves host paths)
RUN find /app/.venv/bin -type f -exec sed -i '1s|^#!.*python.*$|#!/app/.venv/bin/python|' {} + 2>/dev/null || true

# Stage 2: Runtime - Minimal production image
FROM python:3.12-slim-bookworm@sha256:93ab4b7fa528b25124c97bcc755415e60eb671a86b4dbe0328df2fe2d1c1193d

# SECURITY: Create non-root user
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --shell /bin/false --create-home appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser . .

ENV PATH="/app/.venv/bin:$PATH"

# SECURITY: Run as non-root user
USER appuser

EXPOSE 8891

HEALTHCHECK --interval=15s --timeout=10s --retries=5 --start-period=120s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8891/health')" || exit 1

CMD ["sh", "-c", "gunicorn app.main:app \
     -k uvicorn.workers.UvicornWorker \
     -w ${WEB_CONCURRENCY:-2} \
     --preload \
     --max-requests 1000 \
     --max-requests-jitter 100 \
     --bind 0.0.0.0:8891 \
     --timeout 120 \
     --graceful-timeout 30"]
