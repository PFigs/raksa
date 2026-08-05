FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --no-install-project

COPY README.md ./
COPY src/ src/
RUN uv sync --no-editable

CMD ["uv", "run", "raksa", "meters", "sync-zaptec", "--submit"]