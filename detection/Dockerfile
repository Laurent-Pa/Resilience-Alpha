# Image du service de détection d'anomalies
FROM python:3.12-slim

WORKDIR /app

# Dépendances d'abord (meilleur cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Le code
COPY . .

# Utilisateur non-root (DoD du projet). detect.py ne fait que LIRE model.joblib,
# donc la racine en lecture seule suffit ; collect/train se lancent en local.
RUN useradd -r app && chown -R app /app
USER app

# Par défaut, le conteneur lance la détection en continu.
# (La collecte et l'entraînement se font une fois, à la main — voir README.)
CMD ["python", "detect.py"]
