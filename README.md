# Resilience-Alpha

Projet EPSI Workshop M2 Bac+5 — plateforme de paiement fictive et conteneurisée, avec remédiation autonome face à une attaque simulée.

Ce dépôt couvre le **pilier développement** (payment-api, frontend, lib partagée). L'infra (Compose complet, Ansible, Prometheus/Grafana/Loki), l'IA (ml-detector, rag-assistant), la cyber (WAF, Vault, SIEM) et la gouvernance sont portées par d'autres membres de l'équipe. Voir `.claude/CLAUDE.md` pour le handoff complet (architecture, décisions, contrats, pièges connus).

## Arborescence

```
resilience-alpha/
├── README.md
├── Makefile                       # cibles dev : sync, test, lint, export-openapi, seed, dev-up, dev-down
├── pyproject.toml                 # racine du workspace uv
├── uv.lock
├── compose.dev.yaml                # stack de dev locale : postgres + payment-api
├── .secrets/                       # secrets locaux non commités (voir compose.dev.yaml)
├── contracts/
│   └── openapi-payment.json        # exporté depuis payment-api (make export-openapi)
├── libs/
│   └── common/                     # package resilience_common (logging, metrics, health, auth, hmac, settings)
│       ├── pyproject.toml
│       ├── src/resilience_common/
│       └── tests/
├── services/
│   └── payment-api/
│       ├── pyproject.toml
│       ├── Dockerfile
│       ├── alembic.ini
│       ├── migrations/
│       ├── src/payment_api/
│       │   ├── main.py             # create_app() — uvicorn --factory
│       │   ├── settings.py         # pydantic-settings, secrets lus depuis $SECRETS_DIR
│       │   ├── api/                # payments.py, accounts.py, admin.py
│       │   ├── domain/             # règles pures : rules.py, iban.py, bic.py
│       │   ├── repo/               # accounts.py, transactions.py, ledger.py
│       │   ├── service.py          # cas d'usage transactionnel (virement)
│       │   ├── crypto.py           # déchiffrement hybride RSA-OAEP + AES-GCM, HMAC IBAN
│       │   ├── models.py, db.py, schemas.py
│       │   ├── bootstrap.py        # migrations + seed au démarrage
│       │   ├── export_openapi.py
│       │   └── seed.py             # comptes fictifs, idempotent
│       └── tests/
├── frontend/                       # app de paiement (Next.js), servie sous `/`
│   ├── app/
│   │   ├── page.tsx                 # accueil
│   │   └── payment/page.tsx         # formulaire de virement
│   ├── lib/
│   │   ├── crypto.ts                # chiffrement hybride RSA-OAEP + AES-GCM (contrat §7)
│   │   ├── crypto.test.ts           # tests Vitest
│   │   ├── payments.ts              # client API (clé publique, virement, retry sur decryption_failed)
│   │   └── format.ts                # formatage IBAN, conversion euros/centimes
│   ├── .env.example                 # à copier en .env.local (gitignoré)
│   └── Dockerfile
└── observability
    ├── grafana/ provisioning/datasources
    │   └── datasources.yml          # sources de données pour brancher Prometheus et Loki
    ├── loki
    │    └── loki-config.yml      # version minimale, mono-instance, stockage local              
    └── prometheus
         └── prometheus.yml      # cibles désignées par le nom du conteneur Docker + Port      
```

`services/prober`, `services/remediation-engine` et `frontend-attack/` ne sont pas encore créés dans ce dépôt (voir `.claude/CLAUDE.md` §11-12 pour le plan). L'authentification Keycloak/OIDC côté frontend n'est pas encore implémentée : c'est la prochaine étape, sur une branche dédiée.

## Prérequis

