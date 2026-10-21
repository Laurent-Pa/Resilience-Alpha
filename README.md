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
openssl rand -hex 32 | tr -d '\n' > .secrets/webhook_hmac_key
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

## Déploiement sur le PC Hôte (configuration de démo, proche de la prod)

`compose.dev.yaml` reste l'environnement de développement rapide. Cette section monte la plateforme **telle qu'elle sera présentée au jury** : un seul point d'entrée publié (le WAF, en HTTPS), tout le reste sur des réseaux Docker internes, actions de remédiation réelles. Références : [`docs/prod-interface.md`](docs/prod-interface.md) (contrat de chaque service), [`docs/infra-todo.md`](docs/infra-todo.md), [`DEPLOIEMENT-PROD.md`](DEPLOIEMENT-PROD.md).

```
Navigateur / PC Attaquant ──HTTPS :443──▶ proxy L4 Windows (hors Docker, ajoute l'IP réelle : PROXY protocol)
                                               └──▶ WAF (conteneur, publié sur 127.0.0.1:8443 uniquement)
                                                      ├─ /              → frontend (paiement + /admin)
                                                      ├─ /api/payments, /api/accounts, /api/admin → payment-api
                                                      ├─ /api/remediation/* → remediation-engine (préfixe retiré)
                                                      └─ /auth          → keycloak (HTTP interne)
Réseaux internes : postgres, vault, prometheus/loki/grafana/alertmanager, docker-socket-proxy
```

Avancement :

- [x] Étape 1 — Adresse publique et PKI de labo
- [x] Étape 2 — `compose.yaml` : services internes, sans port publié
- [x] Étape 3 — WAF (routage, en-têtes, TLS)
- [x] Étape 4 — Frontend et Keycloak en URL publiques
- [ ] Étape 5 — Observabilité et Alertmanager
- [ ] Étape 6 — Remédiation réelle (docker-socket-proxy + playbooks Ansible)
- [ ] Étape 7 — Vault
- [ ] Étape 8 — Détection, attaque depuis le PC Attaquant, recette

### Étape 1 — Adresse publique et PKI de labo

**Adresse publique (`PUBLIC_HOST`)**. C'est l'adresse que tapent le navigateur et le PC Attaquant ; elle fixe l'émetteur des jetons Keycloak, les URL du frontend et le certificat du WAF. Le jour de la démo : `192.168.137.1`, qui n'existe que lorsque le **point d'accès sans fil mobile** Windows est activé (Paramètres → Réseau et Internet → Point d'accès sans fil mobile). Sans point d'accès, utiliser l'IPv4 de la carte réseau du PC (`ipconfig`), **jamais `localhost`** : dans un conteneur, `localhost` désigne le conteneur lui-même.

```bash
cp .env.example .env          # puis ajuster PUBLIC_HOST si besoin
ipconfig                      # (PowerShell / cmd) vérifier que l'adresse existe bien sur le PC
```

