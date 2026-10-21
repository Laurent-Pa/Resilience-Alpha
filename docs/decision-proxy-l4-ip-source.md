# Décision : un proxy L4 sur le PC Hôte pour conserver l'IP réelle des clients

| | |
| --- | --- |
| **Statut** | Accepté (21/10/2026) |
| **Portée** | PC Hôte de démo (`compose.yaml`) ; sans effet sur `compose.dev.yaml` |
| **Fichiers** | [`edge/nginx.conf`](../edge/nginx.conf), [`scripts/edge-proxy.ps1`](../scripts/edge-proxy.ps1), [`waf/nginx/default.conf.template`](../waf/nginx/default.conf.template), service `waf` de [`compose.yaml`](../compose.yaml) |
| **Procédure** | README, « Déploiement sur le PC Hôte », étape 3 |

## 1. Contexte

Le scénario de démonstration retenu est le suivant : une attaque DDoS est lancée depuis le PC Attaquant. Elle est détectée (ML sur les métriques, règles Prometheus). Le moteur de remédiation **bloque alors l'IP de l'attaquant au WAF** (`block_ip`), puis la sonde prouve le retour du service par un virement réussi.

Toute cette chaîne repose sur une condition : **le WAF doit voir l'IP réelle du client**. Il pose cette IP dans `X-Forwarded-For` / `X-Real-IP`. Les services en tirent `src_ip` dans leurs journaux et la métrique `http_requests_by_source_total{src_ip}`. La détection et `block_ip` s'appuient sur ce label.

## 2. Constat

Le test a été mené le 21/10 sur le PC Hôte. Le WAF était publié normalement (`ports: ["443:8443"]`). Une requête envoyée depuis un téléphone du réseau local a été journalisée avec `"src_ip":"172.19.0.1"`, comme les requêtes faites depuis le PC lui-même.

`172.19.0.1` est la passerelle du réseau Docker. **Docker Desktop fait passer toute connexion entrante sur un port publié par son propre relais réseau, et l'IP d'origine est perdue.** C'est une limite connue de Docker Desktop sous Windows et macOS, et non un défaut de notre configuration. Ses propres réglages n'y changent rien :

- le « host networking » de Docker Desktop (version 4.34 et suivantes) ne conserve pas l'IP source ;
- le réseau WSL `networkingMode=mirrored` n'agit pas sur Docker Desktop, qui gère son réseau indépendamment de WSL.

Si on ne corrige pas ce point, le jour de la démo :

- **la détection ne peut désigner aucune IP**, puisque tout le trafic, légitime ou malveillant, vient de la même adresse ;
- **`block_ip` bloquerait `172.19.0.1`, donc tout le monde**, sonde comprise : la remédiation provoquerait la panne qu'elle doit corriger ;
- **les journaux ne permettraient pas d'établir l'origine de l'attaque**, ce qui pose un problème d'investigation et de traçabilité.

## 3. Décision

On place **un proxy de niveau 4 sur Windows, hors de Docker**. Il est réalisé avec **nginx pour Windows** et :

- écoute le port **443** du PC Hôte ;
- **ne déchiffre rien** : il relaie le flux TCP/TLS tel quel vers le WAF, publié uniquement sur `127.0.0.1:8443` ;
- ajoute en tête de chaque connexion un en-tête **PROXY protocol** (`PROXY TCP4 <ip client> ...`) qui porte l'IP d'origine.

Le WAF :

- **exige** cet en-tête (`listen 8443 ssl proxy_protocol`) et refuse toute connexion qui ne le porte pas ;
- en fait son `$remote_addr` (`real_ip_header proxy_protocol`), en ne faisant confiance qu'aux relais du réseau Docker / Docker Desktop (`set_real_ip_from`) ;
- **écrase** ensuite `X-Forwarded-For` / `X-Real-IP` avec cette IP. Un en-tête forgé par l'attaquant ne peut donc pas faire accuser une autre adresse.

```
Client ──TCP 443──▶ nginx Windows (relais L4, ajoute PROXY <ip réelle>)
                      └──▶ 127.0.0.1:8443 ──▶ Docker Desktop ──▶ WAF (TLS + ModSecurity)
                                                                  └──▶ services (X-Forwarded-For = ip réelle)
```

L'IP réelle n'existe qu'au moment où la connexion arrive sur Windows : dès qu'elle entre dans Docker Desktop, elle est perdue. C'est pourquoi le composant doit tourner **sur l'hôte, avant Docker**, et pourquoi aucune configuration à l'intérieur des conteneurs ne peut le remplacer.