- [uv](https://docs.astral.sh/uv/) (gestion du workspace Python)
- Node.js 20+ et npm (frontend)
- Docker Desktop (Windows : avec WSL2)

## Démarrage — backend (`payment-api`)

### 1. Secrets locaux

`payment-api` lit ses secrets depuis des fichiers (jamais en clair dans le code ni dans un `.env` commité). Pour le développement local, créer le dossier `.secrets/` à la racine (gitignoré) :

```bash
mkdir -p .secrets
openssl rand -hex 32 > .secrets/db_password
openssl rand -hex 32 > .secrets/iban_hmac_key
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out .secrets/rsa_private_key
openssl rand -hex 16 | tr -d '\n' > .secrets/grafana_admin_password
```

- `iban_hmac_key` est **obligatoire** : sans lui, le démarrage est refusé.
- `rsa_private_key` est recommandé pour la démo/le dev continu : sans lui, une clé RSA éphémère est générée à chaque redémarrage, ce qui invalide la clé publique mise en cache côté frontend (le frontend et le prober s'en remettent via un retry sur `decryption_failed`, mais c'est à éviter en usage courant).
- **Ne jamais régénérer `iban_hmac_key` sur une base existante** : les comptes deviennent introuvables par IBAN.

### 2. Lancer la stack (Postgres + payment-api)

```bash
docker compose -f compose.dev.yaml up -d --build
```

Ou via le Makefile (hors Windows sans `make`, lancer la commande Docker directement) :

```bash
make dev-up
```

Vérifier que tout est démarré :

```bash
docker compose -f compose.dev.yaml ps
docker compose -f compose.dev.yaml logs payment-api --tail=50
```

`payment-api` écoute en local sur `127.0.0.1:8001` (mappé vers le port interne `8000`). Au démarrage : migrations Alembic puis seed des comptes fictifs (`alice`, `bob`, `carol`, `PROBE`, `PROBE_SINK`, `bank_reserve`).

Arrêt :

```bash
docker compose -f compose.dev.yaml down
docker compose -f compose.dev.yaml -f observability/docker-compose.observability.yml up -d --build
# ou : make dev-down
```

### 3. Variables d'environnement utiles (backend)

| Variable | Rôle | Défaut dev |
| --- | --- | --- |
| `CORS_ORIGINS` | Origines autorisées pour les appels navigateur (liste JSON) | `["http://localhost:3000"]` |
| `SECRETS_DIR` | Dossier des secrets | `/run/secrets` dans le conteneur |

## Démarrage — frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # adapter NEXT_PUBLIC_API_BASE_URL si besoin
npm run dev
```

Le frontend démarre sur `http://localhost:3000` (ou le port suivant disponible si 3000 est occupé). `NEXT_PUBLIC_API_BASE_URL` doit pointer vers `payment-api` : en local, `http://localhost:8001/api/payments`.

## Tests

### Backend (pytest, Docker requis pour testcontainers)

```bash
uv sync --all-packages
uv run pytest                        # tous les services
make test-payment                    # payment-api seulement
make test-common                     # libs/common seulement
```

Sous Windows avec Docker Desktop, Ryuk (testcontainers) est désactivé via `TESTCONTAINERS_RYUK_DISABLED=true` (déjà configuré dans `conftest.py`).

### Frontend (Vitest)

```bash
cd frontend
npm run test
```

Couvre `lib/crypto.ts` : import de clé publique (PEM valide/invalide), round-trip de chiffrement, BIC optionnel, noms Unicode, non-déterminisme du chiffrement, détection d'altération (tag GCM).

### Lint

```bash
make lint          # ruff check + ruff format --check (Python)
cd frontend && npm run lint   # ESLint
```

## Vérification manuelle (smoke test de connectivité)

Avec le backend et le frontend lancés :

1. **Clé publique (endpoint non authentifié)** :
   ```bash
   curl http://localhost:8001/api/payments/public-key
   ```
   Doit renvoyer `200` avec `{public_key, key_id, algorithm, content_encryption}`.

2. **Formulaire de virement** : ouvrir `http://localhost:3000/payment`, remplir IBAN/bénéficiaire/montant, soumettre.
   - L'appel à `/api/payments/public-key` doit réussir (200).
   - L'appel à `/api/payments/transfer` renvoie actuellement **401** : c'est le comportement attendu tant que l'authentification Keycloak n'est pas branchée côté frontend (route protégée par `HTTPBearer`). Ce n'est pas une anomalie à corriger avant la branche d'authentification dédiée.

3. **Export OpenAPI à jour** :
   ```bash
   make check-openapi
   ```
   Échoue si `contracts/openapi-payment.json` diverge de ce que `payment-api` exporte réellement.

## Pièges connus

Voir `.claude/CLAUDE.md` §13 pour la liste complète (émetteur Keycloak public vs interne, `EventSource` sans headers, deadlocks sur verrouillage de comptes, RAM sous Docker Desktop/WSL2, etc.). Deux déjà rencontrés en local :

- **CORS** : si le frontend obtient une erreur CORS sur `public-key`/`transfer`, vérifier que `CORSMiddleware` est bien configuré dans `payment_api/main.py` avec l'origine du frontend dans `cors_origins`/`CORS_ORIGINS`.
- **`ERR_CONNECTION_REFUSED`** : le conteneur `payment-api` n'est pas démarré ou a crashé — vérifier `docker compose -f compose.dev.yaml ps` et les logs (`logs payment-api --tail=100`) avant de suspecter le frontend.
