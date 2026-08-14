# syntax=docker/dockerfile:1

# ---------- deps (Node/Bun) ----------
FROM oven/bun:1-slim AS deps
WORKDIR /app
COPY package.json bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile --production

# ---------- runner (Bun + Python/uv for JobSpy) ----------
FROM oven/bun:1-slim AS runner

# JobSpy deps (numpy/pandas/tls-client) ship glibc wheels -> install python3 on Debian
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

# uv is required at runtime: the server invokes JobSpy via `uv run python main.py`
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/app/jobspy/.venv \
    PATH="/app/jobspy/.venv/bin:$PATH"

WORKDIR /app

# Python deps first -> layer cached until requirements.txt changes
COPY jobspy/requirements.txt ./jobspy/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/jobspy/.venv \
    && uv pip install -r jobspy/requirements.txt

# Node production deps + source
COPY --from=deps --chown=bun:bun /app/node_modules ./node_modules
COPY --chown=bun:bun package.json ./
COPY --chown=bun:bun src ./src
COPY --chown=bun:bun jobspy/main.py ./jobspy/main.py

USER bun
EXPOSE 9423

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD bun -e "fetch('http://localhost:9423/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

ENTRYPOINT ["bun", "run", "src/index.js"]
