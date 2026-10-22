# HANDOFF — PROJECT RESILIENCE-ALPHA — Pilier Développement

Document de reprise de contexte pour Claude Code. Il décrit **le périmètre code uniquement**. L'infra (Compose/Kubernetes, Ansible, Prometheus/Grafana/Loki), l'IA (ml-detector, rag-assistant), la cyber (WAF, Vault, SIEM, Red Team) et la gouvernance sont portées par d'autres membres. Seules leurs **interfaces** avec le code sont décrites ici.

---

## 1. Contexte

Workshop EPSI Bac+5, sprint de 4 jours (lundi 19 → jeudi 22 octobre 2026, gel du code jeudi 17 h, jury vendredi).

**Sujet.** Une plateforme de paiement **fictive** et conteneurisée subit une attaque lancée depuis un second PC (le PC Attaquant). Le système doit, **sans intervention humaine** :

1. collecter les événements ;
2. détecter l'anomalie (ML) ;
3. décider d'une remédiation ;
4. l'exécuter ;
5. prouver que le service est rétabli, notamment par **une nouvelle transaction réussie** et des **données cohérentes**.

Un conteneur redémarré ne vaut pas preuve.

**Barème déterminant.** La démo de remédiation autonome compte pour 5 points sur 20. Toute intervention humaine pendant le live donne 0/5.

**Contraintes imposées par le sujet :**

- services en Node.js, Python/FastAPI ou Go → **choix : Python/FastAPI** ;
- dashboard de supervision en **React + Tailwind** ;
- stack d'observabilité : **Prometheus** (métriques), **Grafana** (visualisation), **Loki** (centralisation des journaux) ;
- microservices obligatoires : base de données, API métier, service d'authentification, frontal web ;
- moteur de remédiation, plus une interface de supervision montrant les composants, les événements, les alertes et l'avancement de la reprise ;
- aucune donnée bancaire réelle ; aucun secret en clair dans le dépôt ;
- dépôt livré avec un README de déploiement et de vérification, la documentation d'API (OpenAPI) et des tests.

**Réseau.** PC Hôte en `192.168.137.1` (point d'accès Windows `RESILIENCE-G<n>`). **Seul le WAF est publié** ; tout le reste circule sur des réseaux Docker internes. Le PC Hôte tourne sous Windows avec Docker Desktop et WSL2 : la RAM est contrainte.

---

## 2. Décisions d'architecture (figées)

1. **Monorepo**, avec un **workspace uv** pour le Python (un `pyproject.toml` par service, un `uv.lock` commun) et un **workspace pnpm** pour le front. **(21/10 : uv n'est requis que côté dev pour maintenir `uv.lock` ; la prod n'a besoin que de Docker — uv est embarqué dans les images, jamais installé sur l'hôte. Voir §4.)**
2. **Authentification = Keycloak**, configuré par un export de realm versionné. **Aucun service d'auth maison.**
3. **Preuve de reprise** = un `prober` qui exécute une vraie transaction toutes les 5 s **en passant par le WAF**, et un endpoint `/api/admin/ledger/check` qui vérifie l'invariant comptable.
4. **Paiements idempotents** (header `Idempotency-Key` obligatoire) et **ledger en partie double**, montants en **euros décimaux exacts** : `NUMERIC(12,2)` en base, `Decimal` en Python, chaîne `"50.05"` dans l'API (jamais de float). Modifié le 20/10 (auparavant : centimes entiers).
5. **Moteur de remédiation** = machine d'états persistée. Les actions passent par une interface `Executor` : `FakeExecutor` pour le développement et les tests, `AnsibleExecutor` (via ansible-runner, playbooks fournis par l'infra) pour le réel. Les actions sont limitées à une liste fermée, avec des paramètres validés.
6. **Le moteur n'accède jamais à `docker.sock` directement.** Les playbooks passent par un `docker-socket-proxy` (géré par l'infra).
7. **Les contrats d'abord** : les OpenAPI et JSON Schemas dans `contracts/` sont la source de vérité. Les types TypeScript en sont **générés**, jamais écrits à la main.
8. **Le dashboard ops reçoit les événements en SSE** depuis le moteur. Le navigateur n'accède jamais directement à Prometheus.
9. **Deux niveaux de supervision, complémentaires** (ajout du 19/10) :
   - `web-ops` (React, dev) : la vue **démo et remédiation** (SLI du prober, timeline des incidents, MTTD/MTTR) ;
   - **Grafana** (infra) : la vue **technique**, sur Prometheus (scrape des `/metrics`) et Loki (logs JSON stdout). Le code n'y contribue que par des métriques et des logs conformes au §5 ; dashboards, scrape et collecte sont portés par l'infra.
10. **Un compte bancaire par personne.** Le compte débité se déduit du jeton ; aucun identifiant de compte source n'est envoyé (ajout du 19/10).
11. **Coordonnées bancaires chiffrées de bout en bout.** Le bénéficiaire (IBAN, BIC, nom) est chiffré par le navigateur (RSA-OAEP + AES-GCM) ; l'IBAN n'est jamais stocké ni journalisé en clair (HMAC + forme masquée). Voir §7 (ajout du 19/10).
12. **Routes métier sous `/api`**, sondes techniques (`/health/*`, `/metrics`) à la racine (ajout du 19/10).
13. **Second facteur facial pour le rôle `ops`** (consigne additionnelle 1, ajout du 21/10) : étape caméra **dans Keycloak**, entre l'identifiant et le mot de passe (authenticator Java `keycloak/face-authenticator`, flux `browser-face`), décision par le service `face-auth`. Aucun jeton n'est émis sans visage reconnu : rien à vérifier côté API. Voir §7 bis.

---

## 3. Arborescence cible

```
resilience-alpha/
├── HANDOFF.md
├── README.md
├── Makefile                       # cibles dev : sync, test, lint, export-openapi, gen-types, seed
├── pyproject.toml                 # racine du workspace uv (aucun code)
├── uv.lock
├── contracts/
│   ├── openapi-payment.json       # exporté depuis payment-api
│   ├── openapi-remediation.json   # exporté depuis remediation-engine
│   ├── alert.schema.json          # format d'entrée de POST /alerts
│   └── event.schema.json          # format des événements SSE
├── keycloak/
│   ├── realm-resilience.json      # realm importé au démarrage (--import-realm), flux browser-face
│   ├── Dockerfile                 # image Keycloak + authenticator facial (build Maven multi-stage)
│   └── face-authenticator/        # SPI Java : étape caméra des ops (FaceAuthenticator, face-auth.ftl)
├── libs/
│   └── common/                    # package resilience-common
│       ├── pyproject.toml
│       └── src/resilience_common/
│           ├── logging.py         # structlog JSON + middleware X-Request-ID → trace_id
│           ├── metrics.py         # middleware http_requests_total, _by_source{src_ip}, http_request_duration_seconds + /metrics
│           ├── health.py          # router /health/live, /health/ready (checks injectés)
│           ├── auth.py            # vérif JWT Keycloak (JWKS en cache) + require_role()
│           ├── hmac.py            # signature et vérification des webhooks
│           └── settings.py        # pydantic-settings, secrets lus depuis fichiers /run/secrets/*
├── services/
│   ├── payment-api/
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── alembic.ini
│   │   ├── migrations/
│   │   ├── src/payment_api/
│   │   │   ├── main.py            # create_app() (uvicorn --factory)
│   │   │   ├── api/               # payments.py, accounts.py, admin.py
│   │   │   ├── domain/            # règles pures, sans I/O : rules.py, iban.py, bic.py
│   │   │   ├── repo/              # requêtes SQLAlchemy : accounts, transactions, ledger
│   │   │   ├── service.py         # cas d'usage transactionnel (virement)
│   │   │   ├── crypto.py          # déchiffrement hybride, HMAC IBAN (seal() : resilience_common.crypto)
│   │   │   ├── models.py, db.py, schemas.py, settings.py
│   │   │   ├── bootstrap.py       # migrations + seed au démarrage
│   │   │   ├── export_openapi.py
│   │   │   └── seed.py            # comptes fictifs, idempotent
│   │   └── tests/
│   ├── face-auth/                 # reconnaissance faciale (OpenCV YuNet + SFace), §7 bis
│   │   ├── Dockerfile             # modèles ONNX téléchargés au build (sha256 figé)
│   │   ├── src/face_auth/         # engine, lockout, crypto, store, service, api/{internal,admin}, enroll (CLI)
│   │   └── tests/
│   ├── prober/
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   ├── src/prober/
│   │   └── tests/
│   └── remediation-engine/
│       ├── pyproject.toml
│       ├── Dockerfile
│       ├── playbook_map.yaml
│       ├── migrations/
│       ├── src/remediation_engine/
│       │   ├── main.py
│       │   ├── api/               # alerts.py, incidents.py, events.py
│       │   ├── core/              # models, classifier, policy, state_machine, orchestrator, verifier
│       │   ├── executors/         # base.py, fake.py, ansible.py
│       │   ├── store.py
│       │   └── bus.py
│       └── tests/
├── frontend/                      # app de paiement (Next.js), servie sous `/`
│   ├── app/                       # App Router : page.tsx, layout.tsx, payment/
│   ├── lib/                       # crypto.ts, payments.ts, format.ts — types écrits à la main
│   ├── Dockerfile
│   └── package.json
├── scripts/
│   └── flood.py                   # générateur de charge (attaque DoS contrôlée) : modes get / transfer
└── detection/                     # service ML d'anomalies (pilier IA, standalone pip, Isolation Forest)
    ├── collect.py, train.py, detect.py   # collecte normal → modèle → alerte HMAC conforme alert.schema.json
    ├── config.py, prom.py, signing.py
    └── Dockerfile
```

