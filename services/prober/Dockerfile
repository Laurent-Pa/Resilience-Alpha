# Contexte de build = racine du dépôt :
#   docker build -f services/prober/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs/ libs/
COPY services/prober/ services/prober/
RUN uv sync --frozen --no-dev --package prober

RUN useradd -r app && chown -R app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=2s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=1)"]

# Binaires du venv appelés directement (voir payment-api/Dockerfile).
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "--factory", "prober.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
