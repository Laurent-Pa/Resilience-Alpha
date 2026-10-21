# Resilience-Alpha

Projet EPSI Workshop M2 Bac+5 — plateforme de paiement fictive et conteneurisée, avec remédiation autonome face à une attaque simulée.

Ce dépôt couvre le **pilier développement** (payment-api, frontend, lib partagée). L'infra (Compose complet, Ansible, Prometheus/Grafana/Loki), l'IA (ml-detector, rag-assistant), la cyber (WAF, Vault, SIEM) et la gouvernance sont portées par d'autres membres de l'équipe. Voir `.claude/CLAUDE.md` pour le handoff complet (architecture, décisions, contrats, pièges connus).

## Arborescence

```
resilience-alpha/
├── compose.dev.yaml
├── contracts
│   └── openapi-payment.json
├── DEPLOIEMENT-PROD.md
├── frontend
│   ├── AGENTS.md
│   ├── app
│   │   ├── admin
│   │   ├── callback
│   │   ├── login
│   │   ├── payment
│   │   │   └── page.tsx
│   │   ├── favicon.ico
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── payment
│   │       └── page.tsx
│   ├── components
│   │   ├── admin
│   │   └── public
│   ├── Dockerfile
│   ├── eslint.config.mjs
│   ├── lib
│   │   ├── crypto.test.ts
│   │   ├── crypto.ts
│   │   ├── format.ts
│   │   └── payments.ts
│   ├── next.config.ts
│   ├── package.json
│   ├── package-lock.json
│   ├── README.md
│   └── tsconfig.json
├── grafana
│   └── provisioning
│       └── datasources
│           └── datasources.yml
├── keycloak
│   ├── certs
│   │   ├── keycloak.crt
│   │   ├── keycloak.key
│   │   └── keycloak.pfx
│   └── realm-resilience.json
├── libs
│   └── common
│       ├── pyproject.toml
│       ├── src
│       │   └── resilience_common
│       │       ├── auth.py
│       │       ├── crypto.py
│       │       ├── health.py
│       │       ├── hmac.py
│       │       ├── __init__.py
│       │       ├── logging.py
│       │       ├── metrics.py
│       │       ├── settings.py
│       │       └── testing.py
│       └── tests
│           ├── test_auth.py
│           ├── test_hmac.py
│           └── test_observability.py
├── loki
│   └── loki-config.yml
├── Makefile
├── prometheus
│   └── prometheus.yml
├── pyproject.toml
├── README.md
├── services
│   ├── payment-api
│   │   ├── alembic.ini
│   │   ├── Dockerfile
│   │   ├── migrations
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions
│   │   │       └── 0001_initial.py
│   │   ├── pyproject.toml
│   │   ├── src
│   │   │   └── payment_api
│   │   │       ├── api
│   │   │       │   ├── accounts.py
│   │   │       │   ├── admin.py
│   │   │       │   ├── __init__.py
│   │   │       │   └── payments.py
│   │   │       ├── bootstrap.py
│   │   │       ├── crypto.py
│   │   │       ├── db.py
│   │   │       ├── domain
│   │   │       │   ├── bic.py
│   │   │       │   ├── iban.py
│   │   │       │   ├── __init__.py
│   │   │       │   └── rules.py
│   │   │       ├── export_openapi.py
│   │   │       ├── __init__.py
│   │   │       ├── main.py
│   │   │       ├── models.py
│   │   │       ├── repo
│   │   │       │   ├── accounts.py
│   │   │       │   ├── __init__.py
│   │   │       │   ├── ledger.py
│   │   │       │   └── transactions.py
│   │   │       ├── schemas.py
│   │   │       ├── seed.py
│   │   │       ├── service.py
│   │   │       └── settings.py
│   │   └── tests
│   │       ├── conftest.py
│   │       ├── test_crypto.py
│   │       ├── test_payments.py
│   │       └── test_rules.py
│   └── prober
│       ├── Dockerfile
│       ├── pyproject.toml
│       ├── src
│       │   └── prober
│       │       ├── __init__.py
│       │       ├── main.py
│       │       ├── probe.py
│       │       └── settings.py
│       └── tests
│           └── test_probe.py
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
├── detection/                      # détection ML d'anomalies (Isolation Forest) → alerte signée au moteur (voir detection/README.md)
├── scripts/
│   ├── flood.py                    # générateur de charge (attaque DoS contrôlée), modes get / transfer
│   └── fake_alert.py               # poste une alerte signée au moteur (secours / test)
├── docs/
│   └── prod-interface.md           # contrat code ↔ infra pour le compose de prod
├── services/
│   ├── payment-api/
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── alembic.ini
│   │   ├── migrations/
│   │   ├── src/payment_api/
│   │   │   ├── main.py             # create_app() — uvicorn --factory
│   │   │   ├── settings.py         # pydantic-settings, secrets lus depuis $SECRETS_DIR
│   │   │   ├── api/                # payments.py, accounts.py, admin.py
│   │   │   ├── domain/             # règles pures : rules.py, iban.py, bic.py
│   │   │   ├── repo/               # accounts.py, transactions.py, ledger.py
│   │   │   ├── service.py          # cas d'usage transactionnel (virement)
│   │   │   ├── crypto.py           # déchiffrement hybride RSA-OAEP + AES-GCM, HMAC IBAN
│   │   │   ├── models.py, db.py, schemas.py
│   │   │   ├── bootstrap.py        # migrations + seed au démarrage
│   │   │   ├── export_openapi.py
│   │   │   └── seed.py             # comptes fictifs, idempotent
│   │   └── tests/
│   ├── remediation-engine/         # machine d'états + executors fake/ansible (FakeExecutor par défaut)
│   └── prober/                     # preuve de reprise : un vrai virement toutes les 5 s via le WAF
│       ├── pyproject.toml
│       ├── Dockerfile
│       ├── src/prober/
│       │   ├── main.py              # serveur FastAPI : /metrics, /status
│       │   ├── probe.py             # boucle async : token → clé publique → virement 1 centime
│       │   └── settings.py
│       └── tests/
├── frontend/                       # app de paiement (Next.js), servie sous `/`
│   ├── app/
│   │   ├── page.tsx                 # accueil
│   │   └── payment/page.tsx         # formulaire de virement
│   ├── lib/
│   │   ├── crypto.ts                # chiffrement hybride RSA-OAEP + AES-GCM (contrat §7)
│   │   ├── crypto.test.ts           # tests Vitest
│   │   ├── payments.ts              # client API (clé publique, virement, retry sur decryption_failed)
│   │   └── format.ts                # formatage IBAN, formatage des montants en euros
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

`frontend-attack/` est abandonné : l'attaque est le script `scripts/flood.py` (voir `.claude/CLAUDE.md` §3 et §12 pour le plan). L'authentification Keycloak/OIDC côté frontend n'est pas encore implémentée : c'est la prochaine étape, sur une branche dédiée.

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
openssl rand -hex 32 > .secrets/webhook_hmac_key   # HMAC de POST /alerts : même valeur pour remediation-engine et detection
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out .secrets/rsa_private_key
openssl rand -hex 16 | tr -d '\n' > .secrets/grafana_admin_password
openssl rand -hex 32 > .secrets/prober_client_secret
openssl rand -hex 32 > .secrets/remediation_client_secret
openssl rand -base64 24 > .secrets/test_users_password
```

