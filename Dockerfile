# The Evidentia API, for Cloud Run. Only the `evidentia` package goes in: no tests, no evals,
# no web app, and never a .env file (see .dockerignore). Keys arrive as environment variables.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Dependencies first, so editing the code does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project

COPY evidentia ./evidentia
RUN uv sync --frozen --no-default-groups

ENV PATH="/app/.venv/bin:$PATH"
USER nobody

# Cloud Run tells the container which port to listen on through PORT.
CMD ["sh", "-c", "uvicorn evidentia.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
