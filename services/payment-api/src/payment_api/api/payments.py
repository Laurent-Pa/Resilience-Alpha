import time
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from prometheus_client import Counter, Histogram
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api import crypto, service
from payment_api.db import get_session
from payment_api.domain.rules import PaymentError, TransferRequest
from payment_api.models import INITIATED_BY_PROBER, INITIATED_BY_USER
from payment_api.repo import accounts as accounts_repo
from payment_api.repo import transactions as tx_repo
from payment_api.schemas import Beneficiary, ErrorResponse, Payment, PublicKey, TransferEnvelope
from resilience_common.auth import Claims, require_role

PAYMENTS = Counter("payments_total", "Paiements traités, par issue", ["status"])
PAYMENT_DURATION = Histogram("payment_duration_seconds", "Durée de traitement d'un paiement")

log = structlog.get_logger()
router = APIRouter(prefix="/payments", tags=["payments"])

Session = Annotated[AsyncSession, Depends(get_session)]


# Déclarée avant /{payment_id} pour ne pas être capturée par ce gabarit.
@router.get("/public-key", response_model=PublicKey)
async def public_key(request: Request) -> PublicKey:
    """Clé publique RSA servant à chiffrer les coordonnées du bénéficiaire.

    À recharger si /payments/transfer répond 400 `decryption_failed` (clé renouvelée)."""
    cipher: crypto.TransferCipher = request.app.state.transfer_cipher
    return PublicKey(
        public_key=cipher.public_pem,
        key_id=cipher.key_id,
        algorithm=crypto.ALGORITHM,
        content_encryption=crypto.CONTENT_ENCRYPTION,
    )


@router.post(
    "/transfer",
    status_code=status.HTTP_201_CREATED,
    response_model=Payment,
    responses={
        200: {"model": Payment, "description": "Rejeu identique : transaction existante"},
        400: {"model": ErrorResponse, "description": "Coordonnées indéchiffrables"},
        403: {"model": ErrorResponse, "description": "Aucun compte associé à l'utilisateur"},
        409: {"model": ErrorResponse, "description": "Même clé, requête différente"},
        422: {"description": "Fonds insuffisants, IBAN/BIC invalide ou inconnu, validation"},
    },
)
async def create_transfer(
    body: TransferEnvelope,
    request: Request,
    response: Response,
    session: Session,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    claims: Claims = Depends(require_role("client", "prober")),
) -> Payment:
    # Origine de l'opération : le rôle realm du jeton, et non l'UUID du compte émetteur.
    # Seule cette couche voit les rôles, d'où la décision prise ici et passée en aval.
    initiated_by = INITIATED_BY_PROBER if INITIATED_BY_PROBER in claims.roles else INITIATED_BY_USER
    start = time.perf_counter()
    try:
        # Les coordonnées en clair ne vivent que dans ce bloc et ne sont jamais journalisées.
        plaintext = request.app.state.transfer_cipher.decrypt(
            body.encrypted_key, body.iv, body.ciphertext
        )
        beneficiary = Beneficiary.parse(plaintext)
        req = TransferRequest(beneficiary.iban, beneficiary.bic, body.amount)
        tx, created = await service.transfer(
            session,
            idempotency_key,
            claims.sub,
            req,
            request.app.state.pseudonymizer,
            initiated_by,
        )
    except PaymentError as exc:
        PAYMENTS.labels(exc.code).inc()
        log.warning(
            "payment.rejected",
            reason=exc.code,
            status=exc.http_status,
            amount=str(body.amount),
        )
        raise HTTPException(exc.http_status, {"code": exc.code, "message": exc.message}) from exc
    finally:
        PAYMENT_DURATION.observe(time.perf_counter() - start)

    if created:
        PAYMENTS.labels("completed").inc()
        log.info("payment.created", tx_id=str(tx.id), amount=str(tx.amount), status=201)
    else:
        PAYMENTS.labels("replayed").inc()
        log.info("payment.replayed", tx_id=str(tx.id), status=200)
        response.status_code = status.HTTP_200_OK
    return Payment.model_validate(tx)


@router.get("", response_model=list[Payment])
async def list_payments(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    claims: Claims = Depends(require_role("client", "prober")),
) -> list[Payment]:
    """Historique : virements émis par l'utilisateur et reçus sur ses comptes."""
    owned = await accounts_repo.owned_ids(session, claims.sub)
    txs = await tx_repo.history(session, claims.sub, owned, limit)
    return [Payment.model_validate(t) for t in txs]


@router.get(
    "/{payment_id}", response_model=Payment, responses={404: {"description": "Introuvable"}}
)
async def get_payment(
    payment_id: UUID,
    session: Session,
    claims: Claims = Depends(require_role("client", "prober")),
) -> Payment:
    tx = await tx_repo.get(session, payment_id)
    if tx is None or not await tx_repo.is_visible_to(session, tx, claims.sub):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return Payment.model_validate(tx)