**Variante PowerShell** (Windows), à lancer depuis la racine du dépôt. Elle crée aussi les secrets Keycloak et le fichier `keycloak.env` :

```powershell
New-Item -ItemType Directory -Force .secrets | Out-Null
function New-Secret([int]$n, [switch]$Base64) {
  $b = New-Object byte[] $n
  [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  if ($Base64) { [Convert]::ToBase64String($b) } else { -join ($b | ForEach-Object { $_.ToString('x2') }) }
}
Set-Content .secrets/db_password               (New-Secret 24)          -NoNewline -Encoding ascii
Set-Content .secrets/iban_hmac_key             (New-Secret 32)          -NoNewline -Encoding ascii
Set-Content .secrets/webhook_hmac_key          (New-Secret 32)          -NoNewline -Encoding ascii
Set-Content .secrets/prober_client_secret      (New-Secret 32)          -NoNewline -Encoding ascii
Set-Content .secrets/remediation_client_secret (New-Secret 32)          -NoNewline -Encoding ascii
Set-Content .secrets/test_users_password       (New-Secret 12 -Base64)  -NoNewline -Encoding ascii

**Variante Bash**  à lancer depuis la racine du dépôt. Elle crée aussi les secrets Keycloak et le fichier `keycloak.env` :
```bash
cat > .secrets/keycloak.env <<EOF
KC_BOOTSTRAP_ADMIN_USERNAME=admin
KC_BOOTSTRAP_ADMIN_PASSWORD=ChangeMoi123!
PROBER_CLIENT_SECRET=$(cat .secrets/prober_client_secret | tr -d '[:space:]')
REMEDIATION_CLIENT_SECRET=$(cat .secrets/remediation_client_secret | tr -d '[:space:]')
TEST_USERS_PASSWORD=$(cat .secrets/test_users_password | tr -d '[:space:]')
EOF
```



# keycloak.env : admin de bootstrap + valeurs des placeholders ${...} du realm
@(
  "KC_BOOTSTRAP_ADMIN_USERNAME=admin"
  "KC_BOOTSTRAP_ADMIN_PASSWORD=ChangeMoi123!"
  "PROBER_CLIENT_SECRET=$((Get-Content .secrets/prober_client_secret).Trim())"
  "REMEDIATION_CLIENT_SECRET=$((Get-Content .secrets/remediation_client_secret).Trim())"
  "TEST_USERS_PASSWORD=$((Get-Content .secrets/test_users_password).Trim())"
) | Set-Content .secrets/keycloak.env -Encoding ascii

Get-ChildItem .secrets
```

