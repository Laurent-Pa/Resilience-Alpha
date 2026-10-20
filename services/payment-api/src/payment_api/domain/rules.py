"""Règles métier pures (aucune I/O)."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from payment_api.domain import bic, iban


class PaymentError(Exception):
    """Refus métier, converti en réponse HTTP par la couche API.

    Les messages ne contiennent jamais de donnée saisie (IBAN, nom…)."""

    code = "payment_error"
    http_status = 400
    message = "Paiement refusé."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class UndecryptablePayload(PaymentError):
    code, http_status = "decryption_failed", 400
    message = "Coordonnées du bénéficiaire indéchiffrables. Rechargez la clé publique."


class InvalidPayload(PaymentError):
    code, http_status = "invalid_payload", 422
    message = "Coordonnées du bénéficiaire incomplètes ou mal formées."


class IdempotencyConflict(PaymentError):
    code, http_status = "idempotency_conflict", 409
    message = "Cette clé d'idempotence a déjà été utilisée avec une requête différente."


class InsufficientFunds(PaymentError):
    code, http_status = "insufficient_funds", 422
    message = "Fonds insuffisants sur le compte source."


class SameAccount(PaymentError):
    code, http_status = "same_account", 422
    message = "Les comptes source et destination doivent être différents."


class InvalidIban(PaymentError):
    code, http_status = "invalid_iban", 422
    message = "IBAN du bénéficiaire invalide."


class InvalidBic(PaymentError):
    code, http_status = "invalid_bic", 422
    message = "BIC du bénéficiaire invalide."


class BicMismatch(PaymentError):
    code, http_status = "bic_mismatch", 422
    message = "Le BIC ne correspond pas à la banque de cet IBAN."


class UnknownAccount(PaymentError):
    code, http_status = "unknown_account", 422
    message = "Aucun compte ne correspond à cet IBAN."


class NoAccount(PaymentError):
    code, http_status = "no_account", 403
    message = "Aucun compte n'est associé à cet utilisateur."


@dataclass(frozen=True)
class TransferRequest:
    # Pas de compte source : c'est l'unique compte du porteur du jeton.
    dst_iban: str  # normalisé ; ne quitte jamais la mémoire en clair
    dst_bic: str | None  # normalisé, optionnel
    amount: Decimal  # euros


def hash_request(key: bytes, owner: UUID, req: TransferRequest) -> str:
    """Empreinte HMAC de la requête (idempotence). Calculée sur les données déchiffrées :
    une même requête rechiffrée avec une autre clé AES reste un rejeu. Inclut le
    propriétaire : une clé rejouée par un autre utilisateur est un conflit."""
    canonical = json.dumps(
        {
            "owner": str(owner),
            "dst_iban": req.dst_iban,
            "dst_bic": req.dst_bic,
            "amount": f"{req.amount:.2f}",  # "50.5" et "50.50" : même requête
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(key, b"request:" + canonical.encode(), hashlib.sha256).hexdigest()


def validate_transfer(req: TransferRequest) -> None:
    if not iban.is_valid(req.dst_iban):
        raise InvalidIban()
    if req.dst_bic is not None and not bic.is_valid(req.dst_bic):
        raise InvalidBic()


def check_bic(account_bic: str, given_bic: str | None) -> None:
    if given_bic is not None and not bic.same_institution(account_bic, given_bic):
        raise BicMismatch()


def check_distinct(src_account: UUID, dst_account: UUID) -> None:
    if src_account == dst_account:
        raise SameAccount()


def check_replay(stored_hash: str, request_hash: str) -> None:
    if not hmac.compare_digest(stored_hash, request_hash):
        raise IdempotencyConflict()


def check_funds(balance: Decimal, amount: Decimal) -> None:
    if balance < amount:
        raise InsufficientFunds()


def lock_order(*account_ids: UUID) -> list[UUID]:
    """Ordre stable de verrouillage (évite les deadlocks entre virements croisés)."""
    return sorted(set(account_ids))
