# syntax=docker/dockerfile:1

# ---------- deps (Node/Bun) ----------
FROM oven/bun:1-slim AS deps
WORKDIR /app
COPY package.json bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile --production

# ---------- runner (Bun + Python/uv for JobSpy) ----------
FROM oven/bun:1-slim AS runner

# Install wget for lightweight healthcheck and tini for proper PID 1 zombie reaping
RUN apt-get update && apt-get install -y --no-install-recommends wget tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    VIRTUAL_ENV=/app/jobspy/.venv \
    PATH="/app/jobspy/.venv/bin:$PATH"

WORKDIR /app

# JobSpy pins numpy==1.26.3 (no wheels for Python 3.13), so install standalone
# CPython 3.12 via uv instead of relying on the distro's default Python.
COPY jobspy/requirements.txt ./jobspy/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv python install 3.12 \
    && uv venv --python 3.12 /app/jobspy/.venv \
    && uv pip install -r jobspy/requirements.txt

# Node production deps + source
COPY --from=deps --chown=bun:bun /app/node_modules ./node_modules
COPY --chown=bun:bun package.json ./
COPY --chown=bun:bun src ./src
COPY --chown=bun:bun jobspy/main.py ./jobspy/main.py

USER bun
EXPOSE 9423

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -qO- http://localhost:9423/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "bun", "--smol", "run", "src/index.js"]

