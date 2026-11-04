# ---- web build -------------------------------------------------------------
FROM node:22-slim AS web

RUN corepack enable
WORKDIR /web

COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ .
RUN pnpm build

# ---- runtime ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev

COPY api/ .
COPY seed/ /seed/
COPY --from=web /web/dist ./app/static

EXPOSE 8000

# Migrations are idempotent; running them on boot keeps the single-container
# deployment simple. In a multi-instance deployment this becomes a release step.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
