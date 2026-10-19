"""Configuration commune.

Les valeurs non sensibles viennent des variables d'environnement. Les secrets sont lus
depuis des fichiers (un fichier par champ, nommé comme le champ) dans `SECRETS_DIR`,
par défaut `/run/secrets` (Docker secrets ou Vault Agent).
"""

import os
from pathlib import Path
from typing import Self

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRETS_DIR = "/run/secrets"


def secrets_dir() -> Path | None:
    path = Path(os.environ.get("SECRETS_DIR", DEFAULT_SECRETS_DIR))
    return path if path.is_dir() else None


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_name: str = "service"
    log_level: str = "INFO"

    # Émetteur public (vu par le navigateur via le WAF) ≠ URL interne du JWKS.
    oidc_issuer: str = "https://192.168.137.1/auth/realms/resilience"
    oidc_jwks_url: str = "http://keycloak:8080/auth/realms/resilience/protocol/openid-connect/certs"

    @classmethod
    def load(cls, **overrides: object) -> Self:
        """Construit la configuration en lisant aussi les fichiers de secrets."""
        return cls(_secrets_dir=secrets_dir(), **overrides)  # type: ignore[call-arg]
