FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs/ libs/
COPY services/remediation-engine/ services/remediation-engine/
RUN uv sync --frozen --no-dev --package remediation-engine
# Modules Docker des playbooks infra (via docker-socket-proxy : DOCKER_HOST=tcp://...).
RUN /app/.venv/bin/ansible-galaxy collection install -p /usr/share/ansible/collections \
    "community.docker:>=4,<5"
RUN useradd -r app && chown -R app /app
USER app
# Pas de `uv run` au runtime (cache dans le home non-root inexistant) : binaires du venv.
# HOME : ansible écrit ~/.ansible/tmp, l'utilisateur système n'a pas de home.
ENV PATH="/app/.venv/bin:$PATH" HOME=/tmp
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live').status==200 else 1)"
CMD ["uvicorn", "--factory", "remediation_engine.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
