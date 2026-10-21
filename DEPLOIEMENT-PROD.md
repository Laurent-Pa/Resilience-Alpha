# Passage en production — écarts par rapport à `compose.dev.yaml`

Checklist des éléments à **modifier ou ajouter** pour passer du dev local (`compose.dev.yaml`,
Keycloak `start-dev`, secrets en fichiers) à la prod derrière WAF + Vault.

`compose.dev.yaml` est un environnement de dev local **jetable**. Il ne doit pas servir de base
telle quelle : reprendre les images et les variables, mais appliquer tous les points ci-dessous.

---

## 1. Keycloak

| Sujet | Dev (actuel) | Prod |
| --- | --- | --- |
| Commande | `start --import-realm` (déjà en mode non-dev localement) | `start --optimized --import-realm` (ou import par kcadm) |
| Base | H2 interne au conteneur (volontairement jetable) | Postgres dédié et persistant, séparé de celui de payment-api |
| `KC_HOSTNAME` | `https://localhost:8443/auth` | `https://192.168.137.1/auth` (**le `/auth` doit y figurer**, sinon l'`iss` perd ce segment — voir §4) |
| TLS | HTTPS auto-signé, terminé par Keycloak lui-même (cert généré par `keycloak/generate-keycloak-cert.sh`, voir `KC_HTTPS_CERTIFICATE_FILE`/`KC_HTTPS_CERTIFICATE_KEY_FILE`) | HTTPS, terminé au WAF ; `KC_PROXY_HEADERS=xforwarded` |
| Admin | `KC_BOOTSTRAP_ADMIN_*` en clair dans `keycloak.env` | identifiants admin forts, fournis par Vault, **rotation après le 1er boot** |
| Divers | — | `KC_HEALTH_ENABLED=true`, `KC_METRICS_ENABLED=true`, logs JSON |

**Backchannel dynamique.** Ne **pas** activer `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` sans avoir
réglé le point §4. Avec cette option, l'`iss` du jeton dépend de l'hôte appelant : le prober et le
moteur récupèrent leur jeton en interne (`keycloak:8080`) et obtiendraient un `iss` interne, rejeté
par payment-api. (Vérifié en dev : c'est la cause des 401 `Invalid issuer`.)

---

## 2. Secrets (Vault au lieu de fichiers)

En dev, tout est dans `./.secrets/` (gitignored). En prod, **chaque secret vient de Vault**
(Vault Agent qui écrit dans un chemin lu par le service, ou injection équivalente). Aucun secret
en clair, nulle part, y compris dans un `.env`.

Secrets à provisionner (chemins Vault à définir avec le pilier cyber, cf. §11 du handoff) :

| Secret | Utilisé par | Contrainte |
| --- | --- | --- |
| `db_password` | Postgres + payment-api | — |
| `iban_hmac_key` | payment-api | **immuable** une fois une base seedée (sinon comptes introuvables par IBAN) |
| `rsa_private_key` | payment-api | PEM PKCS#8, RSA ≥ 2048 (3072 conseillé). **Obligatoire en prod** : sans lui, clé éphémère régénérée à chaque boot → front et prober cassés |
| `prober_client_secret` | prober ↔ Keycloak | = secret du client `prober` dans le realm |
| `remediation_client_secret` | remediation-engine ↔ Keycloak | = secret du client `remediation-engine` |
| secret HMAC webhooks | remediation-engine | signe `POST /alerts` (Alertmanager, ml-detector) |
| `test_users_password` | Keycloak (import realm) | **à retirer en prod** si les comptes de test ne sont pas voulus |

Le realm `keycloak/realm-resilience.json` contient des **placeholders** (`${PROBER_CLIENT_SECRET}`,
`${REMEDIATION_CLIENT_SECRET}`, `${TEST_USERS_PASSWORD}`) résolus depuis l'environnement de Keycloak
à l'import. En prod, alimenter ces variables depuis Vault.

---

## 3. Réseau, WAF, URL publiques

- **Seul le WAF est publié.** Tous les services (payment-api, prober, remediation-engine, keycloak,
  postgres) restent sur des réseaux Docker internes, sans port exposé sur l'hôte. Retirer tous les
  `ports: ["127.0.0.1:..."]` du dev.
- **Routage WAF** (sans réécriture de chemin) :
  - `/` → `web-pay` ; `/ops` → `web-ops` ;
  - `/api/payments`, `/api/accounts`, `/api/admin` → payment-api ;
  - `/api/remediation` → remediation-engine ;
  - `/auth` → keycloak.
- Le WAF pose `X-Request-ID`, `X-Forwarded-For` / `X-Real-IP` (exploités dans les logs, §5 du handoff).
- **TLS labo** : le prober doit valider le certificat auto-signé du WAF via un **bundle CA**
  (`CA_BUNDLE`), **jamais** `verify=False` en dur.

---

## 4. Le piège de l'émetteur (`iss`) — à valider absolument

Le navigateur passe par le WAF (`https://192.168.137.1/auth`) ; les services appellent Keycloak en
interne (`http://keycloak:8080`). Il faut **un `iss` unique et public** pour tous les jetons, tout en
récupérant le JWKS en interne.

- `KC_HOSTNAME = https://192.168.137.1/auth` → `iss = https://192.168.137.1/auth/realms/resilience`
  pour **tous** les jetons (navigateur **et** prober/moteur en interne).
- Côté services : `OIDC_ISSUER = https://192.168.137.1/auth/realms/resilience` (émetteur public, validé)
  et `OIDC_JWKS_URL = http://keycloak:8080/auth/realms/resilience/protocol/openid-connect/certs`
  (JWKS interne). payment-api n'utilise pas le discovery, donc ces deux URL peuvent différer sans souci.

**Test de non-régression avant la démo** : récupérer un jeton `client_credentials` du prober *depuis
le réseau interne* et vérifier que son `iss` vaut l'émetteur **public** (avec `/auth`). S'il vaut
`http://keycloak:8080/...`, payment-api renverra 401 `Invalid issuer`.

---

## 5. payment-api / prober / remediation-engine

- **`OIDC_ISSUER`** : passer de `https://localhost:8443/auth/...` (dev) à l'URL publique (§4).
- **prober** : `TARGET_URL = https://192.168.137.1` (via le WAF, plus `http://payment-api:8000`) ;
  `CA_BUNDLE` renseigné ; `KC_TOKEN_URL` interne ; `PROBE_DST_IBAN` = IBAN de `PROBE_SINK`.
- **remediation-engine** : `EXECUTOR=ansible` (dev = `fake`) ; monter les playbooks de l'infra dans
  `/playbooks` (`block_ip.yml`, `recycle_service.yml`, `kill_db_conns.yml`) ; **jamais d'accès direct
  à `docker.sock`** → passer par le `docker-socket-proxy`.
- **Postgres** : `statement_timeout` côté serveur, volume persistant et sauvegardé, rôle `payment_app`
  avec mot de passe Vault (ne pas réutiliser le mot de passe de dev).
- **uvicorn** : rester à `--workers 1` par service (contrainte RAM, Keycloak ~700 Mo).

---

## 6. Observabilité (pilier infra)

- Prometheus scrape le `/metrics` de chaque service (port interne 8000), un `job` par service.
- Loki collecte les logs JSON stdout ; n'indexer que `service` et `level` (le reste, dont `trace_id`,
  reste dans la ligne pour éviter l'explosion de cardinalité).
- Grafana : dashboards techniques (santé, latences, `incident_mttr_seconds`, `probe_success`, etc.).

---

## 7. Points de vérification avant le jury

- [ ] `KC_HOSTNAME` public contient `/auth` ; `iss` du jeton prober interne = émetteur public (§4).
- [ ] `rsa_private_key` fourni par Vault (pas de log `crypto.ephemeral_rsa_key` au boot de payment-api).
- [ ] `iban_hmac_key` figé et sauvegardé ; jamais régénéré sur une base existante.
- [ ] Aucun port de service exposé hors WAF ; `docker.sock` inaccessible au moteur.
- [ ] `EXECUTOR=ansible` et playbooks montés ; un recyclage réel aboutit à `RECOVERED` (étape 7).
- [ ] Prober en TLS via `CA_BUNDLE` (pas de `verify=False`).
- [ ] Comptes de test Keycloak retirés si non souhaités en prod.
- [ ] `.gitattributes` en `eol=lf` (scripts/entrypoints cassent sinon dans les conteneurs).
