from pydantic import Field, SecretStr

from resilience_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "face-auth"
    # Audience des JWT ops du back-office (mapper `aud-face-auth` du client web-ops).
    oidc_audience: str = "face-auth"

    cors_origins: list[str] = ["http://localhost:3000"]  # noqa: RUF012 (pydantic copie le défaut)

    # Secret : $SECRETS_DIR/face_service_token. Jeton partagé avec l'authenticator Keycloak
    # (routes /internal). Obligatoire.
    face_service_token: SecretStr | None = None
    # Secret : $SECRETS_DIR/biometric_key (hex, 32 octets). Chiffre les empreintes au repos
    # (AES-256-GCM). Obligatoire ; la changer rend les enrôlements existants illisibles.
    biometric_key: SecretStr | None = None

    # Modèles ONNX (téléchargés dans l'image au build).
    models_dir: str = "/app/models"
    # Similarité cosinus SFace : 0.363 est le seuil de référence d'OpenCV (LFW).
    match_threshold: float = Field(default=0.363, gt=0, lt=1)

    # Verrouillage : `max_failures` échecs consécutifs -> bloqué `lock_s` secondes.
    # Consigne : « peut recommencer 1 fois puis est bloqué 5 minutes ».
    max_failures: int = Field(default=2, ge=1)
    lock_s: float = Field(default=300, gt=0)

    # Persistance (schéma `biometrics`). db_host absent : mémoire (tests, dev nu).
    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "resilience"
    db_user: str = "payment_app"
    # Secret : $SECRETS_DIR/db_password.
    db_password: SecretStr | None = None
