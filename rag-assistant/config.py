# ===================================================================
# CONFIGURATION DE L'ASSISTANT RAG
# Tout se règle par variables d'environnement (valeurs par défaut ici).
# ===================================================================
import os

# --- Ollama (le LLM local) ---
# URL du serveur Ollama. Trois cas courants :
#   - Ollama sur le PC IA        : http://192.168.137.X:11434
#   - Ollama sur le PC Hôte      : http://host.docker.internal:11434  (depuis un conteneur)
#   - Ollama en conteneur        : http://ollama:11434
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")

# Modèle de génération (≤ 8 milliards de paramètres, exigence du sujet). À avoir fait
# `ollama pull` avant. Mesuré sur le PC Hôte (CPU seul) :
#   - qwen2.5:3b  : lecture ~20 tokens/s, écriture ~6 tokens/s → réponse en ~1 min
#   - llama3.1:8b : lecture ~6 tokens/s,  écriture ~3 tokens/s → plusieurs minutes
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")

# Durée pendant laquelle Ollama garde le modèle en mémoire après une question. Par défaut
# (5 min), chaque question espacée repaie le chargement (5 s en 3B, 20 s en 8B).
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "30m")

# Longueur maximale d'une réponse, en tokens. Sur CPU, l'écriture domine la latence : une
# réponse bornée tient dans le délai du relais payment-api.
NUM_PREDICT = int(os.getenv("NUM_PREDICT", "256"))

# Modèle d'embeddings (transforme le texte en vecteurs pour la recherche).
# "nomic-embed-text" est léger et efficace. À faire `ollama pull nomic-embed-text`.
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# --- Source documentaire ---
# Dossier des docs d'exploitation (monté dans le conteneur). Indexe tous les .md.
DOCS_DIR = os.getenv("DOCS_DIR", "/app/docs")

# --- Base vectorielle (Chroma, stockage local persistant) ---
PERSIST_DIR = os.getenv("PERSIST_DIR", "/app/chroma")
# Le suffixe de version change avec la façon d'indexer (découpage, modèle ou préfixes
# d'embeddings) : la nouvelle collection est vide, donc reconstruite au démarrage, au lieu
# de mélanger des vecteurs incompatibles. v2 : préfixes nomic (cf. embeddings.py).
COLLECTION = os.getenv("COLLECTION", "resilience-docs-v2")

# --- Recherche ---
# Nb de fragments donnés au LLM. Chaque fragment (~300 tokens) se lit à ~20 tokens/s
# en 3B sur CPU : 2 fragments, ~30 s de lecture.
TOP_K = int(os.getenv("TOP_K", "2"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))   # taille max d'un fragment (caractères)
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

# --- Divers ---
PORT = int(os.getenv("PORT", "8000"))
