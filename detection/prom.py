# ===================================================================
# OUTILS PARTAGÉS : interroger Prometheus et construire un "relevé"
# Utilisé par collect.py, train.py et detect.py.
# ===================================================================
import time

import requests

import config


def query_one(promql):
    """Pose UNE question (requête PromQL) à Prometheus et renvoie un nombre.

    Renvoie 0.0 si Prometheus ne répond rien (pas de données pour l'instant,
    histogramme vide, etc.) pour que le reste du programme ne plante pas.
    """
    url = f"{config.PROMETHEUS_URL}/api/v1/query"
    try:
        reponse = requests.get(url, params={"query": promql}, timeout=5)
        reponse.raise_for_status()
        resultat = reponse.json()["data"]["result"]
        if not resultat:
            return 0.0
        # On prend la valeur de la première série renvoyée.
        valeur = float(resultat[0]["value"][1])
        # Prometheus peut renvoyer "NaN" sous forme de texte -> on met 0.
        if valeur != valeur:  # test NaN (NaN != NaN est vrai)
            return 0.0
        return valeur
    except Exception as e:
        print(f"[prom] requête en échec ({promql}): {e}")
        return 0.0


def releve_actuel():
    """Interroge TOUTES les métriques de config.QUERIES une fois.

    Renvoie un dictionnaire {nom_feature: valeur}, par ex :
    {"req_rate": 12.3, "error_rate": 0.0, "http_latency_p95": 0.04, ...}
    L'ordre des clés suit config.QUERIES (important pour le modèle).
    """
    return {nom: query_one(requete) for nom, requete in config.QUERIES.items()}


def _serie(promql, debut, fin):
    """{timestamp: valeur} d'une requête sur une plage (NaN -> 0.0, comme query_one)."""
    url = f"{config.PROMETHEUS_URL}/api/v1/query_range"
    params = {"query": promql, "start": debut, "end": fin, "step": config.POLL_INTERVAL_SECONDS}
    reponse = requests.get(url, params=params, timeout=30)
    reponse.raise_for_status()
    resultat = reponse.json()["data"]["result"]
    if not resultat:
        return {}
    return {t: (v if v == v else 0.0) for t, v in ((t, float(v)) for t, v in resultat[0]["values"])}


def releves_historiques(minutes):
    """Relevés des `minutes` passées, un toutes les POLL_INTERVAL_SECONDS (mêmes colonnes que
    releve_actuel). On ne garde que les instants SAINS : sans 5xx et sonde OK, pour ne pas
    apprendre une attaque ou une panne passée comme « normale »."""
    # Prometheus refuse plus de 11 000 points par série.
    assert minutes * 60 / config.POLL_INTERVAL_SECONDS <= 11000, "plage trop longue"
    fin = time.time()
    debut = fin - minutes * 60
    series = {nom: _serie(q, debut, fin) for nom, q in config.QUERIES.items()}
    releves = [
        {nom: series[nom].get(t, 0.0) for nom in config.QUERIES} for t in sorted(series["req_rate"])
    ]
    return [
        r
        for r in releves
        if r["error_rate"] == 0 and r["probe_success"] == 1 and r["probe_failures_rate"] == 0
    ]


def noms_features():
    """La liste ordonnée des colonnes, pour le CSV et le modèle."""
    return list(config.QUERIES.keys())


def top_source_ip():
    """IP source dominante sur la dernière minute, ou None si pas de données.

    Sert à remplir le champ src_ip de l'alerte (block_ip côté remédiation).
    On lit l'ÉTIQUETTE src_ip de la première série, pas sa valeur.
    """
    url = f"{config.PROMETHEUS_URL}/api/v1/query"
    try:
        reponse = requests.get(url, params={"query": config.SOURCE_IP_QUERY}, timeout=5)
        reponse.raise_for_status()
        resultat = reponse.json()["data"]["result"]
        return resultat[0]["metric"].get("src_ip") if resultat else None
    except Exception as e:
        print(f"[prom] top_source_ip en échec: {e}")
        return None
