# Interface code ↔ infra — pour le `compose.yaml` de prod

Public visé : le pilier **infra**, qui assemble le `compose.yaml` de prod (WAF, Vault, observabilité, playbooks Ansible).
Ce document liste, pour chaque service du pilier **dev**, ce que son code attend en entrée : image, port, variables d'environnement, secrets, dépendances réseau. Les valeurs viennent des `settings.py` réels (pas inventées).

> Rien ici n'est à implémenter côté dev. C'est le contrat pour câbler la prod. Les écarts « étape 7 » (encore absents du code) sont signalés en fin de document.

> **Implémentation de référence (21/10)** : [`compose.yaml`](../compose.yaml) applique ce contrat sur le PC Hôte (procédure et vérifications : README, « Déploiement sur le PC Hôte »). En cas de doute entre ce document et `compose.yaml`, `compose.yaml` est la configuration **testée**.

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
- Piège `iss` : on valide l'émetteur **public** mais on récupère le JWKS en **interne**. Keycloak doit donc être configuré `KC_HOSTNAME=https://<public>/auth` **sans** `KC_HOSTNAME_BACKCHANNEL_DYNAMIC` : avec cette option, un jeton obtenu en interne (prober, moteur) porte un `iss` interne et payment-api répond 401 `Invalid issuer` (cf. [DEPLOIEMENT-PROD.md](../DEPLOIEMENT-PROD.md) §1 et §4). Derrière le WAF : `KC_HTTP_ENABLED=true` (en mode `start`, le port HTTP interne 8080 est **fermé** par défaut) et `KC_PROXY_HEADERS=xforwarded`. Validé sur le PC Hôte le 21/10 : l'émetteur annoncé en interne est bien l'émetteur public.

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
- **Dépend de** : le WAF (pour `LEDGER_URL`), le prober (`PROBER_STATUS_URL`), Keycloak (jeton ops, interne), Postgres (schéma `remediation`, créé au démarrage), et **en prod les playbooks Ansible** montés dans `/playbooks`.

