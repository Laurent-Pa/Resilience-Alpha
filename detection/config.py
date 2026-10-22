# ===================================================================
# CONFIGURATION DU SERVICE DE DÉTECTION
# C'est le SEUL fichier à modifier pour adapter le service.
# ===================================================================

# --- Où joindre Prometheus ---
# En local (hors conteneur) : http://localhost:9090
# Dans le réseau Docker      : http://prometheus:9090
PROMETHEUS_URL = "http://prometheus:9090"

# --- Où prévenir le moteur de remédiation quand une anomalie est détectée ---
# Le remediation-engine n'est pas encore codé : laisse vide ("") pour
# juste logguer l'alerte, ou mets son URL quand il existera, par ex :
# "http://remediation-engine:8000/alerts"   (endpoint + port du handoff)
REMEDIATION_URL = "http://remediation-engine:8000/alerts"

# Service visé par l'anomalie (champ "target" de l'alerte, cf. alert.schema.json).
TARGET_SERVICE = "payment-api"

# Secret HMAC pour signer POST /alerts (en-tête X-Signature). Requis SEULEMENT si
# REMEDIATION_URL est défini. Contrat : le secret = contenu du fichier, espaces retirés,
# encodé UTF-8 — le moteur doit lire le MÊME secret de la même façon.
# Fichier d'abord (conventions projet /run/secrets), sinon variable d'env WEBHOOK_HMAC_SECRET.
HMAC_SECRET_FILE = "/run/secrets/webhook_hmac_key"  # noqa: S105 (chemin du secret, pas le secret)

# --- Les signaux qu'on surveille ---
# Chaque entrée = un nom de "feature" (colonne) -> une requête PromQL.
# Ce sont ces chiffres que le modèle apprend puis surveille.
# Tu peux en ajouter/retirer : collect.py et train.py s'adaptent tout seuls.
QUERIES = {
    # Débit total de requêtes HTTP (req/s). Explose pendant un DoS.
    "req_rate": "sum(rate(http_requests_total[1m]))",
    # Débit de requêtes en erreur serveur 5xx (req/s). Monte sous surcharge.
    "error_rate": 'sum(rate(http_requests_total{status=~"5.."}[1m]))',
    # Latence HTTP au 95e centile (s). Grimpe quand l'API sature.
    "http_latency_p95": (
        "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[1m])) by (le))"
    ),
    # Le service répond-il, vu du prober ? 1 = ok, 0 = down.
    "probe_success": "min(probe_success)",
    # Latence vue par le prober au 95e centile (s).
    "probe_latency_p95": (
        "histogram_quantile(0.95, sum(rate(probe_latency_seconds_bucket[1m])) by (le))"
    ),
    # Échecs du prober (éch/s), toutes étapes confondues.
    "probe_failures_rate": "sum(rate(probe_failures_total[1m]))",
}

# --- IP source dominante (pour block_ip de la remédiation) ---
# Pas une feature du modèle : récupérée seulement quand une anomalie est confirmée,
# pour dire à la remédiation QUI bloquer. S'appuie sur http_requests_by_source_total
# (émis par payment-api, labellé par src_ip).
SOURCE_IP_QUERY = "topk(1, sum by (src_ip) (rate(http_requests_by_source_total[1m])))"

# --- Réglages de la boucle de détection ---
POLL_INTERVAL_SECONDS = 10  # on interroge Prometheus toutes les 10 s
CONSECUTIVE_ANOMALIES = 3  # nb d'anomalies d'affilée avant de déclencher
# Seuil du score Isolation Forest : en dessous = anormal. Le défaut de sklearn (-0.5) est trop
# sensible sur un trafic normal quasi constant (un débit -30 % ou un pic de latence suffisent).
# Mesuré le 22/10 (2 h d'historique PC Hôte, repos + navigation browse.py) : pire relevé normal
# -0.722, 0 alerte confirmée sur 2 h à -0.72 (4 à -0.66) ; flood simulé -0.76 (get) à -0.82.
# À revérifier après chaque réentraînement ; le seuil est figé dans model.joblib par train.py.
SEUIL_SCORE = -0.725
# (évite de réagir à un simple hoquet)

# --- Fichiers produits ---
DATA_FILE = "normal_traffic.csv"  # données de trafic normal (étape collecte)
MODEL_FILE = "model.joblib"  # modèle entraîné (étape entraînement)
