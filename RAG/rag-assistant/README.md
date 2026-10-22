# Assistant RAG — Résilience Alpha

Assistant documentaire local (**Ollama + LangChain**, RAG) destiné aux opérateurs.
Il répond aux questions **uniquement à partir des docs d'exploitation**
(`docs/exploitation/`), **cite ses sources**, n'exécute aucune action et n'a
aucun accès privilégié au système. Contrat : `POST /ask → {answer, sources[]}`.

## Comment ça marche

```
docs/exploitation/*.md → découpage par titres (+ frontmatter) → embeddings (Ollama)
   → base vectorielle Chroma → recherche des passages pertinents → réponse LLM citée
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | Réglages (URL Ollama, modèles, dossiers, top_k) — par défaut déjà prêts |
| `ingest.py` | Construit l'index Chroma à partir des docs |
| `app.py` | API HTTP : `POST /ask`, `/health/live`, `/health/ready`, `/metrics` |
| `requirements.txt`, `Dockerfile` | Dépendances et image |

---

# Mise en route complète (Ollama sur le PC Hôte)

Configuration retenue : Ollama tourne **directement sous Windows** sur le PC Hôte
(32 Go de RAM), le conteneur `rag-assistant` le joint via `host.docker.internal`.
Toutes les commandes se lancent depuis la **racine du dépôt** sauf indication.

## Étape 1 — Installer Ollama (Windows)

Télécharge et installe Ollama depuis **https://ollama.com/download**. Une fois
installé, il tourne en service en arrière-plan.

## Étape 2 — Télécharger les modèles

Dans PowerShell :

```powershell
ollama pull llama3.1:8b          # le LLM (8 Md paramètres = le max autorisé)
ollama pull nomic-embed-text     # les embeddings (recherche)
ollama list                      # vérifier : les deux doivent apparaître
```

## Étape 3 — Rendre Ollama joignable depuis Docker

Par défaut Ollama n'écoute que sur `127.0.0.1`, ce qui empêche un conteneur de le
joindre. On le fait écouter sur toutes les interfaces :

1. Menu Démarrer → « Modifier les variables d'environnement système » → **Variables d'environnement**.
2. Ajouter une variable **utilisateur** : nom `OLLAMA_HOST`, valeur `0.0.0.0:11434`.
3. **Quitter puis relancer Ollama** (clic droit sur l'icône Ollama → Quitter, puis le rouvrir).

Vérifier : `curl http://localhost:11434/api/tags` doit renvoyer la liste des modèles.

## Étape 4 — Ajouter le service au `compose.yaml`

Ajoute ce bloc aux `services:` du `compose.yaml`, et le volume à la fin :

```yaml
  rag-assistant:
    build:
      context: .
      dockerfile: rag-assistant/Dockerfile
    container_name: ra-rag-assistant
    restart: unless-stopped
    environment:
      OLLAMA_BASE_URL: "http://host.docker.internal:11434"
      LLM_MODEL: "llama3.1:8b"
      EMBED_MODEL: "nomic-embed-text"
      DOCS_DIR: "/app/docs"
    volumes:
      - ./docs/exploitation:/app/docs:ro    # la source documentaire (lecture seule)
      - rag_chroma:/app/chroma              # l'index persistant
    networks:
      - backend
    # Sur Docker Desktop (Windows), host.docker.internal fonctionne d'office.
    # (Sur un Docker Linux, décommenter la ligne suivante.)
    # extra_hosts: ["host.docker.internal:host-gateway"]
```

Et, sous la section `volumes:` du fichier (en créer une si absente) :

```yaml
volumes:
  rag_chroma:
```

## Étape 5 — Construire et lancer

```powershell
docker compose build rag-assistant
docker compose up -d rag-assistant
```

Au **premier démarrage**, le conteneur indexe automatiquement les docs (il calcule
les embeddings via Ollama — quelques dizaines de secondes). Les fois suivantes,
l'index persistant est réutilisé.

## Étape 6 — Vérifier

```powershell
docker compose logs -f rag-assistant      # doit finir par "Uvicorn running on ..."
docker compose exec rag-assistant curl -s http://localhost:8000/health/ready
```
`/health/ready` doit renvoyer `{"status":"ready","documents":N}` avec N > 0.

## Étape 7 — Tester une vraie question

Depuis le conteneur (ou n'importe où si tu publies le port) :

```powershell
docker compose exec rag-assistant curl -s -X POST http://localhost:8000/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\": \"Que faire en cas de flood HTTP sur payment-api ?\"}"
```

La réponse doit être en français, ancrée dans la doc, avec une liste `sources`
pointant vers les fichiers de `docs/exploitation/`.

## Étape 8 — (optionnel) Brancher le back-office

Pour que le panneau AssistantPanel du back-office `web-ops` l'utilise, l'infra
route `/api/assistant` vers `rag-assistant:8000` au niveau du WAF (même logique que
`/api/remediation`). Non nécessaire pour démontrer l'assistant isolément.

---

## Réindexer après modification des docs

Les docs d'exploitation changent → il faut réindexer :

```powershell
docker compose restart rag-assistant          # réindexe si l'index est vide
# Pour forcer une reconstruction complète :
docker compose down rag-assistant
docker volume rm <projet>_rag_chroma           # vide l'index
docker compose up -d rag-assistant
```

## Réglages (config.py / variables d'env)

- `OLLAMA_BASE_URL` : où joindre Ollama (`http://host.docker.internal:11434` ici).
- `LLM_MODEL` / `EMBED_MODEL` : les modèles Ollama (déjà téléchargés à l'étape 2).
- `TOP_K` : nombre de passages récupérés par question (défaut 4).

## Conseils pour la démonstration

- Montre l'assistant **avant ou après** la séquence de remédiation live, pas pendant :
  le LLM et la boucle de reprise se partageraient le CPU au moment critique.
- Exemples de questions qui montrent bien les citations : « Comment le système réagit
  à un flood HTTP ? », « Que signifie un incident ESCALATED ? », « À quoi sert le relais L4 ? ».

## En cas de souci

- **Le conteneur ne joint pas Ollama** (`Connection refused`) : vérifier l'étape 3
  (`OLLAMA_HOST=0.0.0.0:11434` + Ollama relancé) et le pare-feu Windows pour le port 11434.
- **`/health/ready` renvoie `empty`** : l'indexation a échoué — regarder les logs ;
  souvent Ollama injoignable au moment de l'index (mêmes causes que ci-dessus).
- **Réponses lentes** : normal au tout premier appel (chargement du modèle en RAM) ;
  les suivants sont plus rapides.

## Limites assumées

- L'assistant ne répond que ce qui est dans la doc ; une information absente est
  signalée (« je ne trouve pas… »), pas inventée.
- La qualité dépend du modèle et de la fraîcheur de l'index.
- Il est **séparé** du moteur de remédiation : il n'agit jamais sur le système.
