# ===================================================================
# ASSISTANT RAG — API HTTP
# POST /ask {question}  ->  {answer, sources[]}
# L'assistant répond UNIQUEMENT à partir des docs d'exploitation
# (Retrieval-Augmented Generation), cite ses sources, n'exécute aucune
# action et n'a aucun accès privilégié au système.
# ===================================================================
import json
import os
import sys
import time

from fastapi import FastAPI, Response
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama, OllamaEmbeddings
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

import config

# --- Métriques Prometheus (DoD projet : chaque service expose /metrics) ---
RAG_REQUESTS = Counter("rag_requests_total", "Questions traitées", ["outcome"])
RAG_LATENCY = Histogram("rag_answer_duration_seconds", "Durée d'une réponse")


def log_json(event, **fields):
    """Log JSON sur une ligne vers stdout (convention de journalisation du projet)."""
    print(
        json.dumps({"service": "rag-assistant", "event": event, **fields}),
        file=sys.stdout,
        flush=True,
    )


# --- Consigne donnée au modèle (ancrage strict + citation + pas d'action) ---
SYSTEME = (
    "Tu es l'assistant documentaire de la plateforme Résilience Alpha. "
    "Tu aides un opérateur à comprendre le système et à retrouver les procédures. "
    "Réponds en français, de façon concise et précise. "
    "Appuie-toi UNIQUEMENT sur le CONTEXTE fourni ci-dessous. "
    "Si l'information ne s'y trouve pas, dis-le clairement (« je ne trouve pas cette "
    "information dans la documentation ») plutôt que d'inventer. "
    "Si le contexte porte la mention « À compléter par l'équipe », signale-le. "
    "Tu n'exécutes aucune action et ne disposes d'aucun accès au système : "
    "tu ne fais qu'expliquer et citer la documentation.\n\n"
    "CONTEXTE :\n{context}"
)

PROMPT = ChatPromptTemplate.from_messages([("system", SYSTEME), ("human", "{question}")])

app = FastAPI(title="Résilience Alpha — Assistant RAG")
_store = None
_llm = None


def _get_store():
    global _store
    if _store is None:
        embeddings = OllamaEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_BASE_URL)
        _store = Chroma(
            collection_name=config.COLLECTION,
            embedding_function=embeddings,
            persist_directory=config.PERSIST_DIR,
        )
    return _store


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=config.LLM_MODEL, base_url=config.OLLAMA_BASE_URL, temperature=0)
    return _llm


class AskIn(BaseModel):
    question: str
    top_k: int | None = None


@app.post("/ask")
def ask(body: AskIn):
    """Répond à une question en s'appuyant sur les docs d'exploitation."""
    debut = time.perf_counter()
    k = body.top_k or config.TOP_K
    docs = _get_store().similarity_search(body.question, k=k)

    if not docs:
        RAG_REQUESTS.labels(outcome="no_context").inc()
        log_json("rag.answer", outcome="no_context", question_len=len(body.question))
        return {
            "answer": "Je ne trouve pas d'information pertinente dans la documentation.",
            "sources": [],
        }

    # Construit le contexte en étiquetant chaque fragment par sa source.
    contexte = "\n\n".join(
        f"[Source : {d.metadata.get('fichier')} — {d.metadata.get('section')}]\n{d.page_content}"
        for d in docs
    )
    message = PROMPT.format_messages(context=contexte, question=body.question)
    reponse = _get_llm().invoke(message)

    # Dédoublonne les sources (fichier + section) dans l'ordre d'apparition.
    sources, vus = [], set()
    for d in docs:
        cle = (d.metadata.get("fichier"), d.metadata.get("section"))
        if cle not in vus:
            vus.add(cle)
            sources.append(
                {
                    "title": d.metadata.get("titre"),
                    "file": d.metadata.get("fichier"),
                    "section": d.metadata.get("section"),
                }
            )

    latence_ms = round((time.perf_counter() - debut) * 1000)
    RAG_REQUESTS.labels(outcome="ok").inc()
    RAG_LATENCY.observe(latence_ms / 1000)
    log_json(
        "rag.answer",
        outcome="ok",
        question_len=len(body.question),
        n_sources=len(sources),
        latency_ms=latence_ms,
    )
    return {"answer": reponse.content, "sources": sources}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    """Prêt si l'index contient des documents (Ollama est testé à la 1re question)."""
    try:
        n = _get_store()._collection.count()
        if n > 0:
            return {"status": "ready", "documents": n}
        return ({"status": "empty"}, 503)
    except Exception as e:
        return ({"status": "error", "detail": str(e)}, 503)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", config.PORT)))  # noqa: S104 -- bind conteneur
