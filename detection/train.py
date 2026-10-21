# ===================================================================
# ÉTAPE 2 — ENTRAÎNER LE MODÈLE
# Lit le CSV de trafic normal et apprend au modèle "à quoi ressemble
# le normal". Sauvegarde le modèle entraîné dans model.joblib.
#
# Modèle : Isolation Forest (détection d'anomalies NON supervisée).
#   -> on ne lui montre QUE du normal ;
#   -> ensuite il repère tout seul ce qui s'en écarte.
#
# Usage :  python train.py
# ===================================================================
import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import config
import prom


def main():
    # 1. Charger les relevés de trafic normal.
    data = pd.read_csv(config.DATA_FILE)
    colonnes = prom.noms_features()
    X = data[colonnes]
    print(f"Entraînement sur {len(X)} relevés, {len(colonnes)} signaux.")

    # 2. Construire le modèle.
    #    - StandardScaler : met toutes les métriques à la même échelle
    #      (sans ça, le débit en milliers écraserait le 0/1 du probe_success).
    #    - IsolationForest : le détecteur d'anomalies.
    #      contamination="auto" = il estime lui-même la part d'anomalies.
    modele = make_pipeline(
        StandardScaler(),
        IsolationForest(
            n_estimators=200,
            contamination="auto",
            random_state=42,
        ),
    )

    # 3. Entraîner et sauvegarder.
    modele.fit(X)
    # Remplace le seuil par défaut (-0.5) : predict() renvoie -1 si score < offset_.
    modele[-1].offset_ = config.SEUIL_SCORE
    joblib.dump({"modele": modele, "colonnes": colonnes}, config.MODEL_FILE)

    print(f"✅ Modèle entraîné et sauvegardé dans {config.MODEL_FILE}")
    print("Étape suivante :  python detect.py")


if __name__ == "__main__":
    main()