`services/ml-detector` et `services/rag-assistant` appartiennent au pilier IA. Ils seront ajoutés au même workspace uv par leur propriétaire.
**Note (19/10) :** l'arborescence `web/` du plan initial (workspace pnpm, `@ra/api-client`, `@ra/ui`, `pay`/`ops` en Vite) n'a pas été retenue. L'app de paiement existe déjà en Next.js dans `frontend/`. La seconde app (déclenchement d'attaque) devait aller dans un dossier séparé à la racine. **Mise à jour (21/10) :** `frontend-attack/` abandonné — l'attaque est finalement un script CLI `scripts/flood.py` (générateur de charge, modes `get`/`transfer`), lancé depuis le PC Attaquant ; une app front n'apporte rien pour déclencher la charge.

---

## 4. Stack et dépendances

**Python 3.12 :**

| Projet             | Dépendances                                                                                                                 |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| resilience-common  | fastapi, structlog, prometheus-client, pyjwt[crypto], httpx, pydantic-settings                                              |
| payment-api        | resilience-common, fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, cryptography                          |
| prober             | resilience-common, httpx                                                                                                    |
| remediation-engine | resilience-common, fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, ansible-runner, pyyaml, sse-starlette |
| dev (racine)       | pytest, pytest-asyncio, testcontainers[postgres], ruff, mypy                                                                |