**PKI de labo**. Une CA locale signe le certificat du WAF. On importe la CA une seule fois dans Windows (plus d'avertissement navigateur), et le prober et le moteur la reçoivent en `CA_BUNDLE` (vérification TLS réelle, jamais `verify=False`). Si `PUBLIC_HOST` change, relancer le script : seul le certificat du WAF est régénéré, la CA déjà importée reste valable.

```bash
bash scripts/gen-lab-pki.sh   # Git Bash ; crée certs/lab-ca.pem, certs/lab-ca.key, certs/waf.crt, certs/waf.key
```

Importer la CA dans le magasin de l'utilisateur Windows (PowerShell, depuis la racine du dépôt ; Windows demande confirmation) :

```powershell
Import-Certificate -FilePath .\certs\lab-ca.pem -CertStoreLocation Cert:\CurrentUser\Root
Get-ChildItem Cert:\CurrentUser\Root | Where-Object Subject -like "*Resilience-Alpha*"
```

Chrome et Edge utilisent ce magasin. Firefox a le sien : `about:config` → `security.enterprise_roots.enabled` = `true`.

- `certs/` est gitignoré. **`certs/lab-ca.key` ne quitte jamais le PC Hôte** : qui la possède peut signer un certificat accepté par tous les postes qui ont importé la CA.
- Le PC Attaquant peut recevoir `certs/lab-ca.pem` (jamais la clé) pour `scripts/flood.py --ca lab-ca.pem` ; à défaut, `--insecure`.

### Étape 2 — `compose.yaml` : services internes, sans port publié

`compose.yaml` (lu par défaut par `docker compose`, sans `-f`) est un **projet distinct** (`name: resilience-host`) : conteneurs `ra-*`, volume Postgres et réseaux séparés de ceux de `compose.dev.yaml`. Arrêter la pile de dev avant, la RAM du PC Hôte ne suffit pas pour les deux.

| Réseau | Type | Qui |
| --- | --- | --- |
| `backend` | interne (aucun accès sortant) | postgres, keycloak, payment-api, prober, remediation-engine |
| `edge` | bridge | ce que le WAF servira (keycloak, payment-api, moteur) + prober et moteur, qui joignent le WAF par l'adresse publique |

- **Aucun port publié** à cette étape : rien n'est joignable depuis le navigateur avant le WAF (étape 3). Postgres n'est que sur `backend`.
- **Keycloak** : `start` (mode prod), HTTP interne derrière le WAF (`KC_PROXY_HEADERS=xforwarded`), émetteur figé à `https://${PUBLIC_HOST}/auth`. Base H2 interne au conteneur : le realm est réimporté au démarrage (choix assumé pour la RAM ; un Postgres dédié serait la cible industrielle).
- **Services** : émetteur OIDC public, JWKS et jetons en interne, `CA_BUNDLE=/certs/lab-ca.pem` pour le prober et le moteur, moteur en `EXECUTOR=fake` jusqu'à l'étape 6.

**Secret manquant** : `webhook_hmac_key` (HMAC partagé entre `detection` et le moteur). Si `.secrets/webhook_hmac_key` est un **dossier**, c'est Docker qui l'a créé en montant un fichier absent : le supprimer d'abord.

```bash
rmdir .secrets/webhook_hmac_key 2>/dev/null
openssl rand -hex 32 | tr -d '\n' > .secrets/webhook_hmac_key
```

Démarrage :

```bash
docker compose -f compose.dev.yaml down     # libérer la RAM
docker compose up -d --build
docker compose ps                           # tout en "healthy", colonne PORTS vide
```

Vérifications (à faire avant l'étape 3, elles valident le câblage interne) :

```bash
# 1. payment-api prêt (migrations 0001 + 0002 jouées sur une base neuve, seed fait)
docker compose exec payment-api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready').read().decode())"

# 2. Piège iss : l'émetteur annoncé EN INTERNE doit être l'adresse PUBLIQUE
docker compose exec prober python -c "import urllib.request, json; print(json.load(urllib.request.urlopen('http://keycloak:8080/auth/realms/resilience/.well-known/openid-configuration'))['issuer'])"

# 3. Sonde : jeton OK, échec attendu à l'étape "key" (ConnectError) tant que le WAF n'existe pas
docker compose logs prober --tail=3
```

Résultats attendus : (1) `{"status":"ok","checks":{"db":"ok"}}` ; (2) `https://<PUBLIC_HOST>/auth/realms/resilience` ; (3) des `probe.result` avec `"stage": "key"` et `"error": "ConnectError"`. Un échec au stage `token` signalerait un problème Keycloak ou de `prober_client_secret`.

### Étape 3 — WAF (routage, en-têtes, TLS)

Service `waf` : image `owasp/modsecurity-crs` (nginx + ModSecurity v3 + OWASP CRS), **seul conteneur publié**, et seulement sur `127.0.0.1:8443` (nginx non-root). Le 443 public est tenu par le proxy L4 Windows décrit plus bas. Configuration : [`waf/nginx/default.conf.template`](waf/nginx/default.conf.template).

| Chemin public | Vers | Remarque |
| --- | --- | --- |
| `/api/payments`, `/api/accounts`, `/api/admin` | payment-api:8000 | sans réécriture |
| `/api/remediation/*` | remediation-engine:8000 | préfixe retiré ; `/events` (SSE) sans tampon ni inspection |
| `/auth` | keycloak:8080 | `/auth/admin` refusé (403) : console d'administration non exposée |
| `/` | frontend:3000 | `502` tant que le frontend n'est pas déployé (étape 4) |
| `/api/remediation/alerts`, `/metrics`, `/health` | — | `404` : entrées internes jamais publiées |

- **En-têtes posés par le WAF** : `X-Forwarded-For` / `X-Real-IP` = l'IP de connexion, **en écrasant** ce que le client envoie (sinon un attaquant ferait bloquer l'IP de son choix par `block_ip`) ; `X-Request-ID` (devient le `trace_id` des services, renvoyé aussi au client) ; `X-Forwarded-Proto/Host/Port` pour Keycloak.
- **Journal d'accès JSON** sur stdout, avec `src_ip` et `trace_id`. Le chemin est journalisé **sans la query string** (le jeton du flux SSE y passe).
- **Résolution DNS à la requête** : le WAF démarre même si un service est arrêté, et suit un conteneur recréé par la remédiation.
- **ModSecurity en `DetectionOnly`** à cette étape : les règles CRS journalisent sans bloquer, le temps de vérifier l'absence de faux positifs. Passage en `On` une fois les parcours réels validés (étape 4).
- **Exclusions CRS** : [`waf/modsecurity/RESPONSE-999-EXCLUSION-RULES-AFTER-CRS.conf`](waf/modsecurity/RESPONSE-999-EXCLUSION-RULES-AFTER-CRS.conf), une justification par règle. À ce jour : `920350` (Host = adresse IP), inévitable puisque le sujet impose `192.168.137.1` sans nom DNS.
- **Deux journaux dans `docker compose logs waf`** : l'accès nginx (`"service":"waf"`, une ligne par requête) et l'audit ModSecurity (`"transaction":...`, seulement quand une règle se déclenche).

#### Proxy L4 Windows : conserver l'IP réelle du client

Décision complète (constat, alternatives écartées, conséquences, arguments pour le jury) : [`docs/decision-proxy-l4-ip-source.md`](docs/decision-proxy-l4-ip-source.md).

**Problème constaté** : Docker Desktop remplace l'IP du client par la passerelle du réseau Docker (`172.x`) sur tout port publié ; un téléphone du réseau apparaissait en `172.19.0.1`. Ni le mode « host networking » de Docker Desktop ni le réseau WSL « mirrored » n'y changent rien. Sans IP réelle, la détection par IP et `block_ip` ne peuvent pas viser le PC Attaquant (et bloqueraient la passerelle, donc tout le monde).

**Solution** : nginx pour Windows, lancé **sur l'hôte**, écoute le 443, ne déchiffre rien et relaie le flux TLS vers `127.0.0.1:8443` en le précédant d'un en-tête *PROXY protocol* qui porte l'IP d'origine ([`edge/nginx.conf`](edge/nginx.conf)). Le WAF l'exige (`listen ... proxy_protocol`) et en fait son `$remote_addr` (`real_ip_header proxy_protocol`) : journal, ModSecurity, `X-Forwarded-For` et `block_ip` voient l'IP réelle. Une connexion directe au WAF sans cet en-tête est refusée, et le port n'est publié que sur la boucle locale : impossible de contourner le relais depuis le réseau.

Installation (une fois) : télécharger sur [nginx.org/en/download.html](https://nginx.org/en/download.html) le zip **Stable version** pour Windows et le décompresser de façon à obtenir `tools\nginx\nginx.exe` (dossier `tools/` gitignoré). Vérifier que le module stream est présent :

```powershell
.\tools\nginx\nginx.exe -V 2>&1 | Select-String -- "--with-stream"
```

Pilotage (PowerShell, à la racine ; `-ExecutionPolicy Bypass` si l'exécution de scripts est désactivée) :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\edge-proxy.ps1 start    # test de la conf puis démarrage
powershell -ExecutionPolicy Bypass -File .\scripts\edge-proxy.ps1 status
powershell -ExecutionPolicy Bypass -File .\scripts\edge-proxy.ps1 stop
```

- Au premier démarrage, le pare-feu Windows demande d'autoriser `nginx.exe` : cocher les réseaux **privés et publics** (le point d'accès mobile peut être classé public).
- **Le jour J, démarrer le relais en plus de `docker compose up -d`** : sans lui, plus rien n'est joignable sur le 443.
- Limite connue : nginx pour Windows plafonne à ~1024 connexions simultanées. Sous un flood massif, le relais peut saturer avant le WAF ; le blocage d'IP au WAF libère les connexions de l'attaquant au fil de l'eau.
- Journaux du relais : `edge\logs\error.log` (gitignoré).

Port 443 occupé : `netstat -ano | findstr :443` pour trouver le programme.

```bash
docker compose up -d
docker compose ps waf                      # "healthy", PORTS 127.0.0.1:8443->8443/tcp
PUBLIC_HOST=$(grep -E '^PUBLIC_HOST=' .env | cut -d= -f2 | tr -d '\r')
```

Vérifications (Git Bash) :

```bash
# 1. payment-api via le WAF, certificat vérifié avec la CA de labo
curl --cacert certs/lab-ca.pem https://$PUBLIC_HOST/api/payments/public-key

# 2. Keycloak via le WAF : même émetteur qu'en interne
curl -s --cacert certs/lab-ca.pem https://$PUBLIC_HOST/auth/realms/resilience/.well-known/openid-configuration | grep -o '"issuer":"[^"]*"'

# 3. La sonde passe désormais de bout en bout : "ok": true, "stage": "payment"
docker compose logs prober --tail=3

# 4. Entrées internes non publiées : 404 puis 403
curl -s -o /dev/null -w "%{http_code}\n" --cacert certs/lab-ca.pem https://$PUBLIC_HOST/api/remediation/alerts
curl -s -o /dev/null -w "%{http_code}\n" --cacert certs/lab-ca.pem https://$PUBLIC_HOST/auth/admin/

# 5. ModSecurity détecte (sans bloquer) une injection XSS : 200, puis une trace de règle CRS
curl -s -o /dev/null -w "%{http_code}\n" --cacert certs/lab-ca.pem "https://$PUBLIC_HOST/api/payments/public-key?q=%3Cscript%3Ealert(1)%3C/script%3E"
docker compose logs waf | grep -i "modsecurity" | tail -2
```

Si `curl` refuse `--cacert` (curl de Windows, moteur TLS « schannel »), remplacer `--cacert certs/lab-ca.pem` par `--ssl-no-revoke` (sans chemin de certificat) : schannel s'appuie sur le magasin Windows où la CA a été importée.

6. **Navigateur** : `https://<PUBLIC_HOST>/auth/realms/resilience/account` doit afficher la page de compte Keycloak **avec le cadenas, sans avertissement** (CA importée) et sans jamais rediriger vers `localhost` ou `http://`.

7. **IP source réelle (indispensable pour la démo)** : depuis un autre appareil du même réseau (téléphone en Wi-Fi), ouvrir `https://<PUBLIC_HOST>/api/payments/public-key` (accepter l'avertissement de certificat sur le téléphone), puis :

```bash
docker compose logs waf | grep '"service":"waf"' | grep public-key | tail -3
```

Sur iPhone, Safari affiche « Ce site n'est pas sûr » (la CA de labo n'est pas installée) : « Afficher les détails » → « visiter ce site web ». Tant que l'avertissement n'est pas franchi, aucune requête HTTP n'est envoyée, donc rien dans le journal. `src_ip` doit être l'IP **du téléphone** (`192.168.x.y` du réseau local). Une adresse en `172.x` ou `192.168.65.x` signifie que la requête n'est pas passée par le relais Windows (relais arrêté, ou port publié autrement que sur `127.0.0.1`).

**Figer l'image** une fois l'étape validée (le tag `nginx-alpine` est roulant) :

```bash
docker image inspect owasp/modsecurity-crs:nginx-alpine --format '{{index .RepoDigests 0}}'
```

puis remplacer `image:` du service `waf` par la valeur obtenue (`owasp/modsecurity-crs@sha256:...`).

Résultat validé le 21/10 : sonde en `201` de bout en bout via relais + WAF ; un iPhone du réseau journalisé avec son IP réelle (`192.168.1.61`) ; le PC Hôte lui-même apparaît sous sa propre IP (`192.168.1.156`), comme la sonde (elle sort de Docker et revient par l'adresse publique). Conséquence pour l'étape 6 : `block_ip` doit refuser l'IP du PC Hôte.

### Étape 4 — Frontend et Keycloak en URL publiques

**Frontend** (service `frontend`, réseau `edge`, aucun port) : servi par le WAF sous `/` (paiement) et `/admin` (back-office). Les variables `NEXT_PUBLIC_*` sont **figées dans le bundle au build** :

| Argument de build | Valeur | Pourquoi |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `/api/payments` | relatif : même origine que le WAF, pas de CORS |
| `NEXT_PUBLIC_ADMIN_API_BASE_URL` | `/api/admin` | idem |
| `NEXT_PUBLIC_OIDC_AUTHORITY` | `https://${PUBLIC_HOST}/auth/realms/resilience` | émetteur public, identique à `KC_HOSTNAME` |
| `NEXT_PUBLIC_ADMIN_OIDC_CLIENT_ID` | `web-ops` | client du back-office (rôle `ops`) |

Tous les arguments doivent être fournis : sinon le Dockerfile pose une chaîne vide, qui ne déclenche pas les valeurs par défaut du code (`??`). **Changer `PUBLIC_HOST` impose de reconstruire le frontend** (`docker compose build frontend`).

**Keycloak** : les `redirectUris` / `rootUrl` des clients `web-pay` et `web-ops` utilisent `https://${PUBLIC_HOST:192.168.137.1}` dans [`keycloak/realm-resilience.json`](keycloak/realm-resilience.json), résolu à l'import depuis la variable `PUBLIC_HOST` du conteneur (valeur par défaut `192.168.137.1`, donc `compose.dev.yaml` est inchangé). Le back-office est sous `/admin` (l'ancien chemin `/ops` et `localhost:5174` du realm ne correspondaient à aucune application). Le realm n'est importé que s'il n'existe pas : comme sa base H2 vit dans le conteneur, il faut **recréer** Keycloak après toute modification du realm (`docker compose up -d --force-recreate keycloak`).

```bash
docker compose up -d --build              # construit le frontend, recrée Keycloak (nouvelle variable)
docker compose ps                         # tout "healthy"
cat .secrets/test_users_password; echo    # mot de passe des comptes de test
```

**Recette des parcours réels**, ModSecurity encore en `DetectionOnly` (navigateur du PC, `https://<PUBLIC_HOST>/`) :

1. Paiement : se connecter avec `alice` → virement vers `bob` → confirmation `201`. IBAN de `bob` : `docker compose exec payment-api python -c "from payment_api.seed import seed_iban; print(seed_iban('bob'))"`.
2. Back-office : `https://<PUBLIC_HOST>/admin` → connexion `operator` → liste des paiements (bascule « opérations de la sonde ») → onglet Monitoring (taux de réussite de la sonde).
3. Déconnexion des deux côtés : retour sur la page de connexion, jamais vers `localhost` ni `http://`.

Puis relever les règles CRS déclenchées **par ces parcours** (journal d'audit ModSecurity des 15 dernières minutes) :

```bash
docker compose logs --since 15m waf | grep '"transaction"' | grep -o '"ruleId":"[0-9]*"' | sort | uniq -c
```

`949110` / `980170` sont les règles d'évaluation du score ; les `941xxx` viennent du test XSS de l'étape 3 s'il a été rejoué. **Toute autre règle sur un parcours légitime est un faux positif** à analyser avant le passage en `On` (exclusion justifiée dans `waf/modsecurity/RESPONSE-999-EXCLUSION-RULES-AFTER-CRS.conf`).

**Passage de ModSecurity en blocage** : dans `compose.yaml`, service `waf`, `MODSEC_RULE_ENGINE: "On"`, puis `docker compose up -d waf` ; rejouer les parcours 1 à 3 et le test XSS de l'étape 3, qui doit maintenant répondre `403`.

## Pièges connus

Voir `.claude/CLAUDE.md` §13 pour la liste complète (émetteur Keycloak public vs interne, `EventSource` sans headers, deadlocks sur verrouillage de comptes, RAM sous Docker Desktop/WSL2, etc.). Deux déjà rencontrés en local :

- **CORS** : si le frontend obtient une erreur CORS sur `public-key`/`transfer`, vérifier que `CORSMiddleware` est bien configuré dans `payment_api/main.py` avec l'origine du frontend dans `cors_origins`/`CORS_ORIGINS`.
- **`ERR_CONNECTION_REFUSED`** : le conteneur `payment-api` n'est pas démarré ou a crashé — vérifier `docker compose -f compose.dev.yaml ps` et les logs (`logs payment-api --tail=100`) avant de suspecter le frontend.
