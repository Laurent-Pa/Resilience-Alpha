# ./vault/config.hcl
listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/vault/certs/vault.crt"
  tls_key_file  = "/vault/certs/vault.key"
}

storage "file" {
  path = "/vault/file"
}

api_addr     = "https://vault:8200"
cluster_addr = "https://vault:8201"
ui           = true

# Sécuriser les logs
log_level = "info"