**Front (`frontend/`, Next.js** Next.js 16 (App Router), React 19, TypeScript, Tailwind v4 (`@tailwindcss/turbopack`). Types du contrat de paiement écrits à la main, pas générés depuis `contracts/openapi-payment.json`. Authentification Keycloak:  `oidc-client-ts`. La seconde app front (`frontend-attack/`) suivra la même stack.

**Initialisation :**

```bash
# Python
uv init --lib --name resilience-common libs/common
for s in payment-api prober remediation-engine; do uv init --package --app services/$s; done
# ajouter ensuite resilience-common à chaque service ([tool.uv.sources] resilience-common = { workspace = true })

# Front
# Front — app de paiement (déjà initialisée dans frontend/)
cd frontend && npx create-next-app@latest .   # TypeScript, Tailwind, App Router

# Front — app de déclenchement d'attaque simulée (à créer, structure à confirmer)
# cd frontend-attack && npx create-next-app@latest .
```

**Mise en place — qui a besoin d'uv, où.** uv n'est **jamais** installé sur la machine de prod : il est **embarqué dans les images** (`COPY --from=ghcr.io/astral-sh/uv`). Il n'est requis que côté **dev**, pour maintenir `uv.lock`.

- **Déploiement / démo (VM neuve)** : `docker compose up --build`. Besoin : **Docker seul**. Le build exécute `uv sync --frozen` **dans l'image** → installe les versions **exactes** du `uv.lock` commité (reproductible, sûr pour le live). Aucun `uv sync` à taper sur la VM.
- **Dev** : `uv sync --all-packages` installe tout le workspace dans `.venv` (sans `--all-packages`, uv ne sync que le projet racine → `ModuleNotFoundError`). Puis `uv run pytest` ou `.venv\Scripts\python -m pytest`. Quand les deps changent → `uv sync` régénère `uv.lock`, qu'on **commite** : c'est le seul moment où uv est nécessaire.
- Les tests trouvent les paquets first-party via `pythonpath` de pytest (marche même sans réinstaller). Pour lancer un service à la main hors Docker, poser `PYTHONPATH` sur son `src` — cf. §9.

**Dockerfile type** (contexte de build = racine du dépôt) :

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY libs/ libs/
COPY services/<svc>/ services/<svc>/
RUN uv sync --frozen --no-dev --package <svc>   # uv embarqué + uv.lock commité : build reproductible
RUN useradd -r app && chown -R app /app
USER app
# Ne PAS utiliser `uv run` au runtime : il exige un cache dans le home de l'utilisateur
# non-root, qui n'existe pas (le conteneur crashe). On appelle les binaires du venv.
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn","--factory","<module>.main:create_app","--host","0.0.0.0","--port","8000","--workers","1"]
```

Référence complète : `services/payment-api/Dockerfile` (migrations + seed avant uvicorn, HEALTHCHECK).

---

## 5. Conventions transverses (Definition of Done de chaque service)

- `GET /health/live` répond toujours 200 si le processus tourne.
- `GET /health/ready` vérifie les dépendances **réellement bloquantes** (la DB avec `SELECT 1`, timeout de 500 ms). **Ne doit pas dépendre de Keycloak.**
- `GET /metrics` au format Prometheus.
- Logs JSON sur une ligne, vers stdout, avec ces champs minimum :
  ```json
  {
    "ts": "…",
    "level": "info",
    "service": "payment-api",
    "trace_id": "…",
    "event": "payment.created",
    "user_id": "…",
    "src_ip": "…",
    "status": 201,
    "latency_ms": 42
  }
  ```

  - `trace_id` provient du header `X-Request-ID` (posé par le WAF), ou est généré s'il est absent, puis propagé dans les appels sortants.
  - `src_ip` provient de `X-Forwarded-For` ou `X-Real-IP` posés par le WAF.
  - Les noms d'événements sont pointés : `payment.created`, `payment.rejected`, `remediation.transition`, `probe.result`, etc.
- **Secrets** : lus depuis des fichiers (`/run/secrets/<nom>` ou chemin fourni par Vault Agent). Jamais dans le code, jamais dans un `.env` commité.
- OpenAPI exportée dans `contracts/` via `make export-openapi`. La CI vérifie que l'export est identique au fichier versionné.
- **Observabilité (contrat avec l'infra)** : chaque service expose `/metrics` sur son port interne 8000 (cible Prometheus `job=<service>`) ; les logs JSON sur stdout sont collectés par Loki, qui indexe uniquement `service` et `level` (les autres champs, dont `trace_id`, restent dans la ligne pour éviter l'explosion de cardinalité). Toute nouvelle métrique est listée dans la section du service.
- Au moins un test automatisé par module métier.
- Dockerfile avec utilisateur non-root.

---

## 6. Keycloak : intégration

**Realm `resilience`** (`keycloak/realm-resilience.json`) :

- **Rôles realm :** `client`, `ops`, `prober`.
- **Clients :**
  - `web-pay` : public, Authorization Code + PKCE, redirect `https://192.168.137.1/*` ;
  - `web-ops` : public, Authorization Code + PKCE, accès réservé au rôle `ops` ;
  - `prober` : confidentiel, service account activé, rôle `prober` assigné, grant `client_credentials`. Le secret vient de Vault et n'est jamais commité dans l'export : placer un placeholder dans le fichier.
  - `payment-api` : bearer-only, sert d'audience.
- **Audience mapper** sur `web-pay`, `web-ops` et `prober`, qui ajoute `aud: payment-api` (et `remediation-engine` pour `web-ops`).
- **Utilisateurs de test** avec des **`id` UUID fixes** : 3 clients (`alice`, `bob`, `carol`) et 1 ops (`operator`). Le service account `prober` a lui aussi un `id` fixe, défini dans l'export. Ces valeurs sont **imposées par le seed de payment-api** (`seed.py`) et doivent être recopiées telles quelles dans le realm :

  | Utilisateur | `id` |
  | --- | --- |
  | alice | `11111111-1111-4111-8111-111111111111` |
  | bob | `22222222-2222-4222-8222-222222222222` |
  | carol | `33333333-3333-4333-8333-333333333333` |
  | operator | `44444444-4444-4444-8444-444444444444` |
  | service account `prober` | `55555555-5555-4555-8555-555555555555` |
  | service account `remediation-engine` (rôle `ops`) | `66666666-6666-4666-8666-666666666666` |

  Secrets des clients et mot de passe des utilisateurs de test : placeholders `${PROBER_CLIENT_SECRET}`, `${REMEDIATION_CLIENT_SECRET}`, `${TEST_USERS_PASSWORD}` dans l'export, remplacés par Keycloak à l'import depuis ses variables d'environnement.

  Si le `sub` du jeton ne correspond à aucun de ces UUID, `/api/accounts/me` répond 404.
- **Sécurité :** `bruteForceProtected: true`, durée de vie des jetons d'accès de 5 minutes, `eventsEnabled` et `adminEventsEnabled` activés (sources SIEM).

**Piège de l'émetteur (`iss`).** Le navigateur passe par le WAF (`https://192.168.137.1/auth`) alors que les services appellent Keycloak en interne (`http://keycloak:8080`). On valide donc l'**émetteur public**, mais on récupère le **JWKS en interne** :

```python
ISSUER = settings.oidc_issuer  # https://192.168.137.1/auth/realms/resilience
JWKS_URL = (
    settings.oidc_jwks_url
)  # http://keycloak:8080/auth/realms/resilience/protocol/openid-connect/certs
jwks = PyJWKClient(JWKS_URL, cache_keys=True, lifespan=300)


def decode(token, audience):
    key = jwks.get_signing_key_from_jwt(token).key
    p = jwt.decode(token, key, algorithms=["RS256"], audience=audience, issuer=ISSUER)
    return Claims(sub=UUID(p["sub"]), roles=set(p.get("realm_access", {}).get("roles", [])))
```

Côté Keycloak (configuré par l'infra) : `KC_HOSTNAME=https://192.168.137.1/auth`, `KC_HTTP_RELATIVE_PATH=/auth`, `KC_HEALTH_ENABLED=true`, `KC_METRICS_ENABLED=true`, logs JSON.
**Pas** de `KC_HOSTNAME_BACKCHANNEL_DYNAMIC` : il rend l'`iss` des jetons internes non public → 401 `Invalid issuer` (vérifié ; cf. `DEPLOIEMENT-PROD.md` §1, §4).

**Le JWKS en cache est un choix de résilience** : pendant une panne de Keycloak, les jetons déjà émis restent valides et payment-api continue de servir.

---

## 7. payment-api

> **État : implémenté et testé** (lundi 19/10). Les décisions ci-dessous ont évolué par rapport à la version initiale du handoff : virement par **IBAN chiffré côté navigateur**, **un compte par personne**, routes sous **`/api`**.

### Principes

- **Un compte par personne.** Le compte débité est déduit du jeton (`sub` → son unique compte) ; aucun `src_account` n'est envoyé. L'unicité est garantie en base (index unique sur `owner_id`).
- **Bénéficiaire désigné par IBAN (+ BIC optionnel, + nom du titulaire)**, chiffré par le front (chiffrement hybride RSA-OAEP + AES-GCM). Le backend déchiffre, valide, et **ne persiste ni ne journalise jamais l'IBAN en clair**.
- **IBAN au repos** : HMAC-SHA256 à clé secrète (recherche du compte) + forme masquée `FR****1132` (affichage). Un SHA-256 simple est proscrit : l'espace des IBAN se casse par force brute.
- **BIC** : chaque compte a le BIC par défaut `RSALFRP0XXX` (fictif ; le « 0 » en 8e position désigne un BIC de test SWIFT).
- Données **fictives** uniquement : IBAN générés sur le code banque `99999`.

### Modèle de données (schéma `payments`, rôle Postgres `payment_app`)

```sql
accounts(id uuid pk, owner_id uuid not null unique, iban_hash text not null unique,
         iban_masked text not null, bic text not null default 'RSALFRP0XXX',
         label text not null, currency char(3) default 'EUR', created_at timestamptz)
transactions(id uuid pk, idempotency_key text unique not null, owner_id uuid not null,
             src_account uuid fk not null, dst_account uuid fk not null,
             dst_iban_masked text not null,
             amount numeric(12,2) not null check (amount > 0),
             status text not null check (status in ('COMPLETED','REJECTED')),
             request_hash text not null, created_at timestamptz)
ledger_entries(id bigint identity pk, tx_id uuid fk, account_id uuid fk, amount numeric(12,2) not null)
index ledger_entries(account_id), ledger_entries(tx_id), transactions(owner_id, created_at desc)
```

Le solde est **calculé** (`SUM(ledger_entries.amount)`), jamais stocké. `owner_id` = `sub` Keycloak. `request_hash` est un HMAC (même clé que les IBAN).

Migration unique `0001` (modifiée en place tant que rien n'est déployé : après un changement, `docker compose -f compose.dev.yaml down -v`).

### Seed (`seed.py`, idempotent, lancé au démarrage du conteneur)

| Compte | Propriétaire | IBAN (fictif) | Solde d'ouverture |
| --- | --- | --- | --- |
| Compte courant | alice | FR76 9999 9000 0110 0000 0001 132 | 1 500 € |
| Compte courant | bob | FR76 9999 9000 0110 0000 0002 102 | 800 € |
| Compte courant | carol | FR76 9999 9000 0110 0000 0003 169 | 2 500 € |
| `PROBE` | service account `prober` | FR76 9999 9000 0190 0000 0000 150 | 10 000 € |
| `PROBE_SINK` | propriétaire technique `00000000-…-0001` | FR76 9999 9000 0190 0000 0000 247 | 0 € |
| `bank_reserve` | propriétaire technique `00000000-…-0000` | — | négatif (source des ouvertures) |

`operator` n'a pas de compte (rôle ops seulement). Liste à jour : `python -m payment_api.seed`.

### Endpoints

Les routes métier sont sous **`/api`** ; les sondes techniques restent à la racine (`/health/live`, `/health/ready`, `/metrics`), pour Docker et Prometheus. Le WAF route `/api/payments`, `/api/accounts`, `/api/admin` vers payment-api **sans réécriture de chemin**.

| Méthode | Route | Rôle | Réponses |
| --- | --- | --- | --- |
| GET | `/api/payments/public-key` | aucun (clé publique) | `{public_key (PEM SPKI), key_id, algorithm: "RSA-OAEP-256", content_encryption: "A256GCM"}` |
| POST | `/api/payments/transfer` (header `Idempotency-Key` requis) | client, prober | 201 créé, 200 rejeu, 400 `decryption_failed`, 403 `no_account`, 409 `idempotency_conflict`, 422 (`insufficient_funds`, `invalid_iban`, `invalid_bic`, `bic_mismatch`, `unknown_account`, `same_account`, `invalid_payload`, validation) |
| GET | `/api/payments/{id}` | émetteur ou destinataire | 200, 404 |
| GET | `/api/payments?limit=` | client, prober | historique : virements émis et reçus |
| GET | `/api/accounts/me` | client, prober | **un objet** `{id, iban_masked, bic, label, currency, balance}` (`balance` en chaîne décimale, ex. `"1500.00"`) ; 404 si aucun compte |
| GET | `/api/admin/ledger/check` | ops | `{ok, unbalanced_tx[], incomplete_tx[], negative_accounts[]}` |
| GET | `/api/admin/payments?page=&page_size=&include_prober=` | ops | `{items: AdminPayment[], total, page, page_size}`, tous émetteurs confondus ; **trafic de la sonde exclu par défaut** (`include_prober=true` le réintègre) ; `AdminPayment` = `Payment` + `initiated_by` (`user` \| `prober`), absent de `Payment` côté client |
+| GET | `/api/admin/prober/success-rate` | ops | `{interval_s, window_minutes: 60, points: [{minute, success_count, expected_count, success_pct}]}`, une entrée par minute complète ; voir « SLI de la sonde » |
 
Erreurs métier au format `{"detail": {"code": "...", "message": "..."}}`. Les messages ne contiennent jamais de valeur saisie.

### Chiffrement des coordonnées bénéficiaire (contrat front ↔ back)

```
1. GET /api/payments/public-key          → clé publique RSA 3072 (PEM SPKI)
2. Front (WebCrypto) :
   a. JSON {iban, bic?, account_holder_name}
   b. clé AES-256 + IV de 12 octets, éphémères
   c. AES-GCM (tag 128 bits ; WebCrypto renvoie ciphertext || tag : c'est le format attendu)
   d. clé AES brute (32 octets) chiffrée en RSA-OAEP, hash SHA-256
3. POST /api/payments/transfer
   { amount: "50.05", encrypted_key, iv, ciphertext }   (les trois derniers en base64 standard)
4. Back : déchiffre, normalise (espaces/minuscules acceptés), valide IBAN (mod 97) et BIC,
   résout le compte par HMAC, exécute le virement.
```

- Toute erreur de déchiffrement → 400 `decryption_failed`, sans détail (pas d'oracle). Le front recharge alors la clé publique et renvoie **une fois** avec la **même** `Idempotency-Key`.
- L'empreinte d'idempotence est calculée sur les données **déchiffrées** : un rechiffrement de la même requête reste un rejeu (200).
- `src_account` dans le corps → 422 (champ interdit).
- Implémentation de référence côté client : `seal()` dans `resilience_common/crypto.py` (utilisée par les tests et le prober).

### Transfert (règles critiques, `service.py`)

```python
async def transfer(s, key, owner, req, pseudo):
    validate_transfer(req)                                   # IBAN mod 97, format BIC
    h = hash_request(pseudo.key, owner, req)                 # HMAC
    async with s.begin():
        existing = await get_by_key(s, key)
        if existing: check_replay(existing.request_hash, h); return existing, False   # 200 / 409
        src = await find_by_owner(s, owner)          or raise NoAccount              # 403
        dst = await find_by_iban_hash(s, pseudo.iban_hash(req.dst_iban)) or raise UnknownAccount  # 422
        check_bic(dst.bic, req.dst_bic); check_distinct(src.id, dst.id)
        await lock_accounts(s, sorted([src.id, dst.id]))     # SELECT … FOR UPDATE, ordre stable
        check_funds(await balance(s, src.id), req.amount)                      # 422
        tx = await insert(..., dst_iban_masked=mask(req.dst_iban))
        await insert_entries(s, tx.id, [(src.id, -amount), (dst.id, +amount)])
    return tx, True                                          # 201
```

- Une `IntegrityError` sur `idempotency_key` (course entre deux requêtes) est attrapée : relire et renvoyer la transaction existante.
- Les règles pures sont dans `domain/` (`rules.py`, `iban.py`, `bic.py`), testées sans base.
- Métriques : `payments_total{status}` (`completed`, `replayed` ou le code d'erreur), `payment_duration_seconds`.
- Origine : `transactions.initiated_by` (`user` | `prober`) est décidée par la couche API depuis le **rôle realm** du jeton, pas depuis l'UUID du compte, et un rejeu ne la réécrit pas. Index `(initiated_by, created_at)` car la sonde domine vite la table ; les filtres s'écrivent en `IN (...)` (via `INITIATED_BY_VALUES`), jamais en `!=`, qui ne sait pas utiliser l'index.
 
### Contrôle d'invariant (`/api/admin/ledger/check`)

```sql
SELECT tx_id FROM ledger_entries GROUP BY tx_id HAVING SUM(amount) <> 0;
SELECT t.id FROM transactions t LEFT JOIN ledger_entries e ON e.tx_id = t.id
 WHERE t.status = 'COMPLETED' GROUP BY t.id HAVING COUNT(e.id) <> 2;
SELECT account_id FROM ledger_entries e JOIN accounts a ON a.id = e.account_id
  WHERE a.label <> 'bank_reserve' GROUP BY account_id HAVING SUM(amount) < 0;
 ```

### SLI de la sonde (`/api/admin/prober/success-rate`)

Taux de réussite par minute sur la dernière heure, affiché dans l'onglet Monitoring de `web-ops`. Calcul pur dans `domain/probe_sli.py`.

payment-api ne voit que les virements **réussis** : un échec de sonde n'écrit rien. Le dénominateur vient donc de la cadence nominale : `expected_count = 60 / PROBER_INTERVAL_S`.
**Couplage à respecter** : `PROBER_INTERVAL_S` (payment-api, défaut 5) doit rester égal à `INTERVAL_S` (prober, défaut 5). Si l'un change sans l'autre, le taux est faux. La mesure indépendante de cette hypothèse est `probe_success_ratio`, exposée par le prober (§8).
La minute en cours est exclue (partielle, elle ferait plonger le dernier point) ; les minutes sans virement valent 0 % (une sonde arrêtée n'écrit rien, c'est le signal) ; le taux est plafonné à 100 %.
Effet connu du plafond : une sonde qui tombe sur une frontière de minute donne 13 puis 11 virements, soit un creux à ~92 % sans aucun échec réel. Le compte brut (`success_count`) reste exposé.


### Secrets (fichiers dans `$SECRETS_DIR`, défaut `/run/secrets`)

| Fichier | Contenu | Absent |
| --- | --- | --- |
| `db_password` | mot de passe du rôle `payment_app` | connexion sans mot de passe |
| `iban_hmac_key` | ≥ 16 octets aléatoires (`openssl rand -hex 32`) | **démarrage refusé** |
| `rsa_private_key` | PEM PKCS#8, RSA ≥ 2048 (3072 recommandé) | clé éphémère générée au démarrage (log `crypto.ephemeral_rsa_key`) : **à éviter en démo**, chaque recyclage invalide la clé publique en cache côté front |
|`Taille explicite`| (`pool_size=10`, `max_overflow=5`), `pool_timeout=2`, `statemen
 
**Ne jamais changer `iban_hmac_key` sur une base existante** : les comptes ne seraient plus retrouvables par IBAN.

### Pool DB

Taille explicite (`pool_size=10`, `max_overflow=5`), `pool_timeout=2`, `statement_timeout` côté Postgres (5 s). Un pool saturé fait échouer `/health/ready` **rapidement** (timeout 500 ms) : c'est un signal de détection.

### Tests

`uv run pytest services/payment-api` (Docker requis : Postgres via testcontainers). Couvrent : nominal, refus métier, IBAN/BIC, chiffrement (altération, mauvaise clé, IV invalide, payload incomplet), idempotence (rejeu, conflit, 10 requêtes concurrentes même clé), 50 virements croisés concurrents, ledger check, absence d'IBAN en clair en base et dans les logs, origine des opérations (rôle du jeton, rejeu), exclusion de la sonde de la vue admin, SLI par minute.
 
---

## 7 bis. Second facteur facial (back-office, rôle `ops`)

> **État : fait et testé de bout en bout** (21/10) : vrai Keycloak 26.8 + face-auth + Postgres. L'IoT (ESP8266, LED) n'est pas traité.

**Flux Keycloak `browser-face`** (navigateur, tous clients) : cookie, ou identifiant (`auth-username-form`) → sous-flux CONDITIONAL [`conditional-user-role` = `ops` → `face-recognition`] → mot de passe (`auth-password-form`). `client_credentials` (prober, moteur) n'est pas concerné. Le realm exporté contient **tous** les flux par défaut : dès que `authenticationFlows` est fourni, Keycloak ne recrée pas ceux qui manquent à l'import (le flux `clients` disparaîtrait, cassant prober et moteur).

**Authenticator** (`keycloak/face-authenticator`) : page `face-auth.ftl` (getUserMedia, capture 480×360 JPEG : la limite de formulaire de Keycloak est d'environ 128 Ko, au-delà HTTP 413), POST du data URL, appel serveur à serveur de face-auth. Non reconnu → page « Visage non reconnu », caméra éteinte, bouton → `resetFlow()` (identifiant vide). Verrou → page « bloqué jusqu'à … », sans caméra. face-auth injoignable → refus (fail-closed). L'échec est aussi compté par la protection brute-force de Keycloak (`failureChallenge`).

**face-auth** : YuNet (détection) + SFace (empreinte 128 floats), OpenCV sur CPU, ~39 Mo de modèles Apache 2.0. Préféré à InsightFace : modèles pré-entraînés InsightFace réservés à la recherche non commerciale, dépendances lourdes, compilation C. Seuil cosinus 0.363 (`MATCH_THRESHOLD`). Aucune image conservée ; empreinte chiffrée AES-256-GCM (`biometric_key`, identifiant en donnée authentifiée). Issues : `match` ; `no_match` et `not_enrolled` (comptés, même réponse vue de Keycloak) ; `locked` ; `no_face`/`invalid_image` (non comptés). 2 échecs consécutifs → verrou 5 min (`MAX_FAILURES`, `LOCK_S`).

| Méthode | Route | Auth | Rôle |
| --- | --- | --- | --- |
| GET | `/internal/users/{username}/status` | Bearer `face_service_token` | Keycloak : verrou actif ? |
| POST | `/internal/verify` `{username, image}` | Bearer `face_service_token` | Keycloak : comparaison + compteur |
| GET | `/api/biometrics/users` | JWT ops, aud `face-auth` | enrôlés + verrous/échecs en cours |
| PUT / DELETE | `/api/biometrics/users/{username}/face` | JWT ops | enrôler (un seul visage) / révoquer |
| POST | `/api/biometrics/users/{username}/unlock` | JWT ops | lever le verrou |
| GET | `/api/biometrics/attempts?limit=` | JWT ops | journal (issue, score) |

**Amorçage** : un ops non enrôlé ne peut pas se connecter. Pas d'enrôlement à la première connexion : un tiers qui ne connaît que l'identifiant pourrait enrôler son propre visage. Premier enrôlement en CLI : `python -m face_auth.enroll <username> <image>` dans le conteneur (cf. README) ; ensuite page `/admin/biometrics`. Realm : client bearer-only `face-auth` + mapper d'audience `aud-face-auth` sur `web-ops`.

---

## 8. prober

Boucle asynchrone, sans serveur HTTP lourd. Un petit serveur (FastAPI ou `prometheus_client.start_http_server`) expose `/metrics` et `/status`.

**Rôle** : prouver en continu qu'un vrai client peut payer. Le moteur de remédiation et le dashboard s'appuient sur ses résultats.

Toutes les 5 s :

1. obtenir un jeton par `client_credentials` sur `KC_INTERNAL/realms/resilience/protocol/openid-connect/token`, mis en cache jusqu'à `exp - 30s` ;
2. récupérer (et mettre en cache) la clé publique `GET https://192.168.137.1/api/payments/public-key` ; la recharger après un 400 `decryption_failed` ;
3. `POST https://192.168.137.1/api/payments/transfer` **via le WAF** (vérification TLS par bundle CA configurable), **1 centime** du compte `PROBE` (déduit du jeton) vers l'IBAN de `PROBE_SINK` (variable d'environnement `PROBE_DST_IBAN`), coordonnées chiffrées avec `seal()`, `Idempotency-Key` UUID neuf ;
4. succès si la réponse est 201 ;
5. publier les résultats :
   - métriques : `probe_success` (gauge 0/1), `probe_latency_seconds` (histogram), `probe_failures_total{stage="token|key|payment"}`, `probe_success_ratio` (gauge 0–1 : part des réussites parmi les 60 derniers résultats, la fenêtre de `/status` ; NaN avant la première sonde ; tracée telle quelle par Grafana, sans calcul côté dashboard) ;
    - log : `probe.result` avec `ok`, `stage` et `latency_ms` ;
   - `GET /status` : les 60 derniers résultats `[{at, ok, stage, latency_ms}]`, consommés par le dashboard et par le verifier du moteur.

**Budget** : chaque sonde coûte 1 centime, sans retour (un compte par personne). `PROBE` est ouvert à 10 000 €, soit ~57 jours à 172,80 €/jour ; le seed le recrée à chaque base neuve.

Le prober est un service séparé : il doit survivre à la panne de tous les autres.

---

## 9. remediation-engine

> **État : étape 7 faite côté code (21/10)** — `services/remediation-engine/`. AnsibleExecutor réel (ansible-runner + timeout, validé dans l'image), Verifier réel (sondes + `ledger_check` avec jeton ops `client_credentials`, erreurs réseau = « pas OK », jamais un crash), persistance Postgres (schéma `remediation`, DDL au démarrage, écritures best-effort) + reprise au redémarrage. Sans `DB_HOST` : mémoire ; `EXECUTOR`/`VERIFIER=fake` par défaut pour le dev nu. 22 tests verts + ruff. Contrat des playbooks pour l'infra : `docs/prod-interface.md` §3.

### Fonctionnement

`POST /alerts` (signé HMAC) → normalisation (ml / Alertmanager) → `classify` → orchestrateur : machine d'états, dédoublonnage `(type, target)`, retries (×3), cooldown + flapping → `Executor` (fake|ansible) → `Verifier` (fake|real) → `RECOVERED` ou `ESCALATED`. Chaque transition est journalisée (`remediation.transition`), stockée et publiée sur le bus → SSE `/events`. Métriques sur `/metrics`.

**Config (variables d'env)** : `EXECUTOR=fake|ansible`, `VERIFIER=fake|real`, `WEBHOOK_HMAC_KEY` (secret HMAC de `/alerts`, sinon fichier `$SECRETS_DIR/webhook_hmac_key`), `PROBER_STATUS_URL`, `LEDGER_URL`, `CA_BUNDLE`, `KC_TOKEN_URL`, `CLIENT_ID`, `PLAYBOOKS_DIR`, `ACTION_TIMEOUT_S`, `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`, `COOLDOWN_S`, `FLAPPING_MAX`, `FLAPPING_WINDOW_S`. Secrets fichiers : `webhook_hmac_key`, `remediation_client_secret`, `db_password`.

### Test et démo

**Dev local (sans uv ni Keycloak).** Le paquet n'est pas installé dans le venv (uv absent de la machine) : poser `PYTHONPATH` sur son `src` à chaque terminal.

1. Tests (les 7 critères de l'étape 5) — `pythonpath` de pytest trouve les paquets, pas de `PYTHONPATH` :
   ```powershell
   .\.venv\Scripts\python.exe -m pytest services/remediation-engine/tests -q   # -> 15 passed
   ```
2. Flux complet en HTTP réel (tout en fake, 2 terminaux) :
   ```powershell
   # Terminal A — le moteur
   $env:PYTHONPATH = "$PWD\services\remediation-engine\src"; $env:WEBHOOK_HMAC_KEY = "devsecret"
   .\.venv\Scripts\python.exe -m uvicorn --factory remediation_engine.main:create_app --port 8003
   # Terminal B — une alerte signée (MÊME secret)
   $env:WEBHOOK_HMAC_SECRET = "devsecret"
   .\.venv\Scripts\python.exe scripts/fake_alert.py --url http://127.0.0.1:8003/alerts
   ```
   Le Terminal A montre `TRIAGED → EXECUTING` (3 actions) `→ VERIFYING → RECOVERED` (`mttr_s`). Escalade : `--src-ip 192.168.137.1` (IP interne refusée par `block_ip`) ou `--target postgres` (hors liste). `/incidents`, `/events`, `/stats` exigent un JWT ops (donc Keycloak).

**Prod / démo (lab, étape 7).** Conteneurisé derrière le WAF : `EXECUTOR=ansible` (playbooks infra), `VERIFIER=real` (sondes prober + `ledger_check` via jeton ops), secret `webhook_hmac_key` par Vault. Les alertes viennent du `detection/` (ml) et d'Alertmanager. Scénario : `scripts/flood.py` (ou vraie attaque) → détection → `POST /alerts` → `block_ip` + `recycle_service` + `kill_db_conns` → `VERIFYING` → **le prober prouve un 201 + ledger ok** → `RECOVERED`, visible dans `web-ops` (SSE). `fake_alert.py` reste le secours pour déclencher la chaîne sans attendre une vraie alerte.

### API

| Méthode | Route                      | Auth                                                                                                             | Rôle                                           |
| ------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| POST    | `/alerts`                  | HMAC (`X-Signature: sha256=<hex>` sur le corps brut, ml) **ou** `Authorization: Bearer` (secret `alertmanager_token`, Alertmanager) | Entrée des alertes Alertmanager et ml-detector |
| GET     | `/incidents?state=&limit=` | JWT, rôle ops                                                                                                    | Liste                                          |
| GET     | `/incidents/{id}`          | JWT, rôle ops                                                                                                    | Détail et transitions                          |
| GET     | `/events`                  | JWT, rôle ops (jeton passé en query, car `EventSource` ne gère pas les headers ; vérifié puis jamais journalisé) | Flux SSE                                       |
| GET     | `/stats`                   | JWT, rôle ops                                                                                                    | Dernier MTTD/MTTR, compteurs                   |

### Normalisation des alertes

Les deux formats d'entrée sont convertis vers un modèle unique :

- **Alertmanager** (webhook v4) : `alerts[].labels.{alertname, service, src_ip}` ;
- **ml-detector** : `{"source":"ml","type":"anomaly","target":"payment-api","score":0.93,"features":{…},"src_ip":"…","at":"…"}`. **Figé (21/10)** dans `contracts/alert.schema.json` (signature HMAC en en-tête `X-Signature`, hors corps). Le `src_ip` dominant vient de la métrique `http_requests_by_source_total{src_ip}` (émise par payment-api via le middleware commun) : `topk(1, sum by (src_ip)(rate(...[1m])))`. Implémenté côté détecteur dans `detection/` (émet déjà l'alerte signée dès que `REMEDIATION_URL` est renseignée).

```python
class Alert(BaseModel):
    source: Literal["alertmanager", "ml"]
    type: str  # alertname ou "anomaly"
    target: str
    src_ip: IPv4Address | None
    score: float | None
    at: datetime
```

### Classification (`classifier.py`)

Règles explicites et testées, des alertes vers le type d'incident :

| Condition                                                                                             | Type d'incident     |
| ----------------------------------------------------------------------------------------------------- | ------------------- |
| Anomalie ML ou `HighRequestRate`/`High5xx`/`DbPoolSaturated` sur payment-api, avec `src_ip` dominante | `http_flood`        |
| `ServiceDown`/`Unhealthy` sur payment-api                                                             | `service_down`      |
| `KeycloakDown` ou échecs de jeton du prober (`stage=token`)                                           | `idp_down`          |
| `WafBlocksBurst`                                                                                      | `injection_attempt` |

### Politique (`playbook_map.yaml`)

```yaml
http_flood:
  actions: [block_ip, recycle_service, kill_db_conns]
  verify: { probe_ok_consecutive: 3, ledger_check: true, timeout_s: 60 }
service_down:
  actions: [recycle_service]
  verify: { probe_ok_consecutive: 3, ledger_check: true, timeout_s: 45 }
idp_down:
  actions: [recycle_service] # target: keycloak
  verify: { probe_ok_consecutive: 3, ledger_check: false, timeout_s: 90 }
injection_attempt:
  actions: [block_ip] # aucune action de disponibilité : rien n'est cassé
  verify: { ledger_check: true }
```

### Actions autorisées (liste fermée)

```python
class BlockIpParams(BaseModel):
    ip: IPv4Address  # refuser 192.168.137.1 et les IP internes Docker


class RecycleParams(BaseModel):
    service: Literal["payment-api", "keycloak"]


class KillConnsParams(BaseModel):
    db_role: Literal["payment_app"]


ALLOWED = {
    "block_ip": BlockIpParams,
    "recycle_service": RecycleParams,
    "kill_db_conns": KillConnsParams,
}
```

### Executor

```python
class Executor(Protocol):
    async def run(
        self, action: str, params: BaseModel
    ) -> ActionResult: ...  # ok, duration_ms, output
```

- `FakeExecutor` : succès ou échec configurable, délai simulé. Utilisé par les tests et en développement.
- `AnsibleExecutor` : `ansible_runner.run_async(playbook=f"{action}.yml", extravars=params.model_dump(mode="json"), …)`. Les playbooks (`block_ip.yml`, `recycle_service.yml`, `kill_db_conns.yml`) sont **fournis par l'infra** et montés dans `/playbooks`. Timeout par action.
- Sélection par variable d'environnement : `EXECUTOR=fake|ansible`.

### Machine d'états

```
DETECTED → TRIAGED → EXECUTING → VERIFYING → RECOVERED
                         ↑            │
                         └── retry ───┘ (max 2 retries)
tout état → ESCALATED   (échec de vérification, cooldown actif, limite de flapping)
```

```python
TRANSITIONS = {
    "DETECTED": {"TRIAGED", "ESCALATED"},
    "TRIAGED": {"EXECUTING", "ESCALATED"},
    "EXECUTING": {"VERIFYING", "ESCALATED"},
    "VERIFYING": {"RECOVERED", "EXECUTING", "ESCALATED"},
}
```

Toute transition non listée lève une exception (testé). Chaque transition est **persistée**, **journalisée** (`remediation.transition`) et **publiée sur le bus**.

### Orchestrateur

```python
async def handle(inc):
    async with locks[inc.target]:
        if cooldown.active(inc.target) or flapping.exceeded(inc.target):  # > 3 incidents / 10 min
            return await escalate(inc, "cooldown_or_flapping")
        await move(inc, "TRIAGED", plan=policy.plan_for(inc.type))
        for attempt in range(3):
            await move(inc, "EXECUTING", attempt=attempt)
            for action in inc.plan.actions:
                res = await executor.run(action, build_params(action, inc))
                await record_action(inc, action, res)
            await move(inc, "VERIFYING")
            if await verifier.check(inc.plan.verify):
                return await move(
                    inc, "RECOVERED", mttr_s=(now() - inc.detected_at).total_seconds()
                )
        await escalate(inc, "verification_failed")
```

- **Dédoublonnage :** clé `(type, target)`. Une alerte qui correspond à un incident non terminal y est rattachée, sans nouveau traitement.
- **Exécution :** le traitement tourne en tâche de fond (`asyncio.create_task`) ; `POST /alerts` répond 202 immédiatement.
- **Reprise au démarrage :** les incidents restés en `EXECUTING`/`VERIFYING` sont repris en `VERIFYING`.

### Verifier

- Interroge `prober /status` jusqu'à obtenir N succès consécutifs **postérieurs au début de la vérification**, dans la limite de `timeout_s`.
- Si `ledger_check: true`, appelle `payment-api /api/admin/ledger/check` avec un jeton ops obtenu par client_credentials (client confidentiel dédié `remediation-engine`, rôle `ops`, à ajouter au realm). Exige `ok == true`.

### Persistance

Schéma `remediation` :

- `incidents(id, type, target, state, src_ip, detected_at, recovered_at, mttd_s, mttr_s, attempt, plan jsonb)`
- `transitions(id, incident_id, at, from_state, to_state, action, params jsonb, result, detail)`
- `alerts(id, incident_id, raw jsonb, received_at)`

### Métriques

`incidents_total{type,outcome}`, `incident_mttr_seconds`, `incident_mttd_seconds`, `remediation_actions_total{action,result}`, `incidents_open`.

**MTTD** = heure de détection − heure de début de l'anomalie (champ `startsAt` d'Alertmanager ou `at` du ML).

### Événement SSE (`contracts/event.schema.json`)

```json
{
  "incident_id": "…",
  "at": "…",
  "state": "EXECUTING",
  "type": "http_flood",
  "target": "payment-api",
  "action": "block_ip",
  "params": { "ip": "192.168.137.42" },
  "result": "ok",
  "detail": "…"
}
```

Un heartbeat (commentaire SSE) est envoyé toutes les 15 s.

---

## 10. Front

### `@ra/api-client`

- Types générés par `openapi-typescript` depuis `contracts/openapi-*.json` (`pnpm gen`).
- `createClient({ baseUrl, getToken })` : ajoute `Authorization` et un `X-Request-ID` (UUID) à chaque requête, et convertit les réponses non-2xx en `ApiError {status, body}`.
- Aucune dépendance à Keycloak : le jeton est fourni par l'application.

### `@ra/ui`

Composants Card, Badge, StatusDot (`ok`/`degraded`/`down`), Table, Button, Spinner, EmptyState.

### `web/pay`

- **Auth :** `react-oidc-context`, avec `authority: https://192.168.137.1/auth/realms/resilience`, `client_id: web-pay`, `automaticSilentRenew: true`.
- **Pages :** Callback, Account (le compte unique : IBAN masqué, BIC, solde), Transfer, History.
- **Transfer :** saisie de l'IBAN (espaces acceptés), du BIC (optionnel) et du nom du titulaire, et du montant. **Pas de choix de compte source** (un compte par personne). Les coordonnées sont chiffrées dans le navigateur avec WebCrypto selon le contrat du §7 (RSA-OAEP SHA-256 + AES-GCM 256, IV 12 octets) puis envoyées à `POST /api/payments/transfer`. La clé publique est mise en cache et rechargée après un 400 `decryption_failed`.
- La clé d'idempotence est **générée au montage du formulaire** et régénérée seulement après un succès. Un double clic ou un rejeu réseau réutilise ainsi la même clé. Messages clairs pour 409 et 422 (codes du §7).
- Ne jamais journaliser (console, Sentry…) ni stocker (localStorage) l'IBAN saisi.
- Servi sous `/` derrière le WAF.

### `web/ops`

- **Auth :** client `web-ops` ; écran d'accès refusé si le rôle `ops` est absent.
- **Une page Overview, composée des widgets suivants :**

| Widget             | Source                                                | Contenu                                                                                                |
| ------------------ | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `SliBanner`        | `prober /status` (polling 2 s)                        | Grand indicateur vert/rouge et sparkline des 5 dernières minutes. **Élément central du Clip Chrono.**  |
| `ServiceGrid`      | Health des services, agrégés par le moteur (`/stats`) | État de chaque service                                                                                 |
| `IncidentTimeline` | SSE `/events`                                         | Transitions horodatées, action, paramètres, résultat                                                   |
| `DetectionPanel`   | `/stats`                                              | Score d'anomalie contre seuil, top des IP sources                                                      |
| `MttrCounters`     | `/stats`                                              | MTTD et MTTR du dernier incident                                                                       |
| `AssistantPanel`   | `rag-assistant POST /ask`                             | Questions/réponses avec sources citées ; **visuellement séparé** de la timeline, aucun bouton d'action |

- `useEventStream` reconnecte automatiquement. À chaque (re)connexion, il recharge `/incidents` pour combler les événements manqués.
- Servi sous `/ops` derrière le WAF.
 *(21/10 : le back-office réellement livré est l'application `frontend/` sous `/admin`, client `web-ops` ; `/ops` n'est pas routé.)*
---

## 11. Interfaces avec les autres piliers (à confirmer, sans bloquer)

| Pilier      | Le dev fournit                                                                                    | Le dev attend                                                                                                                                                                                                  | Mock en attendant                                                                  |
| ----------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Infra       | Dockerfiles, ports internes (8000), health, besoins réseau, variables d'environnement documentées, liste des métriques et format des logs (§5) | Stack Prometheus + Grafana + Loki (scrape des `/metrics`, collecte des logs stdout, dashboards techniques) ; `compose.yaml`, WAF routant `/`, `/ops`, `/api/payments` + `/api/accounts` + `/api/admin` (vers payment-api, **sans réécriture de chemin**), `/api/remediation`, `/auth` ; playbooks `block_ip.yml`, `recycle_service.yml`, `kill_db_conns.yml` ; Alertmanager configuré vers `POST /alerts` avec HMAC | `FakeExecutor` ; `compose.dev.yaml` local minimal (postgres + keycloak + services) |
| IA          | Métriques exposées ; format de `POST /alerts`                                                     | Webhook ml-detector conforme à `alert.schema.json` ; `rag-assistant POST /ask → {answer, sources[]}`                                                                                                           | Script `scripts/fake_alert.py` qui signe et poste une alerte                       |
| Cyber       | `X-Request-ID`, `src_ip` dans les logs, liste fermée des actions, IBAN jamais en clair (chiffrement navigateur, HMAC au repos) | Chemins Vault des secrets (secret client du prober, secret client du moteur, mot de passe DB, secret HMAC des webhooks, **`iban_hmac_key`**, **`rsa_private_key`** de payment-api)                                                                                                     | Fichiers dans `./.secrets/` (gitignored)                                           |
| Gouvernance | MTTD et MTTR mesurés, journal d'audit des transitions                                             | RTO cible, utilisé comme `timeout_s`                                                                                                                                                                           | Valeurs par défaut du YAML                                                         |

---

## 12. Plan d'exécution ordonné

Chaque étape se termine par des tests verts et un commit. **Ne pas passer à l'étape suivante sans les critères d'acceptation.**

> **Avancement au 19/10 :** étapes 0, 1 et 3 **faites** (lint vert, 20 tests `libs/common`, 67 tests payment-api). Étape 4 (prober) **codée** (5 tests, image OK) ; critère d'acceptation à rejouer quand Keycloak (étape 2, en cours côté collègue : reprendre les UUID du §6) sera dans `compose.dev.yaml`.
>
> **Avancement au 21/10 :**
> - **Attaque** : `scripts/flood.py` (générateur de charge, modes `get` et `transfer`). Le flood `transfer` sature le pool DB (verrou sur la ligne PROBE_SINK) → ~50 % de 5xx : dégradation visible et mesurable. Détection fiable = **taux de 5xx / débit** (pas `/health/ready` ni `probe_success`, qui récupèrent en pleine attaque car l'API shed la charge).
> - **Détection** : service `detection/` (Isolation Forest sur métriques Prometheus) intégré ; alerte conforme `alert.schema.json` + signée HMAC (prête, inactive tant que `REMEDIATION_URL` vide).
> - **src_ip** : nouvelle métrique `http_requests_by_source_total{src_ip}` (middleware commun) + payment-api ajouté au réseau `monitoring` de `compose.dev.yaml` (il en manquait, Prometheus ne le scrapait pas). Chaîne validée en local (en local `src_ip` = gateway Docker, vraie IP seulement derrière le WAF).
> - **Contrat** : `contracts/alert.schema.json` figé.
> - **Remédiation (étape 5)** : `services/remediation-engine/` **fait** — machine d'états, classifier, politique (`playbook_map.yaml`), orchestrateur (dédoublonnage, retries, cooldown, flapping), verifier, bus SSE, API `/alerts` (HMAC) + `/incidents` + `/stats` + `/events`, FakeExecutor/FakeVerifier, `scripts/fake_alert.py`. **15 tests verts + ruff.** Fonctionnement et étapes de test (dev/prod) : voir §9. Store en mémoire (persistance Postgres repoussée à l'étape 7).
> - **uv / build (21/10)** : `uv.lock` régénéré (inclut remediation-engine), Dockerfiles en `uv sync --frozen` → **builds reproductibles**. uv **jamais** sur l'hôte (embarqué dans l'image) ; la prod n'a besoin que de Docker, uv n'est requis que côté dev pour le lock. `pythonpath` pytest pour lancer les tests sans réinstaller. Cf. §4.
> - **Étape 7 (code) faite** : AnsibleExecutor, Verifier réel (jeton ops + ledger), persistance Postgres + reprise. `compose.dev.yaml` : moteur en `EXECUTOR=fake` + `VERIFIER=real` + Postgres. **Reste à l'infra** : playbooks (contrat dans `docs/prod-interface.md` §3), docker-socket-proxy, WAF (`/api/remediation` avec réécriture), Alertmanager signé.
> - **PC Hôte (21/10 soir)** : `compose.yaml` (projet `resilience-host`, conteneurs `ra-*`) monte la plateforme en conditions de démo : `PUBLIC_HOST` dans `.env`, PKI de labo (`scripts/gen-lab-pki.sh`, CA = `CA_BUNDLE`), Keycloak en mode `start` derrière le WAF, WAF nginx + ModSecurity/CRS **en blocage** (`waf/`, exclusions 920350 et 931100 ciblées et justifiées), relais L4 Windows + PROXY protocol pour l'IP réelle des clients (`edge/`, `docs/decision-proxy-l4-ip-source.md`), front + back-office validés en recette. **Reste** : étapes 5 à 8 du README (observabilité + Alertmanager, playbooks + docker-socket-proxy, Vault, détection sur site) ; pièges listés dans la note de passation du README.

### Étape 0 — Squelette (lundi)

- Workspace uv, workspace pnpm, `Makefile`, `.gitignore` (`.secrets/`, `.env`, `node_modules`, `.venv`), configuration ruff, pre-commit avec gitleaks.
- **Critère :** `uv sync` et `pnpm install` passent ; `make lint` passe.

### Étape 1 — `libs/common` (lundi)

- logging, metrics, health, auth (JWKS + `require_role`), hmac, settings.
- **Tests :**
  - jeton valide → claims ;
  - mauvais émetteur, mauvaise audience ou jeton expiré → 401 ;
  - rôle absent → 403 (JWKS servi par une fixture locale avec clé RSA générée) ;
  - HMAC valide ou invalide ;
  - `X-Request-ID` propagé dans les logs.

### Étape 2 — Realm Keycloak (lundi)

- `keycloak/realm-resilience.json` complet (section 6), avec les clients `prober` et `remediation-engine` confidentiels.
- Fichier `compose.dev.yaml` minimal pour le développement local : postgres + keycloak en `start-dev --import-realm`.
- **Critère :**
  - un jeton `client_credentials` du prober contient `aud: payment-api` et le rôle `prober` ;
  - un login `alice` via `web-pay` fonctionne.

### Étape 3 — payment-api (mardi)

- Modèle, migration Alembic, seed, endpoints, métriques, export OpenAPI.
- **Tests (sur un vrai Postgres via testcontainers) :**
  - transfert nominal ; fonds insuffisants → 422 ; compte non possédé → 403 ;
  - rejeu avec la même clé → 200 et **un seul** jeu d'écritures ; même clé avec un corps différent → 409 ;
  - **50 transferts concurrents** croisés A↔B : aucun deadlock, soldes exacts, `ledger/check.ok == true` ;
  - `ledger/check` détecte une écriture déséquilibrée insérée à la main.

### Étape 4 — prober (mardi)

- **Critère :** contre payment-api et Keycloak locaux, `probe_success == 1`. Arrêter payment-api → 0 en moins de 10 s. Le relancer → 1.

### Étape 5 — remediation-engine avec FakeExecutor (mardi)

- Modèles, classifier, policy, state machine, store, orchestrateur, verifier, bus, SSE, `/alerts`, `/incidents`, `/stats`.
- `scripts/fake_alert.py` pour poster une alerte signée.
- **Tests :**
  - toutes les transitions interdites lèvent une exception ;
  - alerte → `RECOVERED` quand le verifier est OK ;
  - verifier KO ×3 → `ESCALATED` ;
  - deux alertes identiques → un seul incident ;
  - HMAC invalide → 401 ;
  - paramètre hors liste (`service: "postgres"`, IP `192.168.137.1`) → rejet sans exécution ;
  - cooldown et flapping → `ESCALATED`.
- **Critère d'intégration :** `fake_alert.py` fait défiler la machine d'états, visible en SSE avec `curl -N`.

### Étape 6 — Front (mardi soir → mercredi matin)

- `api-client` généré, `ui`, puis `pay` (Accounts, Transfer, History), puis `ops` (SliBanner, IncidentTimeline en priorité, puis le reste).
- **Critère :**
  - un virement réalisé depuis `pay` apparaît dans History ;
  - un incident simulé apparaît en direct dans `ops` ;
  - SliBanner passe au rouge quand payment-api est arrêté.

### Étape 7 — AnsibleExecutor (mercredi 12 h, jalon critique)

- Brancher les playbooks de l'infra. Vérifier la sortie et les timeouts.
- **Critère :** une vraie alerte Alertmanager (ou `fake_alert.py`) → recyclage réel de payment-api → `RECOVERED` après 3 sondes OK et ledger OK.

### Étape 8 — Intégration ML et RAG (mercredi après-midi)

- Accepter le webhook ml-detector, afficher le score dans DetectionPanel, brancher AssistantPanel.

### Étape 9 — Robustesse et rendus (jeudi, gel du code à 17 h)

- **10 exécutions consécutives** du scénario d'attaque, en relevant le taux de succès, le MTTD et le MTTR.
- Corriger le flapping, les timeouts et les reconnexions SSE.
- Test E2E `tests/e2e/test_recovery.py` : login → paiement → incident injecté → `RECOVERED` → nouveau paiement 201 → ledger OK.
- README (section développement) : installation, variables d'environnement, lancement des tests, export OpenAPI, déroulé de vérification.
- `make export-openapi` à jour dans `contracts/`.

---

## 13. Pièges connus

- **`iss` Keycloak** : URL publique ≠ URL interne (voir section 6).
- **`EventSource` ne gère pas les headers** : jeton en query, durée de vie courte, jamais journalisé (filtrer l'URL dans les logs d'accès).
- **Renouvellement OIDC** : avec des jetons de 5 minutes, sans `automaticSilentRenew`, le dashboard décroche pendant la démo.
- **Deadlocks** : toujours verrouiller les comptes dans un ordre stable (UUID triés).
- **`/health/ready` trop large** : ne pas y inclure Keycloak, sinon une panne d'IdP déclencherait un recyclage inutile de payment-api.
- **Verifier** : ne compter que les sondes **postérieures** au début de la vérification, sinon les succès d'avant l'incident valident une fausse reprise.
- **Certificat TLS de labo** : le prober doit accepter le certificat auto-signé du WAF via un bundle CA configuré, pas via `verify=False` en dur.
- **RAM** : Keycloak consomme environ 700 Mo. Rester sobre en workers uvicorn (1 par service).
- **`uv run` dans le conteneur** : crash « Failed to initialize cache » avec un utilisateur non-root sans home. Appeler les binaires de `/app/.venv/bin` (voir §4).
- **testcontainers sous Windows** : Ryuk échoue avec Docker Desktop ; il est désactivé dans `conftest.py` (`TESTCONTAINERS_RYUK_DISABLED=true`).
- **Clé RSA éphémère** : sans secret `rsa_private_key`, chaque redémarrage de payment-api change la clé publique ; le front et le prober doivent la recharger sur 400 `decryption_failed`. Fournir la clé via Vault pour la démo.
- **`iban_hmac_key` immuable** : la changer rend les comptes introuvables par IBAN (il faudrait re-seeder).
- **Windows et fins de ligne** : `.gitattributes` avec `* text=auto eol=lf`, sinon les scripts shell et les entrypoints cassent dans les conteneurs.

---

## 14. Hors périmètre de ce handoff

`compose.yaml` de production, réseaux Docker, WAF/ModSecurity, Vault, Prometheus/Alertmanager/Grafana/Loki, contenu des playbooks Ansible, docker-socket-proxy, ml-detector, rag-assistant, scripts Red Team, EBIOS RM, PCA/PRA, NIS2/DORA. **Ne pas les implémenter ici** ; s'appuyer sur les contrats de la section 11 et sur les mocks.
