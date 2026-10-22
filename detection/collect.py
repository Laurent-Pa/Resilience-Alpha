# ===================================================================
# ÉTAPE 1 — COLLECTER DU TRAFIC NORMAL
# À lancer QUAND TOUT VA BIEN (trafic normal, prober qui tourne).
# Enregistre un relevé toutes les X secondes dans un fichier CSV.
# Ce CSV servira à entraîner le modèle à reconnaître "le normal".
#
# Usage :  python collect.py 10              (collecte pendant 10 minutes)
#          python collect.py --history 120   (reprend les 120 dernières min de Prometheus)
# ===================================================================
import csv
import sys
import time

import config
import prom


def depuis_historique(minutes):
    """Reconstruit le CSV depuis l'historique Prometheus, sans attendre (instants sains seulement)."""
    releves = prom.releves_historiques(minutes)
    with open(config.DATA_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=prom.noms_features())
        writer.writeheader()
        writer.writerows(releves)
    print(f"✅ {len(releves)} relevés sains des {minutes:.0f} dernières min -> {config.DATA_FILE}")
    print("Étape suivante :  python train.py")


def main():
    # --history N : reprendre les N dernières minutes de Prometheus au lieu de collecter en direct.
    if len(sys.argv) > 2 and sys.argv[1] == "--history":
        return depuis_historique(float(sys.argv[2]))
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
