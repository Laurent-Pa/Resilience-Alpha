# Service de détection d'anomalies — Workshop RESILIENCE-ALPHA

Surveille les métriques Prometheus, détecte un déni de service (ou toute anomalie) avec un
**Isolation Forest** (scikit-learn, non supervisé) et prévient le moteur de remédiation par une
alerte **signée HMAC**.

```
Prometheus → [detection : lit + score ML] → anomalie persistante (3 relevés) → POST /alerts → remediation-engine
```

On apprend au modèle à quoi ressemble le trafic NORMAL, puis il repère ce qui s'en écarte
(pic de requêtes, erreurs 5xx, latence). Il fournit aussi la `src_ip` dominante de l'attaque.

## Les fichiers

| Fichier           | Rôle                                                                  |
| ----------------- | --------------------------------------------------------------------- |
| `config.py`       | **Le seul à modifier** : URLs, requêtes PromQL, seuils                |
| `prom.py`         | Interroge Prometheus (partagé)                                        |
| `collect.py`      | Étape 1 — collecte du trafic normal → `normal_traffic.csv`            |
| `train.py`        | Étape 2 — entraîne le modèle → `model.joblib`                         |
| `detect.py`       | Étape 3 — surveille en direct et alerte                               |
| `signing.py`      | Signature HMAC (`X-Signature`) de l'alerte, testée (`test_signing.py`) |
| `pyproject.toml`  | Dépendances (membre du workspace uv, versions verrouillées dans `uv.lock`) |

`normal_traffic.csv` et `model.joblib` sont **générés** et ignorés par git : à refaire sur
chaque machine (le modèle est un pickle lié à la version de scikit-learn et au trafic local).

## Lancer la détection (stack Docker, cas normal)

Le service `detection` est déjà dans `compose.dev.yaml`. Prérequis : la stack tourne
(payment-api, prober, remediation-engine, Prometheus) et le secret `.secrets/webhook_hmac_key`
existe (le **même** que celui du moteur).

```powershell
# 1. Collecter ~12 min de trafic NORMAL (aucune attaque pendant ce temps)
docker compose -f compose.dev.yaml -f observability/docker-compose.observability.yml run --rm --no-deps detection python collect.py 12

# 2. Entraîner
docker compose -f compose.dev.yaml -f observability/docker-compose.observability.yml run --rm --no-deps detection python train.py

# 3. Lancer la détection en continu
docker compose -f compose.dev.yaml -f observability/docker-compose.observability.yml up -d detection
docker logs --tail 20 resilience-alpha-detection-1
```

`./detection` est monté dans le conteneur : `normal_traffic.csv` et `model.joblib` sont écrits
sur l'hôte et lus sans rebuild. **Sans `model.joblib`, le conteneur plante au démarrage.**

Dans les logs : `✅ normal`, puis pendant une attaque `⚠️ ANORMAL (1/3)…(3/3)`, puis
`🚨 ANOMALIE CONFIRMÉE (src_ip=…)` et `remédiation notifiée`.

> **À refaire sur le site de la démo.** Le modèle doit être entraîné sur le trafic normal de
> la plateforme finale (WAF, vrais flux), pas sur celui d'un poste de dev. Sinon : fausses
> alertes ou attaque non vue. Compter 10 à 15 min de collecte, avec le prober actif.

## Hors Docker (dev du service)

```powershell
uv sync --all-packages           # depuis la racine du dépôt
cd detection
# config.py : PROMETHEUS_URL = "http://localhost:9090"
..\.venv\Scripts\python.exe collect.py 10
..\.venv\Scripts\python.exe train.py
..\.venv\Scripts\python.exe detect.py
```

Test de la signature : `uv run pytest detection` (depuis la racine).

## Brancher la remédiation

`config.py` pointe déjà vers `REMEDIATION_URL = "http://remediation-engine:8000/alerts"`
(vide = on logge seulement). L'alerte respecte `contracts/alert.schema.json` :

```json
{"source":"ml","type":"anomaly","target":"payment-api","score":0.93,
 "features":{...},"src_ip":"203.0.113.5","at":"2026-10-21T12:00:00+00:00"}
```

Elle est signée : en-tête `X-Signature: sha256=<hmac_sha256(secret, corps brut)>`. Le secret
est lu dans `/run/secrets/webhook_hmac_key` (sinon variable `WEBHOOK_HMAC_SECRET`) ; le moteur
doit utiliser la **même valeur**.

`src_ip` vient de la métrique `http_requests_by_source_total{src_ip}`, donc du
`X-Forwarded-For` posé par le WAF. **Sans WAF**, c'est l'IP de la passerelle Docker : pour
tester en local, lancer l'attaque avec `--xff 8.8.8.8` (cf. `scripts/flood.py`).

## Réglages utiles (`config.py`)

- `QUERIES` : les signaux surveillés (`http_requests_total`, `http_request_duration_seconds`, `probe_*`).
- `CONSECUTIVE_ANOMALIES` : relevés anormaux d'affilée avant de déclencher (3 par défaut ;
  monter si trop de fausses alertes, baisser pour réagir plus vite).
- `POLL_INTERVAL_SECONDS` : fréquence d'interrogation (10 s par défaut).

## Dépannage

- **`docker logs` vide** : stdout doit être non bufferisé (`PYTHONUNBUFFERED=1`, déjà dans l'image).
- **Beaucoup de fausses alertes** : trop peu de données d'entraînement ou `probe_success`
  absent à la collecte. Vérifier `http://localhost:9090/targets` (tous UP), puis recollecter.
- **Le conteneur plante** : `model.joblib` manquant (voir étapes 1-2).
