from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from payment_api.domain import bic, iban
from payment_api.domain.rules import InvalidPayload

MAX_AMOUNT_CENTS = 100_000_000  # 1 000 000 €


class TransferEnvelope(BaseModel):
    """Corps de POST /payments/transfer. Les coordonnées du bénéficiaire sont chiffrées ;
    le montant, non sensible, reste en clair. Le compte débité est celui du porteur du
    jeton (un compte par personne)."""

    model_config = ConfigDict(extra="forbid")

    amount_cents: int = Field(gt=0, le=MAX_AMOUNT_CENTS, description="Montant en centimes")
    encrypted_key: str = Field(
        max_length=1024, description="Clé AES-256 chiffrée en RSA-OAEP SHA-256, base64"
    )
    iv: str = Field(max_length=32, description="IV AES-GCM de 12 octets, base64")
    ciphertext: str = Field(
        max_length=4096,
        description=(
            "JSON {iban, bic?, account_holder_name} chiffré en AES-GCM "
            "(ciphertext || tag de 16 octets, comme WebCrypto), base64"
        ),
    )


class Beneficiary(BaseModel):
    """Contenu déchiffré. Jamais journalisé ni renvoyé ; seul l'IBAN masqué est persisté."""

    model_config = ConfigDict(extra="ignore")

    iban: str = Field(min_length=15, max_length=50)
    bic: str | None = Field(default=None, max_length=20)
    account_holder_name: str = Field(min_length=1, max_length=70)

    @field_validator("iban")
    @classmethod
    def _normalize_iban(cls, v: str) -> str:
        return iban.normalize(v)

    @field_validator("bic")
    @classmethod
    def _normalize_bic(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return bic.normalize(v) or None  # chaîne vide = BIC non fourni

    @classmethod
    def parse(cls, plaintext: bytes) -> "Beneficiary":
        """Erreur générique, sans écho des valeurs reçues (pas de fuite dans la réponse)."""
        try:
            return cls.model_validate_json(plaintext)
        except ValidationError as exc:
            raise InvalidPayload() from exc


class PublicKey(BaseModel):
    public_key: str = Field(description="Clé publique RSA, PEM SubjectPublicKeyInfo")
    key_id: str = Field(description="Empreinte de la clé ; change si la clé est renouvelée")
    algorithm: Literal["RSA-OAEP-256"]
    content_encryption: Literal["A256GCM"]


class Payment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    src_account: UUID
    dst_account: UUID
    dst_iban_masked: str = Field(examples=["FR****8995"])
    amount_cents: int
    status: Literal["COMPLETED", "REJECTED"]
    created_at: datetime


class PaymentPage(BaseModel):
    """Page de résultats pour la vue admin (/admin/payments) : tous les virements,
    tous émetteurs/destinataires confondus, avec pagination."""

    items: list[Payment]
    total: int
    page: int
    page_size: int


class Account(BaseModel):
    id: UUID
    iban_masked: str = Field(examples=["FR****8995"])
    bic: str
    label: str
    currency: str
    balance_cents: int


class LedgerCheck(BaseModel):
    ok: bool
    unbalanced_tx: list[UUID]
    incomplete_tx: list[UUID]
    negative_accounts: list[UUID]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail
