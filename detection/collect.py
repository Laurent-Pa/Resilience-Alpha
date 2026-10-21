# ===================================================================
# ÉTAPE 1 — COLLECTER DU TRAFIC NORMAL
# À lancer QUAND TOUT VA BIEN (trafic normal, prober qui tourne).
# Enregistre un relevé toutes les X secondes dans un fichier CSV.
# Ce CSV servira à entraîner le modèle à reconnaître "le normal".
#
# Usage :  python collect.py 10       (collecte pendant 10 minutes)
# ===================================================================
import csv
import sys
import time

import config
import prom


def main():
    # Durée de collecte en minutes (par défaut 10).
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    fin = time.time() + minutes * 60

    colonnes = prom.noms_features()
    print(
        f"Collecte de trafic normal pendant {minutes} min "
        f"(un relevé toutes les {config.POLL_INTERVAL_SECONDS} s)..."
    )
    print("👉 Génère du trafic NORMAL pendant ce temps (pas d'attaque).")

    with open(config.DATA_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=colonnes)
        writer.writeheader()
        n = 0
        while time.time() < fin:
            releve = prom.releve_actuel()
            writer.writerow(releve)
            f.flush()
            n += 1
            print(f"  relevé {n}: {releve}")
            time.sleep(config.POLL_INTERVAL_SECONDS)

    print(f"\n✅ {n} relevés enregistrés dans {config.DATA_FILE}")
    print("Étape suivante :  python train.py")


if __name__ == "__main__":
    main()
