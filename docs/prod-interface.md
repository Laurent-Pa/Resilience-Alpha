# Interface code ↔ infra — pour le `compose.yaml` de prod

Public visé : le pilier **infra**, qui assemble le `compose.yaml` de prod (WAF, Vault, observabilité, playbooks Ansible).
Ce document liste, pour chaque service du pilier **dev**, ce que son code attend en entrée : image, port, variables d'environnement, secrets, dépendances réseau. Les valeurs viennent des `settings.py` réels (pas inventées).

> Rien ici n'est à implémenter côté dev. C'est le contrat pour câbler la prod. Les écarts « étape 7 » (encore absents du code) sont signalés en fin de document.

---

## 0. Conventions communes (tous les services Python)

Base `resilience_common.ServiceSettings` — s'applique à payment-api, prober, remediation-engine.

| Variable | Défaut | Prod |
| --- | --- | --- |
| `SECRETS_DIR` | `/run/secrets` | chemin monté par Vault Agent / Docker secrets |
| `SERVICE_NAME` | (par service) | inchangé |
| `LOG_LEVEL` | `INFO` | `INFO` |
| `OIDC_ISSUER` | `https://192.168.137.1/auth/realms/resilience` | URL **publique** du realm (via WAF) |
| `OIDC_JWKS_URL` | `http://keycloak:8080/auth/realms/resilience/protocol/openid-connect/certs` | URL **interne** de Keycloak |

- **Secrets = fichiers**, un fichier par champ, nommé exactement comme le champ (ex. `db_password`), dans `SECRETS_DIR`. Jamais de secret en variable d'environnement.
- Chaque service écoute en **interne sur le port 8000** et expose `GET /health/live`, `GET /health/ready`, `GET /metrics`.
- Logs JSON une ligne sur stdout (collecte Loki). `/health/ready` ne dépend **jamais** de Keycloak.
- Piège `iss` : on valide l'émetteur **public** mais on récupère le JWKS en **interne**. Keycloak doit donc être configuré `KC_HOSTNAME=https://<public>/auth`, `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true`.

---

## 1. payment-api

- **Build** : `services/payment-api/Dockerfile` (contexte = racine du dépôt). Port interne **8000**. Dev : exposé `8001`.
- **Dépend de** : Postgres (réseau interne), Keycloak (JWKS interne). Doit être sur le réseau `monitoring` pour être scrapé par Prometheus.

| Variable | Défaut | Prod |
| --- | --- | --- |
| `OIDC_AUDIENCE` | `payment-api` | inchangé |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | l'origine publique du front (ex. `https://192.168.137.1`) |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` | `postgres` / `5432` / `resilience` / `payment_app` | selon la base de prod |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `5` | garder sobre (RAM contrainte) |
| `DB_POOL_TIMEOUT_S` | `2.0` | `2.0` (saturation = signal de détection) |
| `DB_STATEMENT_TIMEOUT_MS` | `5000` | `5000` |
| `SEED_ON_START` | `true` | `true` (seed idempotent) |

**Secrets** (`SECRETS_DIR/…`) :

| Fichier | Obligatoire | Note |
| --- | --- | --- |
| `db_password` | recommandé | sinon connexion sans mot de passe |
| `iban_hmac_key` | **oui** (démarrage refusé sinon) | **immuable** : le changer rend les comptes introuvables par IBAN |
| `rsa_private_key` | **oui en démo** | PEM PKCS#8, RSA ≥ 2048. Absent → clé éphémère régénérée à chaque redémarrage (invalide la clé publique en cache côté front/prober) |

---

## 2. prober

- **Build** : `services/prober/Dockerfile`. Port interne **8000**. Dev : `8002`.
- **Dépend de** : Keycloak (interne, pour le jeton), **le WAF** (le virement de preuve passe par le WAF comme un vrai client). Doit survivre à la panne de tous les autres.

| Variable | Défaut | Prod |
| --- | --- | --- |
| `KC_TOKEN_URL` | `http://keycloak:8080/.../token` | URL **interne** de Keycloak |
| `CLIENT_ID` | `prober` | inchangé |
| `TARGET_URL` | `https://192.168.137.1` | URL **publique** du WAF |
| `CA_BUNDLE` | `None` (magasin système) | chemin du **bundle CA du cert de labo du WAF** (ne jamais désactiver la vérif TLS) |
| `PROBE_DST_IBAN` | `FR7699999000019000000000247` | IBAN de `PROBE_SINK` (seed payment-api) |
| `PROBE_DST_NAME` | `PROBE_SINK` | inchangé |
| `INTERVAL_S` / `TIMEOUT_S` | `5.0` / `3.0` | inchangé |

**Secret** : `prober_client_secret` (service account `prober`, grant `client_credentials`).

---

## 3. remediation-engine

- **Build** : `services/remediation-engine/Dockerfile`. Port interne **8000**. Dev : `8003`.
- **Dépend de** : le WAF (pour `LEDGER_URL`), le prober (`PROBER_STATUS_URL`), et **en prod les playbooks Ansible** montés dans `/playbooks`.

