from pydantic import SecretStr

from resilience_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "remediation-engine"

    # Secret HMAC de POST /alerts : fichier $SECRETS_DIR/webhook_hmac_key (Vault). Obligatoire.
    webhook_hmac_key: SecretStr | None = None
    # Jeton bearer alternatif pour POST /alerts : Alertmanager ne sait pas signer un corps.
    # Fichier $SECRETS_DIR/alertmanager_token (Vault). Absent : seule la signature HMAC passe.
    alertmanager_token: SecretStr | None = None

    # Audience attendue dans les JWT ops (endpoints /incidents, /events, /stats).
    oidc_audience: str = "remediation-engine"

    # Composants : fake par défaut (dev local sans infra). Prod : ansible + real.
    executor: str = "fake"  # fake | ansible
    verifier: str = "fake"  # fake | real

    # AnsibleExecutor : playbooks de l'infra (block_ip.yml, recycle_service.yml, kill_db_conns.yml).
    playbooks_dir: str = "/playbooks"
    action_timeout_s: float = 60

    prober_status_url: str = "http://prober:8000/status"
    ledger_url: str = "https://192.168.137.1/api/admin/ledger/check"
    # Bundle CA du certificat de labo du WAF (ledger_url) ; None : magasin système.
    ca_bundle: str | None = None

    # Jeton ops du verifier (ledger_check) : client confidentiel `remediation-engine`.
    kc_token_url: str = "http://keycloak:8080/auth/realms/resilience/protocol/openid-connect/token"  # noqa: S105
    client_id: str = "remediation-engine"
    # Secret : $SECRETS_DIR/remediation_client_secret (Vault).
    remediation_client_secret: SecretStr | None = None

    # Persistance (schéma `remediation`). db_host absent : store en mémoire (tests, dev nu).
    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "resilience"
    db_user: str = "payment_app"
    # Secret : $SECRETS_DIR/db_password.
    db_password: SecretStr | None = None

    cooldown_s: float = 120
    flapping_max: int = 3
    flapping_window_s: float = 600
