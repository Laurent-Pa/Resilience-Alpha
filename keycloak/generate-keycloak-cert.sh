#!/bin/bash
set -euo pipefail

KEYCLOAK_CERT_PATH="./keycloak/certs"
mkdir -p "$KEYCLOAK_CERT_PATH"

# Générer une clé privée et un certificat auto-signé pour Keycloak (dev, HTTPS sur :8443).
# SAN requis : les navigateurs/clients modernes ignorent le CN seul. On passe par un fichier
# de config temporaire plutôt que par `-addext` : certains builds d'OpenSSL fournis avec
# Git for Windows ne le supportent pas et plantent après avoir écrit la clé mais avant le
# certificat (symptôme : keycloak.key présent, keycloak.crt absent).
EXT_CONF="$(mktemp)"
trap 'rm -f "$EXT_CONF"' EXIT

cat > "$EXT_CONF" <<'EOF'
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = localhost

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

openssl req -x509 -newkey rsa:4096 \
    -keyout "$KEYCLOAK_CERT_PATH/keycloak.key" \
    -out "$KEYCLOAK_CERT_PATH/keycloak.crt" \
    -days 365 -nodes \
    -config "$EXT_CONF"

echo "✓ Certificat Keycloak généré dans $KEYCLOAK_CERT_PATH"
