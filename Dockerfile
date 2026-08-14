# syntax=docker/dockerfile:1

# ---------- deps (Node/Bun) ----------
FROM oven/bun:1-slim AS deps
WORKDIR /app
COPY package.json bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile --production

# ---------- runner (Bun + Python/uv for JobSpy) ----------
FROM oven/bun:1-slim AS runner

# uv is required at runtime: the server invokes JobSpy via `uv run python main.py`
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

ENV NODE_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
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

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD bun -e "fetch('http://localhost:9423/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

ENTRYPOINT ["bun", "run", "src/index.js"]
