"""Relais POST /api/admin/assistant/ask → rag-assistant POST /ask.

rag-assistant est simulé par un httpx.MockTransport : ces tests vérifient le contrôle
d'accès, le contrat relayé et la traduction des pannes, pas le RAG lui-même."""

import json

import httpx
import pytest
from structlog.testing import capture_logs

ASK = "/api/admin/assistant/ask"
QUESTION = "Que faire en cas de flood HTTP sur payment-api ?"
RAG_ANSWER = {
    "answer": "Le moteur bloque l'IP source puis vérifie la reprise (RB-01).",
    "sources": [
        {
            "title": "RB-01 — Flood HTTP / déni de service sur payment-api (incident http_flood)",
            "file": "runbooks/RB-01-flood-http.md",
            "section": "RB-01 — Flood HTTP > Ce que fait le système automatiquement",
        }
    ],
}


@pytest.fixture
async def rag(app):
    """rag(handler) remplace le client vers rag-assistant ; renvoie les requêtes reçues."""
    original = app.state.rag_client
    clients: list[httpx.AsyncClient] = []

    def _install(handler) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(recording), base_url="http://rag-assistant:8000"
        )
        clients.append(client)
        app.state.rag_client = client
        return seen

    yield _install
    app.state.rag_client = original
    for c in clients:
        await c.aclose()


def answers(body: dict, status: int = 200):
    return lambda request: httpx.Response(status, json=body)


def raises(exc: type[httpx.HTTPError]):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc("simulé", request=request)

    return handler


# --- Contrôle d'accès ---------------------------------------------------------------


async def test_ask_requires_auth(client, rag):
    seen = rag(answers(RAG_ANSWER))
    r = await client.post(ASK, json={"question": QUESTION})
    assert r.status_code == 401
    assert seen == []


@pytest.mark.parametrize("user", ["alice", "prober"])
async def test_ask_rejects_non_ops_roles(client, auth, rag, user):
    seen = rag(answers(RAG_ANSWER))
    r = await client.post(ASK, json={"question": QUESTION}, headers=auth(user))
    assert r.status_code == 403
    assert seen == []  # rien n'est relayé sans le rôle ops


# --- Relais nominal -----------------------------------------------------------------


async def test_ask_relays_question_and_returns_answer_with_sources(client, auth, rag):
    seen = rag(answers(RAG_ANSWER))
    r = await client.post(ASK, json={"question": QUESTION}, headers=auth("operator"))
    assert r.status_code == 200
    assert r.json() == RAG_ANSWER

    assert len(seen) == 1
    assert (seen[0].method, seen[0].url.path) == ("POST", "/ask")
    # Seule la question part vers rag-assistant : ni jeton, ni top_k.
    assert json.loads(seen[0].content) == {"question": QUESTION}
    assert "authorization" not in seen[0].headers


async def test_ask_without_relevant_passage_is_not_an_error(client, auth, rag):
    no_context = {"answer": "Je ne trouve pas d'information pertinente.", "sources": []}
    rag(answers(no_context))
    r = await client.post(ASK, json={"question": QUESTION}, headers=auth("operator"))
    assert r.status_code == 200
    assert r.json() == no_context


async def test_ask_never_logs_the_question(client, auth, rag):
    rag(answers(RAG_ANSWER))
    with capture_logs() as logs:
        r = await client.post(ASK, json={"question": QUESTION}, headers=auth("operator"))
    assert r.status_code == 200
    event = next(e for e in logs if e["event"] == "admin.assistant.answered")
    assert (event["question_len"], event["n_sources"]) == (len(QUESTION), 1)
    assert QUESTION not in repr(logs)


# --- Validation (mêmes bornes que contracts/rag-ask.schema.json) ---------------------


@pytest.mark.parametrize(
    "body",
    [
        {"question": ""},
        {"question": "x" * 2001},
        {"question": QUESTION, "top_k": 50},  # champ hors contrat côté front
        {},
    ],
    ids=["vide", "trop-longue", "champ-inconnu", "absente"],
)
async def test_ask_rejects_out_of_contract_questions(client, auth, rag, body):
    seen = rag(answers(RAG_ANSWER))
    r = await client.post(ASK, json=body, headers=auth("operator"))
    assert r.status_code == 422
    assert seen == []


# --- Pannes de rag-assistant --------------------------------------------------------


@pytest.mark.parametrize(
    ("handler", "status", "code"),
    [
        (raises(httpx.ConnectError), 503, "assistant_unavailable"),
        (raises(httpx.ConnectTimeout), 503, "assistant_unavailable"),
        (answers({"detail": "Internal Server Error"}, 500), 503, "assistant_unavailable"),
        (raises(httpx.ReadTimeout), 504, "assistant_timeout"),
        (answers({"detail": "hors contrat"}, 422), 502, "assistant_bad_response"),
        (answers({"answer": "sans sources"}), 502, "assistant_bad_response"),
    ],
    ids=[
        "arrete",
        "connexion-lente",
        "ollama-injoignable",
        "llm-trop-lent",
        "422",
        "corps-invalide",
    ],
)
async def test_ask_translates_rag_failures(client, auth, rag, handler, status, code):
    rag(handler)
    with capture_logs() as logs:
        r = await client.post(ASK, json={"question": QUESTION}, headers=auth("operator"))
    assert r.status_code == status
    assert r.json()["detail"]["code"] == code
    assert r.json()["detail"]["message"]
    failed = next(e for e in logs if e["event"] == "admin.assistant.failed")
    assert failed["reason"] == code
