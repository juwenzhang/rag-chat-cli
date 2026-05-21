FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev \
    && chmod +x /app/deploy/backend/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/deploy/backend/entrypoint.sh"]
CMD ["sh", "-c", "uv run uvicorn api.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
