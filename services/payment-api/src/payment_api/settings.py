from pydantic import SecretStr
from sqlalchemy import URL

from resilience_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "payment-api"
    oidc_audience: str = "payment-api"

    cors_origins: list[str] = ["http://localhost:3000"]  # noqa: RUF012 (pydantic copie le défaut)

    db_host: str = "postgres"
    db_port: int = 5432
    db_name: str = "resilience"
    db_user: str = "payment_app"
    # Secret : lu depuis $SECRETS_DIR/db_password.
    db_password: SecretStr | None = None
    # Remplace la construction ci-dessus si fourni (tests, outillage local).
    database_url: str | None = None

    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_s: float = 2.0
    db_statement_timeout_ms: int = 5000

    # Secret : $SECRETS_DIR/iban_hmac_key. Obligatoire (empreinte des IBAN en base).
    iban_hmac_key: SecretStr | None = None
    # Secret : $SECRETS_DIR/rsa_private_key (PEM PKCS#8). Absent : clé éphémère générée
    # au démarrage, ce qui invalide la clé publique en cache côté front à chaque redémarrage.
    rsa_private_key: SecretStr | None = None

    seed_on_start: bool = True

    def db_url(self) -> URL | str:
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value() if self.db_password else None,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
