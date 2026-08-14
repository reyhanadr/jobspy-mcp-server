# syntax=docker/dockerfile:1

# ---------- builder ----------
FROM python:3.12-slim AS builder

# Provide uv (binary only) from the official Astral image; pinned for reproducibility
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

# Optional proxy forwarded via `docker build --build-arg https_proxy=...`
ARG http_proxy
ARG https_proxy
ENV http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Create an isolated virtualenv and expose it via PATH
RUN uv venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Install deps first so this layer is cached until requirements.txt changes
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -r requirements.txt

# ---------- runner ----------
FROM python:3.12-slim AS runner

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Run as a non-root user
RUN groupadd -r app && useradd -r -g app app

# Copy only the built venv and the CLI entrypoint
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --chown=app:app main.py ./

USER app

ENTRYPOINT ["python", "main.py"]
