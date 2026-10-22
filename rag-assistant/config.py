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

# Modèle de génération (≤ 8 milliards de paramètres, exigence du sujet).
# Exemples : "llama3.1:8b", "qwen2.5:7b", "mistral:7b". À avoir fait `ollama pull` avant.
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")

# Modèle d'embeddings (transforme le texte en vecteurs pour la recherche).
# "nomic-embed-text" est léger et efficace. À faire `ollama pull nomic-embed-text`.
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# --- Source documentaire ---
# Dossier des docs d'exploitation (monté dans le conteneur). Indexe tous les .md.
DOCS_DIR = os.getenv("DOCS_DIR", "/app/docs")

# --- Base vectorielle (Chroma, stockage local persistant) ---
PERSIST_DIR = os.getenv("PERSIST_DIR", "/app/chroma")
COLLECTION = os.getenv("COLLECTION", "resilience-docs")

# --- Recherche ---
TOP_K = int(os.getenv("TOP_K", "4"))        # nb de fragments récupérés par question
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))   # taille max d'un fragment (caractères)
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

# --- Divers ---
PORT = int(os.getenv("PORT", "8000"))
