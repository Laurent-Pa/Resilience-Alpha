# ===================================================================
# EMBEDDINGS NOMIC — préfixes de tâche
# nomic-embed-text est entraîné avec un préfixe qui indique le rôle du texte :
# "search_document: " pour ce qu'on indexe, "search_query: " pour la question.
# Sans eux, les vecteurs des questions et des documents se rapprochent mal et
# la recherche ramène des passages hors sujet.
# Partagé par ingest.py (documents) et app.py (questions).
# ===================================================================
from langchain_ollama import OllamaEmbeddings

import config

DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class NomicEmbeddings(OllamaEmbeddings):
    # OllamaEmbeddings.embed_query délègue à embed_documents : on passe par _embed pour
    # que la question ne reçoive pas le préfixe document en plus du sien.

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return super().embed_documents(texts)

    async def _aembed(self, texts: list[str]) -> list[list[float]]:
        return await super().aembed_documents(texts)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed([DOC_PREFIX + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([QUERY_PREFIX + text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._aembed([DOC_PREFIX + t for t in texts])

    async def aembed_query(self, text: str) -> list[float]:
        return (await self._aembed([QUERY_PREFIX + text]))[0]


def make_embeddings() -> NomicEmbeddings:
    return NomicEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_BASE_URL)
