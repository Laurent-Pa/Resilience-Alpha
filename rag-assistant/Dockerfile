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

# Au démarrage : indexe si la collection ne contient aucun document, puis lance l'API.
# On compte les documents plutôt que de tester si le dossier chroma est vide : l'API crée
# une base vide au premier /health/ready, et une indexation ratée (Ollama injoignable)
# ne serait alors plus jamais retentée. Ici, chaque redémarrage la retente.
CMD ["sh", "-c", "python -c \"import sys,app; sys.exit(0 if app._get_store()._collection.count() > 0 else 1)\" || python ingest.py; python app.py"]