## 4. Pourquoi nginx

- **Ce n'est pas une nouvelle technologie dans le projet.** Le WAF *est* déjà un nginx (image `owasp/modsecurity-crs` : nginx + ModSecurity + OWASP CRS). Le même logiciel est réutilisé devant lui, dans un rôle de relais TCP simple, en une vingtaine de lignes de configuration.
- **Rien à installer** : c'est le zip officiel de nginx.org. Il n'y a ni service Windows ni modification du système, et il n'y a pas besoin de droits d'administrateur pour écouter le 443.
- **Surface minimale** : le relais ne déchiffre rien, ne voit aucun contenu applicatif et n'a aucun accès aux conteneurs ni à Docker.
- **Conforme au sujet** : celui-ci autorise « les bibliothèques, images et outils publics ». Aucune technologie prescrite n'est remplacée : Docker Desktop avec WSL2, Docker Compose et le WAF restent en place.

## 5. Alternatives écartées

| Option | Pourquoi elle est écartée |
| --- | --- |
| Garder la publication directe du WAF | `block_ip` bloquerait la passerelle, donc tout le trafic. Le scénario devient impossible, voire dangereux. |
| Docker Engine (`docker-ce`) dans une distribution WSL2, réseau « mirrored » | Conserve l'IP nativement, mais impose de réinstaller tout l'environnement Docker et s'écarte du « Docker Desktop avec WSL2 » prescrit. C'est trop risqué à deux jours du gel du code. |
| Mode « host networking » de Docker Desktop | Ne conserve pas l'IP source sous Windows (les connexions apparaissent depuis `127.0.0.1`). |
| Changer de scénario (panne de service → `recycle_service` / `kill_db_conns`, sans blocage d'IP) | N'a plus besoin du relais, mais renonce au blocage de l'attaquant, qui est le moment le plus démonstratif. L'équipe a choisi de **conserver le scénario**. |
| Autre relais L4 sous Windows (HAProxy, etc.) | Pas de version Windows officielle simple. nginx est déjà maîtrisé grâce au WAF. |

## 6. Conséquences

- **Un processus de plus à démarrer le jour J** : `scripts/edge-proxy.ps1 start`, en plus de `docker compose up -d`. Sans lui, plus rien ne répond sur le 443. C'est un point unique de défaillance, au même titre que le WAF qu'il précède. Il doit figurer dans la check-list de démarrage et dans le PCA/PRA.
- **Pare-feu Windows** : au premier démarrage, il faut autoriser `nginx.exe` sur les réseaux privés **et** publics, car le point d'accès mobile peut être classé « public ».
- **Capacité** : nginx pour Windows plafonne à environ 1024 connexions simultanées. Sous un flood massif, le relais peut saturer avant le WAF. Le blocage de l'IP au WAF referme alors au fil de l'eau les connexions de l'attaquant. C'est une limite à mentionner dans les résultats d'essais.
- **Contournement impossible depuis le réseau** : le WAF n'est publié que sur `127.0.0.1` et refuse les connexions sans en-tête PROXY.
- **Environnement de dev inchangé** : `compose.dev.yaml` n'a pas de WAF. On y simule l'IP source avec `scripts/flood.py --xff`.

## 7. Vérification

À refaire après tout changement réseau, et avant la démo :

1. Relais démarré (`scripts/edge-proxy.ps1 status` : port 443 à l'écoute).
2. Depuis un autre appareil du réseau (téléphone, puis PC Attaquant), ouvrir `https://<PUBLIC_HOST>/api/payments/public-key`.
3. `docker compose logs waf | grep '"service":"waf"' | tail -3` : `src_ip` doit être l'IP **de cet appareil**. Une adresse en `172.x` ou `192.168.65.x` signifie que la requête n'est pas passée par le relais.

## 8. Ce qu'on peut en dire au jury

On ajoute un équilibreur de niveau 4 devant le WAF : c'est un schéma classique en production, où un load-balancer TCP transmet l'IP d'origine au WAF par PROXY protocol. Ici, il compense une limite documentée de Docker Desktop, qui masque l'IP des clients. Sans lui, la remédiation « bloquer l'attaquant » bloquerait tout le monde. La décision a été prise **sur la base d'une mesure** (le test du téléphone en `172.19.0.1`), et sa vérification fait partie de la recette.
