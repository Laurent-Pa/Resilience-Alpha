# Service de détection d'anomalies — Workshop RESILIENCE-ALPHA

Détecte un déni de service (ou toute anomalie) en surveillant les métriques
Prometheus, et prévient le moteur de remédiation. Modèle : **Isolation Forest**
(détection d'anomalies non supervisée, scikit-learn).

## L'idée

```
Prometheus  →  [detection : lit + score ML]  →  si anomalie persistante  →  remédiation
```

On apprend au modèle à quoi ressemble le trafic NORMAL, puis il repère tout
seul ce qui s'en écarte (le pic de requêtes / latence du DoS).

## Les fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | **Le seul à modifier** : URL Prometheus, requêtes, réglages |
| `prom.py` | Outils pour interroger Prometheus (partagé) |
| `collect.py` | Étape 1 — collecter du trafic normal → `normal_traffic.csv` |
| `train.py` | Étape 2 — entraîner le modèle → `model.joblib` |
| `detect.py` | Étape 3 — surveiller en direct et alerter |

## Les 3 étapes

### En local pour tester (hors Docker)

```
pip install -r requirements.txt
```

Dans `config.py`, mets `PROMETHEUS_URL = "http://localhost:9090"`.

1. **Collecter** (pendant que le trafic est normal, ~10 min) :
   ```
   python collect.py 10
   ```
2. **Entraîner** :
   ```
   python train.py
   ```
3. **Détecter** (laisse tourner, puis lance l'attaque pour voir) :
   ```
   python detect.py
   ```

Pendant le DoS, tu verras les lignes passer de `✅ normal` à `⚠️ ANORMAL`,
puis `🚨 ANOMALIE CONFIRMÉE` au bout de 3 relevés anormaux.

### En conteneur (pour la plateforme finale)

Dans `config.py`, remets `PROMETHEUS_URL = "http://prometheus:9090"`.

Ajoute ce service à ton `docker-compose` (sur le même réseau que Prometheus) :

```yaml
  detection:
    build: ./detection
    container_name: detection
    restart: unless-stopped
    depends_on:
      - prometheus
    networks:
      - monitoring
```

Le conteneur lance `detect.py`. ⚠️ Il lui faut un `model.joblib` déjà entraîné :
fais collect + train une fois en local, le fichier est copié dans l'image au build.

## Brancher la remédiation

Quand le `remediation-engine` existera, mets son URL dans `config.py` :
```python
REMEDIATION_URL = "http://remediation:8080/incident"
```
Le service enverra un POST JSON avec les métriques au moment de l'anomalie.
Tant que c'est vide, il loggue juste l'alerte (utile pour la démo).

## Réglages utiles (config.py)

- `QUERIES` : les signaux surveillés. Déjà réglés sur tes métriques
  (`http_requests_total`, `http_request_duration_seconds`, `probe_*`).
- `CONSECUTIVE_ANOMALIES` : nb d'anomalies d'affilée avant de déclencher
  (3 par défaut — monte-le si trop de fausses alertes, baisse-le pour réagir plus vite).
- `POLL_INTERVAL_SECONDS` : fréquence d'interrogation (10 s par défaut).
