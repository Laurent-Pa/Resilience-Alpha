# Reste à faire côté infra — état au 21/10

Public : le pilier **infra**. Le code (payment-api, prober, remediation-engine, detection) est prêt pour la prod ; ce document liste **tout ce qui manque côté infra** pour que la démo de remédiation autonome tourne en vrai, sans intervention humaine.

Référence détaillée des variables, secrets et ports de chaque service : [prod-interface.md](prod-interface.md). Écarts dev → prod (Keycloak, `iss`, TLS) : [../DEPLOIEMENT-PROD.md](../DEPLOIEMENT-PROD.md).

**Légende** : 🔴 bloquant pour la démo · 🟠 nécessaire en prod · 🟢 confort

---

## Vue d'ensemble : où en est la chaîne

| Maillon | État | Manque (infra) |
| --- | --- | --- |
| Détection IA (`detection/`) → `POST /alerts` | ✅ code prêt | modèle à réentraîner sur site (§7) |
| Alertmanager → `POST /alerts` | ❌ (auth par jeton prête côté moteur) | règles + routage (§3) |
| Moteur : classification, décision, vérification | ✅ code prêt | config prod (§5) |
| **Exécution réelle des actions** | ❌ | **les 3 playbooks** + docker-socket-proxy (§1, §2) |
| Preuve de reprise (prober via WAF + ledger) | ✅ code prêt | WAF + CA (§4) |

Aujourd'hui en dev, les actions sont **simulées** (`EXECUTOR=fake`). Tant que §1 et §2 ne sont pas faits, rien n'est réellement remédié.

---

## 1. 🔴 Les trois playbooks Ansible

À livrer dans un dossier monté **en lecture seule** sur `/playbooks` du conteneur `remediation-engine`. Noms exacts :

