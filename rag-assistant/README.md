# Assistant RAG — Résilience Alpha

Assistant documentaire local (**Ollama + LangChain**, RAG) destiné aux opérateurs.
Il répond aux questions **uniquement à partir des docs d'exploitation**
(`docs/exploitation/`), **cite ses sources**, n'exécute aucune action et n'a
aucun accès privilégié au système. Contrat : `POST /ask → {answer, sources[]}`,
décrit dans [`contracts/rag-ask.schema.json`](../contracts/rag-ask.schema.json).

## Comment ça marche

```
docs/exploitation/*.md → découpage par titres (+ frontmatter) → embeddings (Ollama)
   → base vectorielle Chroma → recherche des passages pertinents → réponse LLM citée
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | Réglages (URL Ollama, modèles, dossiers, top_k) — par défaut déjà prêts |
| `embeddings.py` | Embeddings `nomic-embed-text` avec leurs préfixes de tâche |
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
ollama pull qwen2.5:3b           # le LLM (modèle par défaut, ~2 Go)
ollama pull nomic-embed-text     # les embeddings (recherche, ~275 Mo)
ollama list                      # vérifier : les deux doivent apparaître
```

**Pourquoi un modèle 3B.** Sur le PC Hôte, Ollama tourne sur le CPU seul (`ollama ps` :
`100% CPU`). Mesures (`ollama run <modèle> --verbose`) :

| Modèle | Chargement | Lecture du contexte | Écriture | Réponse RAG |
|---|---|---|---|---|
| `qwen2.5:3b` (défaut) | 5 s | ~20 tokens/s | ~6 tokens/s | ~1 min |
| `llama3.1:8b` | 20 s | ~6 tokens/s | ~3 tokens/s | > 4 min (délai dépassé) |

Le sujet impose ≤ 8 Md de paramètres : le 3B est conforme. Pour essayer un autre modèle,
`ollama pull <modèle>` puis `RAG_LLM_MODEL=<modèle>` dans `.env` et
`docker compose up -d rag-assistant` (pas de réindexation : seul le LLM change).

## Étape 3 — Vérifier qu'Ollama est joignable depuis Docker

Vérifier d'abord sur l'hôte : `curl http://localhost:11434/api/tags` doit renvoyer la
liste des modèles. Le test depuis le conteneur se fait à l'étape 5.

Par défaut Ollama n'écoute que sur `127.0.0.1`. Docker Desktop relaie normalement
`host.docker.internal` vers la boucle locale de l'hôte : **essayer d'abord sans rien
changer**. Seulement si le conteneur ne joint pas Ollama (`Connection refused`), le faire
écouter sur toutes les interfaces :

