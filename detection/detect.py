# ===================================================================
# ÉTAPE 3 — DÉTECTER EN DIRECT
# Boucle sans fin : lit les métriques actuelles, demande au modèle
# "normal ou anomalie ?", et déclenche la remédiation si l'anomalie
# persiste plusieurs relevés d'affilée.
#
# Usage :  python detect.py
# ===================================================================
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
import requests

import config
import prom
import signing


def _secret_hmac() -> bytes:
    """Secret HMAC (octets) : fichier d'abord, sinon variable d'env. Lève si introuvable."""
    chemin = Path(config.HMAC_SECRET_FILE)
    if chemin.is_file():
        return chemin.read_text().strip().encode()
    if env := os.getenv("WEBHOOK_HMAC_SECRET"):
        return env.strip().encode()
    raise RuntimeError(
        f"secret HMAC introuvable ({config.HMAC_SECRET_FILE} ni $WEBHOOK_HMAC_SECRET) : "
        "requis pour signer POST /alerts"
    )


def declencher_remediation(releve, src_ip, debut_anomalie):
    """Prévient le moteur qu'une anomalie est confirmée (alerte conforme alert.schema.json).

    src_ip = IP source dominante à bloquer (ou None). debut_anomalie = datetime du 1er relevé
    anormal de la série (base du MTTD côté moteur).
    """
    alerte = {
        "source": "ml",
        "type": "anomaly",
        "target": config.TARGET_SERVICE,
        "src_ip": src_ip,
        "features": releve,
        "at": debut_anomalie.isoformat(),
    }
    print(f"🚨 ANOMALIE CONFIRMÉE (src_ip={src_ip}) -> déclenchement de la remédiation")
    if not config.REMEDIATION_URL:
        print("   (REMEDIATION_URL vide : rien à appeler pour l'instant)")
        return
    # Signer les octets EXACTEMENT envoyés : on sérialise une fois, on signe, on poste ces octets.
    corps = json.dumps(alerte).encode()
    try:
        requests.post(
            config.REMEDIATION_URL,
            data=corps,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signing.signer(_secret_hmac(), corps),
            },
            timeout=5,
        )
        print(f"   remédiation notifiée : {config.REMEDIATION_URL}")
    except Exception as e:
        print(f"   échec de notification : {e}")


def main():
    # 1. Charger le modèle entraîné.
    paquet = joblib.load(config.MODEL_FILE)
    modele = paquet["modele"]
    colonnes = paquet["colonnes"]
    print(f"Modèle chargé. Surveillance toutes les "
          f"{config.POLL_INTERVAL_SECONDS} s. Ctrl+C pour arrêter.\n")

    anomalies_consecutives = 0
    debut_anomalie = None  # datetime du 1er relevé anormal de la série en cours

    # 2. Boucle de surveillance.
    while True:
        releve = prom.releve_actuel()
        X = pd.DataFrame([releve])[colonnes]

        # predict renvoie 1 = normal, -1 = anomalie.
        prediction = modele.predict(X)[0]
        # score_samples : plus c'est bas, plus c'est anormal (pour info).
        score = modele.score_samples(X)[0]

        if prediction == -1:
            if anomalies_consecutives == 0:
                debut_anomalie = datetime.now(UTC)  # horodate le début de la série
            anomalies_consecutives += 1
            etat = f"⚠️  ANORMAL ({anomalies_consecutives}/{config.CONSECUTIVE_ANOMALIES})"
        else:
            anomalies_consecutives = 0
            debut_anomalie = None
            etat = "✅ normal"

        print(f"{etat}  score={score:.3f}  {releve}")

        # 3. Anomalie persistante -> remédiation, puis on remet le compteur à 0.
        if anomalies_consecutives >= config.CONSECUTIVE_ANOMALIES:
            declencher_remediation(releve, prom.top_source_ip(), debut_anomalie)
            anomalies_consecutives = 0

        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