| Variable | Défaut (dev) | Prod |
| --- | --- | --- |
| `OIDC_AUDIENCE` | `remediation-engine` | inchangé |
| `EXECUTOR` | `fake` | **`ansible`** |
| `VERIFIER` | `fake` | **`real`** |
| `PROBER_STATUS_URL` | `http://prober:8000/status` | interne |
| `LEDGER_URL` | `https://192.168.137.1/api/admin/ledger/check` | URL **publique** du WAF |
| `CA_BUNDLE` | `None` | bundle CA du cert de labo du WAF (pour `LEDGER_URL` en https) |
| `KC_TOKEN_URL` | `http://keycloak:8080/.../token` | URL **interne** de Keycloak |
| `CLIENT_ID` | `remediation-engine` | inchangé |
| `PLAYBOOKS_DIR` / `ACTION_TIMEOUT_S` | `/playbooks` / `60` | inchangé |
| `DOCKER_HOST` | — | `tcp://docker-socket-proxy:2375` (lu par les modules `community.docker` des playbooks) |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` | *(vide = mémoire)* / `5432` / `resilience` / `payment_app` | **renseigner `DB_HOST`** (sinon pas de reprise au redémarrage). Le rôle doit pouvoir `CREATE SCHEMA` |
| `COOLDOWN_S` | `120` | à aligner sur le RTO (gouvernance) |
| `FLAPPING_MAX` / `FLAPPING_WINDOW_S` | `3` / `600` | idem |

**Secrets** : `webhook_hmac_key` (**obligatoire**, signature HMAC de `POST /alerts` ; **le même** que pour `detection`), `remediation_client_secret` (jeton ops du verifier, = `REMEDIATION_CLIENT_SECRET` de Keycloak), `db_password`.

**Montage prod** : les playbooks `block_ip.yml`, `recycle_service.yml`, `kill_db_conns.yml` (fournis par l'infra) dans `/playbooks` (lecture seule). Le moteur n'accède **jamais** à `docker.sock` directement (passe par `docker-socket-proxy`).

**Contrat des playbooks** (ce que l'`AnsibleExecutor` fournit) :
- exécutés par ansible-runner, inventaire `localhost ansible_connection=local` (dans le conteneur du moteur, utilisateur non-root) ; viser `hosts: localhost`, `gather_facts: false` ;
- paramètres **déjà validés** en extravars : `block_ip.yml` → `ip` ; `recycle_service.yml` → `service` (`payment-api` | `keycloak`) ; `kill_db_conns.yml` → `db_role` (`payment_app`) ;
- succès = `rc 0` ; tout échec ou dépassement de `ACTION_TIMEOUT_S` remonte en action `fail` dans la timeline (avec la fin de la sortie Ansible) ;
- disponible dans l'image : `ansible-core`, collection `community.docker` 4.x, `requests`. Rien d'autre (pas de CLI `docker`, pas de `psql`) : pour `kill_db_conns`, passer par `community.docker.docker_container_exec` sur le conteneur postgres ;
- playbook absent → log `ansible.playbooks_missing` au démarrage (le moteur démarre quand même).

**Attention `kill_db_conns`** : si le moteur utilise lui aussi le rôle `payment_app`, ses connexions sont tuées. C'est encaissé (retry, puis le journal est best-effort), mais un rôle dédié (`DB_USER=remediation_app`) est plus propre.

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
| `/` | frontend | app de paiement ; back-office sous `/admin` (même application, client Keycloak `web-ops`, rôle `ops` requis) |
| `/api/payments`, `/api/accounts`, `/api/admin` | payment-api:8000 | **sans réécriture** |
| `/api/remediation` | remediation-engine:8000 | **avec réécriture** `/api/remediation/* → /*` (tranché : les routes du moteur restent à la racine, comme `/health` et `/metrics`). **Ne pas publier `/alerts`** : Alertmanager et `detection` l'appellent en interne. |
| `/auth` | keycloak:8080 | `KC_HTTP_RELATIVE_PATH=/auth` |

**Le WAF doit poser** : `X-Forwarded-For` / `X-Real-IP` (source de `src_ip` — **sans eux, la détection d'IP et `block_ip` ne fonctionnent pas**) et `X-Request-ID` (devient `trace_id`). Seul le WAF est publié ; tout le reste sur réseaux Docker internes.

**Implémenté (21/10)** dans [`waf/nginx/default.conf.template`](../waf/nginx/default.conf.template). `X-Forwarded-For` est **écrasé** par l'IP de connexion (jamais complété : un en-tête forgé ferait bloquer une autre IP). Sous Docker Desktop, cette IP n'est réelle que grâce au relais L4 Windows et au PROXY protocol : voir [decision-proxy-l4-ip-source.md](decision-proxy-l4-ip-source.md).

**Alertmanager** → `POST /alerts` du moteur (interne), avec `Authorization: Bearer <alertmanager_token>` (Alertmanager ne sait pas signer un corps). `detection` signe, lui, en `X-Signature: sha256=<hex>` (HMAC `webhook_hmac_key`).

---

## 6. Inventaire des secrets (pour Vault)

| Secret | Consommé par | Remarque |
| --- | --- | --- |
| `db_password` | payment-api | rôle `payment_app` |
| `iban_hmac_key` | payment-api | **immuable**, ≥ 16 octets |
| `rsa_private_key` | payment-api | PEM PKCS#8 |
| `prober_client_secret` | prober | client confidentiel `prober` |
| `webhook_hmac_key` | remediation-engine **et** detection | même valeur des deux côtés |
| `remediation_client_secret` | remediation-engine | jeton ops du verifier (client `remediation-engine`) |
| `db_password` | remediation-engine | si `DB_HOST` renseigné |
| `alertmanager_token` | remediation-engine **et** Alertmanager | jeton bearer de `POST /alerts` |

---

## 7. Étape 7 côté code : faite (21/10)

- **Verifier réel** : sondes prober + `ledger_check` avec jeton ops `client_credentials` (mis en cache). Une panne du prober ou du WAF compte comme « pas OK » (retry / escalade), jamais comme un crash.
- **AnsibleExecutor** : ansible-runner, timeout par action, validé dans l'image (succès, échec, timeout).
- **Persistance Postgres** (schéma `remediation`, DDL idempotent au démarrage) + **reprise** : incidents `EXECUTING`/`VERIFYING` repris en `VERIFYING` sans rejouer les actions ; cooldown rechargé. Base indisponible → le moteur tourne en mémoire (log `store.unavailable`).
- **Client Keycloak** `remediation-engine` : déjà dans le realm (rôle `ops`, UUID `66666666-…`).

**Reste à l'infra** : les trois playbooks (contrat §3), `DOCKER_HOST` vers le docker-socket-proxy, le routage WAF (§5), Alertmanager signé vers `POST /alerts`, et les secrets Vault (§6).
