# Bloc Observabilité — Workshop RESILIENCE-ALPHA

Stack : **Prometheus + Grafana + Loki** (base obligatoire du sujet).

## Contenu du dossier

```
observability/
├── docker-compose.observability.yml   ← le fichier à lancer
├── prometheus/
│   └── prometheus.yml                 ← quoi surveiller
├── loki/
│   └── loki-config.yml                ← config du stockage de logs
├── grafana/
│   └── provisioning/
│       └── datasources/
│           └── datasources.yml        ← branche Prometheus + Loki auto
└── README.md
```

## Secrets locaux (temporaire)

En attendant que Vault soit opérationnel et gère ce secret pour tout le monde, le mot de passe admin Grafana est lu dans `.secrets/grafana_admin_password` **à la racine du dépôt** (fichier gitignoré, jamais commité). Mot de passe de dev par défaut, depuis la racine :

```bash
printf '%s' 'TestPassword123' > .secrets/grafana_admin_password
```

Grafana n'applique ce mot de passe qu'à la création du volume `grafana_data`. Pour le changer ensuite :
`docker exec grafana grafana cli admin reset-admin-password <mdp>`.

## Démarrer

Depuis le dossier `observability/` :

```
docker compose -f docker-compose.observability.yml up -d
```

## Accès (dans le navigateur)

| Service     | Adresse                  | Identifiants      |
|-------------|--------------------------|-------------------|
| Grafana     | http://localhost:3001    | voir .secrets /vault    |
| Prometheus  | http://localhost:9090    | —                 |
| Loki        | http://localhost:3100    | (pas d'interface) |

## Vérifier que ça marche

1. Grafana → http://localhost:3001 (admin/admin)
2. Menu → Connections → Data sources : Prometheus et Loki doivent être là, en vert.
3. Prometheus → http://localhost:9090 → Status → Targets : le job `prometheus` doit être "UP".

## Arrêter

```
docker compose -f docker-compose.observability.yml down
```

Ajouter `-v` pour supprimer aussi les données stockées.

## À FAIRE avec l'équipe DEV (point bloquant pour la fusion)

Avant d'intégrer au Compose du PC Hôte, figer ensemble :
- le **nom des conteneurs** métier (api, auth, db...) et leurs **ports** ;
- le fait que l'**API expose bien un endpoint `/metrics`** au format Prometheus ;
- le **nom du réseau Docker partagé**.

Puis décommenter et adapter les blocs `job_name` dans `prometheus/prometheus.yml`.

## Collecte des logs (Loki)

Loki stocke mais ne collecte pas seul. Sur le Compose final, ajouter à chaque
conteneur métier le driver de log Loki, par ex :

```yaml
    logging:
      driver: loki
      options:
        loki-url: "http://localhost:3100/loki/api/v1/push"
```

(nécessite d'installer le plugin : `docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions`)
