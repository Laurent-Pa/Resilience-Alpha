#!/bin/bash

VAULT_CERT_PATH="./vault/certs"
mkdir -p "$VAULT_CERT_PATH"

# Générer une clé privée et certificat pour Vault
openssl req -x509 -newkey rsa:4096 \
    -keyout "$VAULT_CERT_PATH/vault.key" \
    -out "$VAULT_CERT_PATH/vault.crt" \
    -days 365 -nodes \
    -subj "/CN=vault"

echo "✓ Certificat Vault généré"