| Variable | Défaut (dev) | Prod |
| --- | --- | --- |
| `OIDC_AUDIENCE` | `remediation-engine` | inchangé |
| `EXECUTOR` | `fake` | **`ansible`** |
| `VERIFIER` | `fake` | **`real`** |
| `PROBER_STATUS_URL` | `http://prober:8000/status` | interne |
| `LEDGER_URL` | `https://192.168.137.1/api/admin/ledger/check` | URL **publique** du WAF |
| `COOLDOWN_S` | `120` | à aligner sur le RTO (gouvernance) |
| `FLAPPING_MAX` / `FLAPPING_WINDOW_S` | `3` / `600` | idem |

**Secret** : `webhook_hmac_key` (**obligatoire**, signature HMAC de `POST /alerts`). **Le même secret** doit être fourni au service `detection`.

**Montage prod** : les playbooks `block_ip.yml`, `recycle_service.yml`, `kill_db_conns.yml` (fournis par l'infra) dans `/playbooks`. Le moteur n'accède **jamais** à `docker.sock` directement (passe par `docker-socket-proxy`).

---

## 4. detection (pilier IA, mais déployé avec le reste)

- **Build** : `detection/Dockerfile`, **contexte = racine du dépôt** (membre du workspace uv, `uv sync --frozen`). Interroge Prometheus, poste l'alerte signée au moteur. Le modèle `model.joblib` n'est pas dans l'image : à fournir en volume sur `/app/detection`.
- `REMEDIATION_URL=http://remediation-engine:8000/alerts` (interne).
- `PYTHONUNBUFFERED=1` (sinon `docker logs` reste vide — ajouté en dev).
- **Secret** : `webhook_hmac_key` (identique à celui du moteur).
- **À refaire sur site** : le modèle `model.joblib` est entraîné sur le trafic normal **local**. Il faut recollecter le normal de prod (10–15 min) et réentraîner, sinon faux positifs / non-détection.

---

## 5. WAF — routage attendu (sans réécriture de chemin, sauf mention)

| Chemin public | Vers | Note |
| --- | --- | --- |
| `/` | frontend | app de paiement |
| `/ops` | frontend (web-ops) | rôle `ops` requis |
| `/api/payments`, `/api/accounts`, `/api/admin` | payment-api:8000 | **sans réécriture** |
| `/api/remediation` | remediation-engine:8000 | ⚠️ les routes du moteur sont à la **racine** (`/alerts`, `/incidents`, `/events`, `/stats`) : prévoir une **réécriture** `/api/remediation/* → /*`, ou exposer le moteur à la racine. **À trancher avec le dev.** |
| `/auth` | keycloak:8080 | `KC_HTTP_RELATIVE_PATH=/auth` |

**Le WAF doit poser** : `X-Forwarded-For` / `X-Real-IP` (source de `src_ip` — **sans eux, la détection d'IP et `block_ip` ne fonctionnent pas**) et `X-Request-ID` (devient `trace_id`). Seul le WAF est publié ; tout le reste sur réseaux Docker internes.

**Alertmanager** → `POST /alerts` du moteur, avec en-tête `X-Signature: sha256=<hex>` (HMAC `webhook_hmac_key` sur le corps brut).

---

## 6. Inventaire des secrets (pour Vault)

| Secret | Consommé par | Remarque |
| --- | --- | --- |
| `db_password` | payment-api | rôle `payment_app` |
| `iban_hmac_key` | payment-api | **immuable**, ≥ 16 octets |
| `rsa_private_key` | payment-api | PEM PKCS#8 |
| `prober_client_secret` | prober | client confidentiel `prober` |
| `webhook_hmac_key` | remediation-engine **et** detection | même valeur des deux côtés |
| `remediation_client_secret` | remediation-engine | **étape 7** (jeton ops du verifier) — voir §7 |

---

## 7. Écarts « étape 7 » encore ouverts côté code (bloquants pour la prod réelle)

1. **Verifier réel incomplet** : `ledger_check` lève `NotImplementedError` ([verifier.py:57](../services/remediation-engine/src/remediation_engine/core/verifier.py#L57)). Le moteur n'a **aucun réglage** pour obtenir un jeton ops par `client_credentials` (il manque un `kc_token_url` + un secret `remediation_client_secret` dans ses settings). À ajouter côté dev **avant** de passer `VERIFIER=real`.
2. **AnsibleExecutor** : à brancher sur les vrais playbooks infra, vérifier sorties et timeouts.
3. **Persistance** : le store du moteur est **en mémoire** (pas de reprise au redémarrage). Migrer vers Postgres avant la prod.
4. **Client `remediation-engine` dans le realm Keycloak** : client confidentiel, rôle `ops`, service account (UUID `66666666-…`). À ajouter à l'export de realm.

Tant que ces points ne sont pas faits, la prod tournerait en mode dégradé (fake/real partiel). La chaîne complète **en simulation** est, elle, fonctionnelle via `compose.dev.yaml`.
