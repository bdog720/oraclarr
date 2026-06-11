# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
RUN useradd -m -u 10001 oraclarr
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src ./src
ENV PATH="/app/.venv/bin:$PATH" \
    ORACLARR_TRANSPORT=http \
    ORACLARR_HTTP_HOST=0.0.0.0 \
    ORACLARR_HTTP_PORT=7979 \
    ORACLARR_CONFIG=/config/config.yaml
EXPOSE 7979
USER oraclarr
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import socket,os; socket.create_connection(('127.0.0.1', int(os.environ['ORACLARR_HTTP_PORT'])), 3).close()"
ENTRYPOINT ["oraclarr-mcp"]