| Fichier | Extravar reçue (déjà validée par le moteur) | Effet attendu |
| --- | --- | --- |
| `block_ip.yml` | `ip` (IPv4, jamais loopback) | bloquer cette IP **au WAF** (seul point d'entrée), de façon idempotente |
| `recycle_service.yml` | `service` : `payment-api` ou `keycloak` | redémarrer le conteneur correspondant |
| `kill_db_conns.yml` | `db_role` : `payment_app` | tuer les connexions Postgres de ce rôle (`pg_terminate_backend`) |

Contraintes d'exécution (imposées par le moteur) :

- lancés par ansible-runner, **dans le conteneur du moteur**, utilisateur non-root, inventaire `localhost ansible_connection=local` → écrire `hosts: localhost`, `gather_facts: false` ;
- outils disponibles dans l'image : `ansible-core`, collection **`community.docker` 4.x**, `requests`. **Pas** de CLI `docker`, **pas** de `psql` → passer par les modules `community.docker.*` (ex. `docker_container` avec `restart: true`, `docker_container_exec` sur le conteneur postgres pour `kill_db_conns`) ;
- succès = code retour 0. Tout échec ou dépassement de `ACTION_TIMEOUT_S` (60 s par défaut) apparaît comme action `fail` dans la timeline, puis retry (×3) et escalade ;
- un playbook manquant est signalé au démarrage par le log `ansible.playbooks_missing`.

Squelette :

```yaml
# recycle_service.yml
- hosts: localhost
  gather_facts: false
  tasks:
    - community.docker.docker_container:
        name: "{{ service }}"          # adapter au nom réel du conteneur
        state: started
        restart: true
```

**Test minimal** avant intégration : le moteur a été validé avec des playbooks factices (succès, échec, timeout). Rejouer avec les vrais : `docker compose exec remediation-engine ls /playbooks` puis une alerte via `scripts/fake_alert.py`.

---

## 2. 🔴 docker-socket-proxy

Le moteur **n'accède jamais** à `docker.sock`.

- Déployer un `docker-socket-proxy` (ex. `tecnativa/docker-socket-proxy`) sur un réseau interne partagé **uniquement** avec `remediation-engine`.
- Autoriser le strict nécessaire : `CONTAINERS=1`, `POST=1`, `EXEC=1` (pour `kill_db_conns`) ; tout le reste à 0.
- Dans le service `remediation-engine` : `DOCKER_HOST=tcp://docker-socket-proxy:2375` (lu par `community.docker`).

---

## 3. 🔴 Alertmanager (et règles Prometheus)

Aucune règle d'alerte ni Alertmanager n'existe encore dans `observability/`. Prometheus ne fait que scraper.

### 3.1 Règles : noms et labels **exacts**

Le moteur ne reconnaît que ces `alertname` (le reste est ignoré, mais journalisé). Le label **`service`** devient la cible de l'incident.

| `alertname` | Label `service` | Incident | Actions |
| --- | --- | --- | --- |
| `HighRequestRate`, `High5xx`, `DbPoolSaturated` | `payment-api` | `http_flood` | block_ip, recycle, kill_db_conns |
| `ServiceDown`, `Unhealthy` | `payment-api` | `service_down` | recycle |
| `KeycloakDown`, `ProbeTokenFailures` | peu importe (forcé à `keycloak`) | `idp_down` | recycle keycloak |
| `WafBlocksBurst` | `waf` | `injection_attempt` | block_ip |

⚠️ Pour `http_flood` et `injection_attempt`, l'alerte **doit porter un label `src_ip`** : sans lui, `block_ip` est refusé et l'incident est escaladé. Grouper par IP dans l'expression :

```yaml
groups:
  - name: resilience
    rules:
      - alert: ServiceDown
        expr: up{job="payment-api"} == 0
        for: 15s
        labels: { service: payment-api }
      - alert: High5xx
        # une série par IP source -> label src_ip disponible
        expr: sum by (src_ip) (rate(http_requests_by_source_total[1m])) > 50
              and on() sum(rate(http_requests_total{job="payment-api",status=~"5.."}[1m])) > 1
        for: 30s
        labels: { service: payment-api }
      - alert: ProbeTokenFailures
        expr: rate(probe_failures_total{stage="token"}[1m]) > 0
        for: 20s
        labels: { service: keycloak }
```

Seuils indicatifs : à caler avec le scénario `scripts/flood.py`.

### 3.2 Routage et authentification

- Webhook vers `http://remediation-engine:8000/alerts` (**interne**, jamais via le WAF). `send_resolved: true` est sans danger : les `resolved` sont ignorés.
- Alertmanager ne sait pas signer un corps : il s'authentifie par **jeton bearer**, lu depuis le secret `alertmanager_token` (même fichier monté dans Alertmanager **et** dans le moteur). Générer : `openssl rand -hex 32`.

```yaml
# alertmanager.yml
route:
  receiver: remediation
  group_wait: 5s          # la remédiation doit partir vite (MTTD)
  group_interval: 30s
  repeat_interval: 5m
receivers:
  - name: remediation
    webhook_configs:
      - url: http://remediation-engine:8000/alerts
        send_resolved: true
        http_config:
          authorization:
            type: Bearer
            credentials_file: /run/secrets/alertmanager_token
```

Sans ce secret côté moteur, l'authentification par jeton est désactivée (seule la signature HMAC de `detection/` passe).

---

## 4. 🔴 WAF

| Chemin public | Vers | Réécriture |
| --- | --- | --- |
| `/` | frontend | non |
| `/ops` | frontend (web-ops) | non |
| `/api/payments`, `/api/accounts`, `/api/admin` | `payment-api:8000` | **non** |
| `/api/remediation/*` | `remediation-engine:8000/*` | **oui** (préfixe retiré) |
| `/auth` | `keycloak:8080` | non |

- **Ne pas publier** `/alerts`, `/health/*`, `/metrics`.
- Poser **`X-Forwarded-For` / `X-Real-IP`** (sans eux : pas de `src_ip`, donc ni détection d'IP ni `block_ip`) et **`X-Request-ID`**.
- Mécanisme de blocage d'IP pilotable par `block_ip.yml` (liste de refus + rechargement), idempotent.
- `/api/remediation/events` est un flux **SSE** : désactiver le buffering (`proxy_buffering off` sous nginx), timeout de lecture ≥ 60 s ; le jeton passe en query → **ne pas journaliser la query string** de cette route.
- Fournir le **bundle CA** du certificat de labo, monté dans le prober et le moteur (`CA_BUNDLE`).
- ⚠️ **IP source et Docker Desktop (21/10)** : un WAF publié directement voit toutes les connexions venir de la passerelle Docker (`172.x`), donc `X-Forwarded-For` serait faux pour tout le monde. Retenu : un proxy L4 nginx pour Windows sur le 443 de l'hôte, qui transmet l'IP réelle au WAF par PROXY protocol, avec le WAF publié sur `127.0.0.1:8443` seulement. Détails et alternatives écartées : [decision-proxy-l4-ip-source.md](decision-proxy-l4-ip-source.md). Implémenté dans `compose.yaml`, `waf/`, `edge/`.

---

## 5. 🔴 `compose.yaml` de prod : services du pilier dev

Repartir de `compose.dev.yaml` en appliquant [DEPLOIEMENT-PROD.md](../DEPLOIEMENT-PROD.md). Spécifique au moteur :

```yaml
remediation-engine:
  environment:
    EXECUTOR: ansible
    VERIFIER: real
    OIDC_ISSUER: https://192.168.137.1/auth/realms/resilience
    LEDGER_URL: https://192.168.137.1/api/admin/ledger/check
    CA_BUNDLE: /certs/lab-ca.pem
    KC_TOKEN_URL: http://keycloak:8080/auth/realms/resilience/protocol/openid-connect/token
    DB_HOST: postgres              # sinon : pas de reprise au redémarrage
    DOCKER_HOST: tcp://docker-socket-proxy:2375
  volumes:
    - ./playbooks:/playbooks:ro
    - ./certs/lab-ca.pem:/certs/lab-ca.pem:ro
  secrets: [webhook_hmac_key, alertmanager_token, remediation_client_secret, db_password]
```

- Le moteur crée lui-même son schéma `remediation` au démarrage : son rôle Postgres doit avoir le droit `CREATE` sur la base.
- 🟠 Rôle Postgres **dédié** au moteur (`DB_USER=remediation_app`) recommandé : avec `payment_app`, `kill_db_conns` coupe aussi les connexions du moteur (encaissé, mais sale).
- Aucun `ports:` sur les services ; seul le WAF est publié. Cela vaut aussi pour **Prometheus (9090), Loki (3100), Grafana (3001)**, aujourd'hui publiés dans `docker-compose.observability.yml` (Grafana éventuellement derrière le WAF).
- 🟠 `restart: unless-stopped` sur tous les services : le prober doit survivre à tout le reste.

---

## 6. 🟠 Secrets (Vault)

Un fichier par secret, monté dans `/run/secrets` (ou chemin `SECRETS_DIR`) :

| Secret | Pour | Note |
| --- | --- | --- |
| `db_password` | postgres, payment-api, remediation-engine | |
| `iban_hmac_key` | payment-api | **immuable** une fois la base seedée |
| `rsa_private_key` | payment-api | PEM PKCS#8 ; **obligatoire en démo** |
| `prober_client_secret` | prober | = `PROBER_CLIENT_SECRET` de Keycloak |
| `remediation_client_secret` | remediation-engine | = `REMEDIATION_CLIENT_SECRET` de Keycloak |
| `webhook_hmac_key` | remediation-engine, detection | **même valeur des deux côtés** |
| `alertmanager_token` | remediation-engine, Alertmanager | jeton bearer de `POST /alerts` (§3.2), même valeur des deux côtés |

Côté Keycloak : `PROBER_CLIENT_SECRET`, `REMEDIATION_CLIENT_SECRET`, `TEST_USERS_PASSWORD`, admin bootstrap.

---

## 7. 🟠 Détection IA sur site

- Fournir `model.joblib` en volume sur `/app/detection`.
- **Réentraîner sur le trafic normal du lab** (10–15 min de collecte, cf. `detection/README.md`) : le modèle actuel, entraîné en local, produit des faux positifs (observé le 21/10 au redémarrage de payment-api).
- `REMEDIATION_URL=http://remediation-engine:8000/alerts`, `PYTHONUNBUFFERED=1`, réseau `monitoring` (Prometheus).

---

## 8. 🟢 Observabilité

- Scrape déjà en place pour `payment-api`, `prober`, `remediation-engine`. Ajouter Keycloak (`KC_METRICS_ENABLED=true`).
- Dashboards Grafana : `probe_success`, `probe_latency_seconds`, `http_requests_total{status}`, `http_requests_by_source_total{src_ip}`, `incidents_total{type,outcome}`, `incidents_open`, `incident_mttd_seconds`, `incident_mttr_seconds`, `remediation_actions_total{action,result}`.
- Loki : n'indexer que `service` et `level`. Événements utiles pour les dashboards : `remediation.transition`, `probe.result`, `verifier.ledger_check`, `ansible.error`, `store.write_failed`.

---

## 9. Recette avant le jury

- [ ] Les 3 playbooks présents (pas de log `ansible.playbooks_missing` au boot du moteur).
- [ ] `fake_alert.py` → `recycle_service` redémarre **réellement** payment-api → `RECOVERED`.
- [ ] `scripts/flood.py` depuis le PC Attaquant → détection → `block_ip` bloque **son** IP au WAF → `RECOVERED` → nouveau virement 201.
- [ ] Une alerte Alertmanager `ServiceDown` (arrêt manuel de payment-api) aboutit à `RECOVERED`.
- [ ] Redémarrer le moteur en plein `VERIFYING` : l'incident reprend et termine (log `remediation.resume`).
- [ ] `iss` du jeton du moteur obtenu en interne = émetteur public (sinon `ledger_check` en 401).
- [ ] 10 exécutions consécutives du scénario, MTTD/MTTR relevés.
- [ ] Entre deux démos : vider `remediation.incidents` / `transitions`, sinon cooldown (120 s) et anti-flapping (> 3 incidents / 10 min) escaladent les essais suivants.
