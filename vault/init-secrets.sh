#!/bin/sh
# ./vault/init-secrets.sh
# Initialiser Vault en mode production avec unsealing manuel

export VAULT_ADDR=https://vault:8200
export VAULT_SKIP_VERIFY=true

echo "========================================"
echo "Initialisation de Vault en production"
echo "========================================"

# Attendre que Vault soit prêt
echo "En attente du démarrage de Vault..."
sleep 5

# Vérifier l'état de Vault
VAULT_STATUS=$(vault status 2>&1)
if echo "$VAULT_STATUS" | grep -q "Sealed.*true"; then
    echo "⚠ Vault est scellé (Sealed: true)"
    echo ""
    echo "=== IMPORTANT : UNSEAL MANUAL REQUIS ==="
    echo "Vault est en mode production. Vous devez le désceller manuellement :"
    echo ""
    echo "1. Initialiser Vault (génère les clés d'unseal) :"
    echo "   docker exec -it \$(docker ps -q -f 'name=vault') vault operator init -key-shares=1 -key-threshold=1"
    echo ""
    echo "2. Désceller Vault :"
    echo "   docker exec -it \$(docker ps -q -f 'name=vault') vault operator unseal <unseal-key>"
    echo ""
    echo "3. S'authentifier :"
    echo "   export VAULT_TOKEN=<root-token>"
    echo ""
    echo "4. Relancer l'initialisation :"
    echo "   docker exec -it \$(docker ps -q -f 'name=vault') sh /vault/init-secrets.sh"
    echo "========================================"
    exit 0
fi

# Si Vault est déjà initialisé et déscellé
if echo "$VAULT_STATUS" | grep -q "Sealed.*false"; then
    echo "✓ Vault est déscellé et prêt"
    
    # Vérifier que le token est fourni
    if [ -z "$VAULT_TOKEN" ]; then
        echo "✗ Erreur : VAULT_TOKEN non défini"
        exit 1
    fi
    
    # Créer le chemin des secrets
    echo "Initialisation des secrets dans Vault..."
    vault kv put secret/resilience \
      db_password="$(cat /opt/.secrets/db_password 2>/dev/null || echo 'placeholder')" \
      iban_hmac_key="$(cat /opt/.secrets/iban_hmac_key 2>/dev/null || echo 'placeholder')" \
      rsa_private_key="$(cat /opt/.secrets/rsa_private_key 2>/dev/null || echo 'placeholder')" \
      prober_client_secret="$(cat /opt/.secrets/prober_client_secret 2>/dev/null || echo 'placeholder')"
    
    if [ $? -eq 0 ]; then
        echo "✓ Secrets initialisés dans Vault"
        vault kv list secret/
    else
        echo "✗ Erreur lors de l'initialisation des secrets"
        exit 1
    fi
fi
