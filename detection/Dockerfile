# Contexte de build = racine du dépôt :
#   docker build -f detection/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv

# Venv hors de /app : en dev, ./detection est monté sur /app/detection (bind-mount) et masquerait un .venv local.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY detection/ detection/
RUN uv sync --frozen --no-dev --package detection

# Utilisateur non-root (DoD du projet). detect.py ne fait que LIRE model.joblib ;
# collect/train écrivent dans le dossier monté en dev (cf. README).
RUN useradd -r app && chown -R app /app
USER app

ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app/detection
# Par défaut, le conteneur lance la détection en continu.
CMD ["python", "detect.py"]