La clé RSA se génère avec `openssl`, depuis Git Bash :

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out .secrets/rsa_private_key
```

- `iban_hmac_key` est **obligatoire** : sans lui, le démarrage est refusé.
- `rsa_private_key` est recommandé pour la démo/le dev continu : sans lui, une clé RSA éphémère est générée à chaque redémarrage, ce qui invalide la clé publique mise en cache côté frontend (le frontend et le prober s'en remettent via un retry sur `decryption_failed`, mais c'est à éviter en usage courant).
- **Ne jamais régénérer `iban_hmac_key` sur une base existante** : les comptes deviennent introuvables par IBAN.

Keycloak sert en HTTPS sur `:8443` ; générer son certificat auto-signé (dossier `keycloak/certs/`, gitignoré comme `.secrets/`) :

```bash
./keycloak/generate-keycloak-cert.sh
```

Le driver de logs `loki` (utilisé par `prober` et `frontend` dans `compose.dev.yaml`) nécessite un plugin Docker, à installer une fois par machine :

```bash
docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions
```

### 2. Lancer la stack (Postgres + payment-api + frontend + keycloak + prober + observabilité)

```bash
docker compose -f compose.dev.yaml up -d --build
```

Ou via le Makefile (hors Windows sans `make`, lancer la commande Docker directement) :

```bash
make dev-up
```

`payment-api` écoute en local sur `127.0.0.1:8001` (mappé vers le port interne `8000`). Au démarrage : migrations Alembic puis seed des comptes fictifs (`alice`, `bob`, `carol`, `PROBE`, `PROBE_SINK`, `bank_reserve`). Prometheus, Loki et Grafana sont des services de ce même `compose.dev.yaml`, pas une stack séparée.

Vérifier que tout est démarré :

```bash
docker compose -f compose.dev.yaml ps
docker compose -f compose.dev.yaml logs payment-api --tail=50
```

Changer le mot de passe admin Grafana (il n'est lu dans le secret qu'à la création du volume) :

```bash
docker exec grafana grafana cli admin reset-admin-password TestPassword123
```

Arrêt :

```bash
docker compose -f compose.dev.yaml down
# ou : make dev-down
```

### 3. Variables d'environnement utiles (backend)

| Variable       | Rôle                                                        | Défaut dev                       |
| -------------- | ----------------------------------------------------------- | -------------------------------- |
| `CORS_ORIGINS` | Origines autorisées pour les appels navigateur (liste JSON) | `["http://localhost:3000"]`      |
| `SECRETS_DIR`  | Dossier des secrets                                         | `/run/secrets` dans le conteneur |

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

## Métriques

Chaque service expose ses métriques au format Prometheus sur `GET /metrics` (port interne `8000`, scrapé par l'infra).

### Communes à tous les services (middleware `resilience_common.metrics`)

| Métrique | Type | Labels |
| --- | --- | --- |
| `http_requests_total` | Counter | `method`, `route`, `status` |
| `http_request_duration_seconds` | Histogram | `method`, `route` |

### `payment-api`

| Métrique | Type | Labels |
| --- | --- | --- |
| `payments_total` | Counter | `status` (`completed`, `replayed` ou le code d'erreur, ex. `insufficient_funds`) |
| `payment_duration_seconds` | Histogram | — |

### `prober`

| Métrique | Type | Labels |
| --- | --- | --- |
| `probe_success` | Gauge (0/1) | — |
| `probe_latency_seconds` | Histogram | — |
| `probe_failures_total` | Counter | `stage` (`token`, `key`, `payment`), initialisé à 0 au démarrage |

## Commandes utiles

### Prober

```powershell
# Les 60 derniers résultats de sonde (ok, stage, latency_ms)
Invoke-RestMethod http://localhost:8002/status