1. Menu Démarrer → « Modifier les variables d'environnement système » → **Variables d'environnement**.
2. Ajouter une variable **utilisateur** : nom `OLLAMA_HOST`, valeur `0.0.0.0:11434`.
3. **Quitter puis relancer Ollama** (clic droit sur l'icône Ollama → Quitter, puis le rouvrir).

> ⚠️ Avec `0.0.0.0`, l'API d'Ollama (sans authentification) devient joignable depuis le
> point d'accès de la démo, donc depuis le PC Attaquant : il pourrait saturer le CPU du
> PC Hôte en pleine remédiation. Bloquer alors le port depuis ce réseau
> (PowerShell **administrateur**) :
>
> ```powershell
> New-NetFirewallRule -DisplayName "Ollama - bloque le point d'acces" -Direction Inbound `
>   -Protocol TCP -LocalPort 11434 -RemoteAddress 192.168.137.0/24 -Action Block
> ```

## Étape 4 — Le service dans Compose

Le service est déjà déclaré dans `compose.yaml` (PC Hôte) et `compose.dev.yaml` (dev),
avec le volume `rag_chroma` pour l'index. Points à connaître :

- **Réseau (PC Hôte)** : uniquement `llm`, partagé avec `payment-api`, son seul client.
  Ne pas le rattacher en plus à `backend` ou `monitoring` : ces réseaux sont `internal`,
  et le conteneur perdait alors sa route vers l'hôte (`socket.gaierror` sur
  `host.docker.internal`, puis `[Errno 101] Network is unreachable` même avec
  `gw_priority`). Conséquence assumée : Prometheus ne collecte pas `/metrics`.
- **Aucun port publié** sur le PC Hôte, et aucune route WAF. En dev, `127.0.0.1:8004`
  pour tester `POST /ask` directement.
- **`extra_hosts: host.docker.internal:host-gateway`** : l'adresse de l'hôte est écrite
  dans `/etc/hosts`, sans dépendre du DNS de Docker.
- **Ollama ailleurs** (PC IA) : définir `OLLAMA_BASE_URL=http://<ip>:11434` dans `.env`.
- **Modèle** : `RAG_LLM_MODEL` dans `.env` (défaut `qwen2.5:3b`).
- **Indexation au démarrage** : tant que la collection est vide, chaque démarrage retente
  l'indexation. Après une panne d'Ollama, un `docker compose restart rag-assistant` suffit.
- **Healthcheck** sur `/health/ready` : le conteneur reste `unhealthy` tant que l'index
  est vide (Ollama injoignable au premier démarrage, par exemple).
- `payment-api` ne dépend pas de `rag-assistant` : le paiement fonctionne sans lui.

## Étape 5 — Construire et lancer

```powershell
docker compose build rag-assistant
docker compose up -d rag-assistant
```

Au **premier démarrage**, le conteneur indexe automatiquement les docs (il calcule
les embeddings via Ollama — quelques dizaines de secondes). Les fois suivantes,
l'index persistant est réutilisé.

La collection porte un numéro de version (`COLLECTION`, actuellement
`resilience-docs-v2`). Quand la façon d'indexer change (découpage, modèle ou préfixes
d'embeddings), on l'incrémente : la nouvelle collection est vide, donc reconstruite au
démarrage, sans mélanger des vecteurs incompatibles ni vider le volume à la main.

## Étape 6 — Vérifier

```powershell
docker compose logs -f rag-assistant      # doit finir par "Uvicorn running on ..."
docker compose exec rag-assistant python -c "import urllib.request as u; print(u.urlopen('http://localhost:8000/health/ready').read().decode())"
# Ollama vu depuis le conteneur (liste des modèles) — cf. étape 3 si échec :
docker compose exec rag-assistant python -c "import os,urllib.request as u; print(u.urlopen(os.environ['OLLAMA_BASE_URL'] + '/api/tags', timeout=5).read().decode()[:300])"
```
`/health/ready` doit renvoyer `{"status":"ready","documents":N}` avec N > 0. Si l'index est
vide ou illisible, il répond **503** (la commande ci-dessus affiche alors une `HTTPError 503`).

> L'image `python:3.12-slim` ne contient pas `curl` : les vérifications passent par Python.

## Étape 7 — Tester une vraie question

Depuis le conteneur (sur le PC Hôte, le service ne publie aucun port ; en dev, ajouter
`-f compose.dev.yaml` après `docker compose`) :

```powershell
docker compose exec rag-assistant python -c "import json,urllib.request as u; r=u.Request('http://localhost:8000/ask', json.dumps({'question': 'Que faire en cas de flood HTTP sur payment-api ?'}).encode(), {'Content-Type': 'application/json'}); print(json.dumps(json.loads(u.urlopen(r, timeout=180).read()), ensure_ascii=False, indent=2))"
```

Compter environ une minute (CPU) ; la première question après démarrage d'Ollama ajoute
le chargement du modèle. Ensuite, le modèle reste en mémoire 30 min (`KEEP_ALIVE`).

La réponse doit être en français, ancrée dans la doc, avec une liste `sources`
pointant vers les fichiers de `docs/exploitation/`.

## Accès depuis le back-office

`rag-assistant` n'a pas d'authentification propre : il n'est **pas exposé par le WAF**
et ne publie aucun port. Le back-office (`/admin`, rôle `ops`) l'interroge via
`payment-api` : `POST /api/admin/assistant/ask` vérifie le jeton (rôle `ops`), puis relaie
la question vers `http://rag-assistant:8000/ask` sur le réseau Docker interne.
`payment-api` et `rag-assistant` partagent pour cela le réseau `llm` (PC Hôte) ou
`default` (dev).

Délais de la chaîne, du plus court au plus long, pour qu'une réponse lente arrive :
`payment-api` attend 120 s (`RAG_ASSISTANT_TIMEOUT_S`, puis 504 `assistant_timeout`), et
le WAF 150 s sur `/api/admin/assistant/ask` (`proxy_read_timeout`, au lieu des 60 s par
défaut de nginx).

---

## Réindexer après modification des docs

Les docs d'exploitation changent → il faut réindexer :

```powershell
docker compose rm -sf rag-assistant           # arrête et supprime le conteneur
docker volume rm resilience-host_rag_chroma    # vide l'index (dev : resilience-alpha_rag_chroma)
docker compose up -d rag-assistant             # index vide → réindexation au démarrage
```

Un simple `restart` ne suffit pas : l'index n'est reconstruit que s'il est vide. Et
relancer `python ingest.py` sur un index existant **ajoute** les fragments à la
collection au lieu de la remplacer (doublons dans les sources).
Le nom du volume se vérifie avec `docker volume ls | Select-String rag_chroma`.

## Réglages (config.py / variables d'env)

- `OLLAMA_BASE_URL` : où joindre Ollama (`http://host.docker.internal:11434` ici).
- `LLM_MODEL` / `EMBED_MODEL` : les modèles Ollama (déjà téléchargés à l'étape 2).
  Dans Compose, `LLM_MODEL` vient de `RAG_LLM_MODEL` (`.env`).
- `TOP_K` : nombre de passages donnés au LLM (défaut 2 ; chacun ajoute ~15 s de lecture).
- `NUM_PREDICT` : longueur maximale d'une réponse en tokens (défaut 256).
- `KEEP_ALIVE` : durée de maintien du modèle en mémoire (défaut `30m`).
- `COLLECTION` : nom versionné de la collection (cf. étape 5).

**Préfixes d'embeddings.** `nomic-embed-text` attend `search_document: ` devant les textes
indexés et `search_query: ` devant les questions (`embeddings.py`). Sans eux, la
recherche ramenait des passages hors sujet (ex. « À quoi sert le relais L4 ? » ne
trouvait pas RB-06).

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
- **Réponses lentes ou `assistant_timeout`** : vérifier le modèle utilisé (`ollama ps`,
  champ `model` du log `rag.answer`) ; un 8B sur CPU est trop lent. Vérifier aussi que le
  PC est sur secteur, en mode performances.

## Limites assumées

- L'assistant ne répond que ce qui est dans la doc ; une information absente est
  signalée (« je ne trouve pas… »), pas inventée.
- La qualité dépend du modèle et de la fraîcheur de l'index.
- Il est **séparé** du moteur de remédiation : il n'agit jamais sur le système.
