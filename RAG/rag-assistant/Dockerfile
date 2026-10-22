# Assistant RAG — Ollama + LangChain (service du pilier IA, standalone)
# Contexte de build = racine du dépôt :  docker build -f rag-assistant/Dockerfile .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Dépendances d'abord (meilleur cache)
COPY rag-assistant/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Le code
COPY rag-assistant/ .

# Utilisateur non-root (DoD du projet)
RUN useradd -r app && mkdir -p /app/chroma && chown -R app /app
USER app

# Au démarrage : (ré)indexe si besoin, puis lance l'API.
# L'index se reconstruit si le dossier chroma est vide (ex. 1er lancement).
CMD ["sh", "-c", "python -c \"import pathlib,config,sys; sys.exit(0 if any(pathlib.Path(config.PERSIST_DIR).glob('*')) else 1)\" || python ingest.py; python app.py"]