# Temps de détection : la sonde passe à 0 en moins de 10 s, puis repasse à 1 au redémarrage
docker compose -f compose.dev.yaml stop payment-api
docker compose -f compose.dev.yaml start payment-api
```

### Attaque, détection et remédiation (démo en dev, tout en simulation)

`compose.dev.yaml` démarre la chaîne complète avec `EXECUTOR=fake` et `VERIFIER=fake` : les actions
(`block_ip`, `recycle_service`, `kill_db_conns`) sont **simulées** et la reprise n'est pas prouvée par
le prober. La vraie remédiation (Ansible, WAF, vérification réelle) est branchée sur le lab, voir
[docs/prod-interface.md](docs/prod-interface.md).

```powershell
# Pile + observabilité (le secret .secrets/webhook_hmac_key doit exister)
docker compose -f compose.dev.yaml -f observability/docker-compose.observability.yml up -d

# Détection : collecter le trafic normal, entraîner, puis elle tourne en continu
# (procédure complète : detection/README.md)

# Attaque : en local il n'y a pas de WAF, on simule l'IP source avec --xff
.\.venv\Scripts\python.exe scripts/flood.py --mode transfer -c 300 -d 60 --xff 8.8.8.8

# Chaîne : détection → alerte signée → moteur (TRIAGED → EXECUTING → VERIFYING → RECOVERED)
docker logs --tail 20 resilience-alpha-detection-1
docker logs --tail 20 resilience-alpha-remediation-engine-1

# Secours sans attendre la détection : alerte signée à la main
$env:WEBHOOK_HMAC_SECRET = (Get-Content .secrets/webhook_hmac_key)
.\.venv\Scripts\python.exe scripts/fake_alert.py --url http://127.0.0.1:8003/alerts
```

### Base de données

```bash
# Comptes seedés (alice, bob, carol, PROBE, PROBE_SINK, bank_reserve)
docker compose -f compose.dev.yaml exec postgres psql -U payment_app -d resilience -c "SELECT owner_id, label, iban_masked, bic FROM payments.accounts ORDER BY label;"

# Soldes calculés (somme du ledger)
docker compose -f compose.dev.yaml exec postgres psql -U payment_app -d resilience -c "SELECT a.label, COALESCE(SUM(e.amount),0) AS balance FROM payments.accounts a LEFT JOIN payments.ledger_entries e ON e.account_id = a.id GROUP BY a.label ORDER BY a.label;"

# Derniers virements (ceux du prober s'accumulent : PROBE → PROBE_SINK)
docker compose -f compose.dev.yaml exec postgres psql -U payment_app -d resilience -c "SELECT created_at, amount, status, dst_iban_masked FROM payments.transactions ORDER BY created_at DESC LIMIT 10;"

# Session interactive (\dt payments.*, \d payments.accounts, etc.)
docker compose -f compose.dev.yaml exec postgres psql -U payment_app -d resilience
```

## Pièges connus

Voir `.claude/CLAUDE.md` §13 pour la liste complète (émetteur Keycloak public vs interne, `EventSource` sans headers, deadlocks sur verrouillage de comptes, RAM sous Docker Desktop/WSL2, etc.). Deux déjà rencontrés en local :

- **CORS** : si le frontend obtient une erreur CORS sur `public-key`/`transfer`, vérifier que `CORSMiddleware` est bien configuré dans `payment_api/main.py` avec l'origine du frontend dans `cors_origins`/`CORS_ORIGINS`.
- **`ERR_CONNECTION_REFUSED`** : le conteneur `payment-api` n'est pas démarré ou a crashé — vérifier `docker compose -f compose.dev.yaml ps` et les logs (`logs payment-api --tail=100`) avant de suspecter le frontend.
