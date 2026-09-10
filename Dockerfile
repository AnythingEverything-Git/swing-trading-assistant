# TradePilot API image (Linux VPS / always-on ingest)
FROM python:3.12-slim-bookworm

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Runtime deps (keep in sync with pyproject.toml [project].dependencies)
RUN pip install --no-cache-dir \
    "fastapi>=0.115" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.0" \
    "sqlalchemy>=2.0" \
    "alembic>=1.13" \
    "psycopg[binary]>=3.2" \
    "uvicorn[standard]>=0.30" \
    "httpx>=0.27"

COPY alembic.ini /app/alembic.ini
COPY backend /app/backend

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8001/health || exit 1

CMD ["python", "run_api.py", "--host", "0.0.0.0", "--port", "8001"]
