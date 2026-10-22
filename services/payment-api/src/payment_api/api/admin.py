import time
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from prometheus_client import Counter, Histogram
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from payment_api.db import get_session
from payment_api.domain import probe_sli
from payment_api.models import INITIATED_BY_PROBER
from payment_api.repo import ledger as ledger_repo
from payment_api.repo import transactions as tx_repo
from payment_api.schemas import (
    AdminPayment,
    AssistantAnswer,
    AssistantQuestion,
    ErrorResponse,
    LedgerCheck,
    PaymentPage,
    ProberMinute,
    ProberSuccessRate,
)
from resilience_common.auth import require_role

ASSISTANT_REQUESTS = Counter(
    "assistant_requests_total", "Questions relayées à rag-assistant, par issue", ["outcome"]
)
ASSISTANT_DURATION = Histogram(
    "assistant_duration_seconds",
    "Durée d'une question relayée à rag-assistant (LLM sur CPU : secondes à minutes)",
    buckets=(1, 2.5, 5, 10, 20, 30, 45, 60, 90, 120, 180),
)

log = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("ops"))])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/ledger/check", response_model=LedgerCheck)
async def ledger_check(session: Session) -> LedgerCheck:
    """Invariant comptable : chaque transaction s'équilibre, a deux écritures, et aucun
    compte client n'est négatif. Utilisé par le verifier du moteur de remédiation."""
    found = await ledger_repo.check(session)
    result = LedgerCheck(ok=not any(found.values()), **found)
    log.info("ledger.check", ok=result.ok, **{k: len(v) for k, v in found.items()})
    return result


@router.get("/payments", response_model=PaymentPage)
async def list_all_payments(
    session: Session,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, alias="page_size")] = 20,
    include_prober: bool = False,
) -> PaymentPage:
    """Vue back-office : les virements, tous émetteurs/destinataires confondus
    (contrairement à GET /payments, qui ne renvoie que l'historique de l'appelant).

    Le trafic de la sonde est écarté par défaut : elle émet un virement toutes les
    quelques secondes et noierait la liste. `include_prober=true` le réintègre.

    L'IBAN n'est jamais exposé qu'au format masqué (`AdminPayment.dst_iban_masked`,
    ex. "FR****8995") : c'est la seule forme stockée en base, il n'y a donc rien
    à filtrer ici."""
    excluded = None if include_prober else INITIATED_BY_PROBER
    offset = (page - 1) * page_size
    total = await tx_repo.count_all(session, exclude_initiated_by=excluded)
    txs = await tx_repo.list_all(
        session, limit=page_size, offset=offset, exclude_initiated_by=excluded
    )
    log.info(
        "admin.payments.list",
        page=page,
        page_size=page_size,
        total=total,
        include_prober=include_prober,
    )
    return PaymentPage(
        items=[AdminPayment.model_validate(t) for t in txs],
        total=total,
        page=page,
        page_size=page_size,
    )


PROBER_WINDOW_MINUTES = 60


@router.get("/prober/success-rate", response_model=ProberSuccessRate)
async def prober_success_rate(request: Request, session: Session) -> ProberSuccessRate:
    """SLI de la sonde : taux de réussite par minute sur la dernière heure complète.

    Calculé sur les virements réellement enregistrés, rapportés à la cadence nominale de
    la sonde (PROBER_INTERVAL_S). Une sonde arrêtée ou en échec n'écrit rien : ses
    minutes ressortent à 0 %, ce qui est le signal attendu.

    Pas de log ici : le dashboard interroge cet endpoint en boucle."""
    interval_s: float = request.app.state.prober_interval_s
    start, end = probe_sli.minute_window(datetime.now(UTC), PROBER_WINDOW_MINUTES)
    counts = await tx_repo.completed_per_minute(session, INITIATED_BY_PROBER, start, end)
    points = probe_sli.success_series(counts, start, PROBER_WINDOW_MINUTES, interval_s)
    return ProberSuccessRate(
        interval_s=interval_s,
        window_minutes=PROBER_WINDOW_MINUTES,
        points=[ProberMinute(**asdict(p)) for p in points],
    )


# --- Assistant documentaire (relais vers rag-assistant) -------------------------------


class AssistantError(Exception):
    """Échec du relais, converti en réponse {code, message} par l'endpoint."""

    def __init__(self, http_status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.http_status, self.code, self.message = http_status, code, message


UNAVAILABLE = (503, "assistant_unavailable", "L'assistant documentaire est indisponible.")
TIMEOUT = (504, "assistant_timeout", "L'assistant n'a pas répondu à temps. Réessayez.")
BAD_RESPONSE = (502, "assistant_bad_response", "Réponse inattendue de l'assistant.")


async def ask_rag(client: httpx.AsyncClient, question: str) -> AssistantAnswer:
    """POST /ask de rag-assistant (contracts/rag-ask.schema.json), réponse revalidée."""
    try:
        r = await client.post("/ask", json={"question": question})
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:  # service arrêté ou absent
        raise AssistantError(*UNAVAILABLE) from exc
    except httpx.TimeoutException as exc:  # joint, mais le LLM n'a pas fini à temps
        raise AssistantError(*TIMEOUT) from exc
    except httpx.HTTPError as exc:
        raise AssistantError(*UNAVAILABLE) from exc
    if r.status_code >= 500:  # 500 : Ollama injoignable côté rag-assistant
        raise AssistantError(*UNAVAILABLE)
    if r.status_code != 200:
        raise AssistantError(*BAD_RESPONSE)
    try:
        return AssistantAnswer.model_validate_json(r.content)
    except ValidationError as exc:
        raise AssistantError(*BAD_RESPONSE) from exc


@router.post(
    "/assistant/ask",
    response_model=AssistantAnswer,
    responses={
        502: {"model": ErrorResponse, "description": "Réponse de l'assistant hors contrat"},
        503: {"model": ErrorResponse, "description": "Assistant (ou son LLM) indisponible"},
        504: {"model": ErrorResponse, "description": "Assistant trop lent"},
    },
)
async def assistant_ask(body: AssistantQuestion, request: Request) -> AssistantAnswer:
    """Question à l'assistant documentaire (RAG), réservée au rôle ops.

    Relais vers rag-assistant sur le réseau Docker interne : l'assistant n'a pas
    d'authentification propre et n'est pas exposé par le WAF. Il répond à partir de
    docs/exploitation/ en citant ses sources, et n'exécute aucune action.

    La question n'est jamais journalisée (un opérateur peut y coller un message
    d'erreur) : seule sa longueur l'est."""
    start = time.perf_counter()
    try:
        answer = await ask_rag(request.app.state.rag_client, body.question)
    except AssistantError as exc:
        ASSISTANT_REQUESTS.labels(exc.code).inc()
        ASSISTANT_DURATION.observe(time.perf_counter() - start)
        log.warning(
            "admin.assistant.failed",
            reason=exc.code,
            status=exc.http_status,
            question_len=len(body.question),
            duration_ms=round((time.perf_counter() - start) * 1000),
        )
        raise HTTPException(exc.http_status, {"code": exc.code, "message": exc.message}) from exc
    ASSISTANT_REQUESTS.labels("ok").inc()
    ASSISTANT_DURATION.observe(time.perf_counter() - start)
    log.info(
        "admin.assistant.answered",
        question_len=len(body.question),
        n_sources=len(answer.sources),
        duration_ms=round((time.perf_counter() - start) * 1000),
    )
    return answer
