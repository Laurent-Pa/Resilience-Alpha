from pydantic import SecretStr

from resilience_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "prober"

    # Keycloak en interne ; le virement, lui, passe par le WAF comme un vrai client.
    kc_token_url: str = "http://keycloak:8080/auth/realms/resilience/protocol/openid-connect/token"  # noqa: S105
    client_id: str = "prober"
    # Secret : $SECRETS_DIR/prober_client_secret (Vault).
    prober_client_secret: SecretStr | None = None

    target_url: str = "https://192.168.137.1"
    # Bundle CA du certificat de labo du WAF (None : magasin système).
    ca_bundle: str | None = None

    # IBAN fictif de PROBE_SINK (seed de payment-api).
    probe_dst_iban: str = "FR7699999000019000000000247"
    probe_dst_name: str = "PROBE_SINK"

    interval_s: float = 5.0
    timeout_s: float = 3.0
