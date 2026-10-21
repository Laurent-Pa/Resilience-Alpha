from pydantic import SecretStr

from resilience_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "remediation-engine"

    # Secret HMAC de POST /alerts : fichier $SECRETS_DIR/webhook_hmac_key (Vault). Obligatoire.
    webhook_hmac_key: SecretStr | None = None

    # Audience attendue dans les JWT ops (endpoints /incidents, /events, /stats).
    oidc_audience: str = "remediation-engine"

    # Composants : tout en fake par défaut (dev local, étape 5). real/ansible = étape 7.
    executor: str = "fake"  # fake | ansible
    verifier: str = "fake"  # fake | real

    prober_status_url: str = "http://prober:8000/status"
    ledger_url: str = "https://192.168.137.1/api/admin/ledger/check"

    cooldown_s: float = 120
    flapping_max: int = 3
    flapping_window_s: float = 600
