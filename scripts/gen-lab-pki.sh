#!/bin/bash
# PKI de labo du PC Hôte : une autorité de certification (CA) locale + le certificat
# serveur du WAF signé par cette CA, pour l'adresse publique PUBLIC_HOST (lue dans .env).
#
# Pourquoi une CA plutôt qu'un simple certificat auto-signé : on importe UNE fois la CA
# dans Windows (plus d'avertissement navigateur) et on la donne en CA_BUNDLE au prober et
# au moteur de remédiation (vérification TLS réelle, jamais verify=False). Si PUBLIC_HOST
# change, seul le certificat du WAF est régénéré : la CA déjà importée reste valable.
#
# Sorties (dossier certs/, gitignoré) :
#   lab-ca.key, lab-ca.pem   CA ; lab-ca.key ne doit JAMAIS quitter le PC Hôte
#   waf.key,    waf.crt      certificat serveur du WAF (SAN : PUBLIC_HOST, localhost, 127.0.0.1)
#
# Usage : bash scripts/gen-lab-pki.sh [PUBLIC_HOST]   (défaut : valeur de .env)
#
# Compatibilité Git Bash (Windows) : pas de -subj (MSYS réécrit "/CN=..." en chemin
# Windows) ni de -addext (absent de certains builds) ; tout passe par des fichiers de config.
set -euo pipefail
cd "$(dirname "$0")/.."

PUBLIC_HOST="${1:-}"
if [ -z "$PUBLIC_HOST" ] && [ -f .env ]; then
  PUBLIC_HOST="$(grep -E '^PUBLIC_HOST=' .env | tail -n 1 | cut -d= -f2- | tr -d '\r" ')"
fi
if [ -z "$PUBLIC_HOST" ]; then
  echo "PUBLIC_HOST absent : copier .env.example en .env et le renseigner." >&2
  exit 1
fi
if [ "$PUBLIC_HOST" = "localhost" ] || [ "$PUBLIC_HOST" = "127.0.0.1" ]; then
  echo "PUBLIC_HOST=$PUBLIC_HOST refusé : dans un conteneur, localhost désigne le conteneur" >&2
  echo "lui-même (le prober ne joindrait pas le WAF). Utiliser une IPv4 du PC (ipconfig)." >&2
  exit 1
fi

if [[ "$PUBLIC_HOST" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  HOST_SAN="IP.2 = $PUBLIC_HOST"
else
  HOST_SAN="DNS.2 = $PUBLIC_HOST"
fi

CERT_DIR="certs"
mkdir -p "$CERT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# --- 1. CA (créée une seule fois) -------------------------------------------------------
if [ -f "$CERT_DIR/lab-ca.pem" ] && [ -f "$CERT_DIR/lab-ca.key" ]; then
  echo "• CA existante conservée : $CERT_DIR/lab-ca.pem"
else
  cat > "$TMP_DIR/ca.cnf" <<'EOF'
[req]
distinguished_name = dn
x509_extensions = v3_ca
prompt = no

[dn]
CN = Resilience-Alpha Lab CA
O = Resilience-Alpha

[v3_ca]
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
EOF
  openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout "$CERT_DIR/lab-ca.key" -out "$CERT_DIR/lab-ca.pem" \
    -days 825 -config "$TMP_DIR/ca.cnf"
  echo "✓ CA créée : $CERT_DIR/lab-ca.pem (à importer dans Windows, voir README)"
fi

# --- 2. Certificat serveur du WAF (régénéré à chaque exécution) --------------------------
cat > "$TMP_DIR/waf.cnf" <<EOF
[req]
distinguished_name = dn
req_extensions = v3_req
prompt = no

[dn]
CN = $PUBLIC_HOST
O = Resilience-Alpha

[v3_req]
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt

[alt]
DNS.1 = localhost
IP.1 = 127.0.0.1
$HOST_SAN
EOF

openssl req -new -newkey rsa:2048 -nodes \
  -keyout "$CERT_DIR/waf.key" -out "$TMP_DIR/waf.csr" -config "$TMP_DIR/waf.cnf"
openssl x509 -req -in "$TMP_DIR/waf.csr" \
  -CA "$CERT_DIR/lab-ca.pem" -CAkey "$CERT_DIR/lab-ca.key" -CAcreateserial \
  -out "$CERT_DIR/waf.crt" -days 397 \
  -extfile "$TMP_DIR/waf.cnf" -extensions v3_req

openssl verify -CAfile "$CERT_DIR/lab-ca.pem" "$CERT_DIR/waf.crt"
echo "✓ Certificat du WAF pour $PUBLIC_HOST : $CERT_DIR/waf.crt"
