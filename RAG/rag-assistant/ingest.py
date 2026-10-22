# ===================================================================
# INDEXATION — construit la base vectorielle à partir des docs
# Lit docs/exploitation/*.md, découpe par titres Markdown en gardant
# le frontmatter YAML comme métadonnées, calcule les embeddings (Ollama)
# et stocke le tout dans Chroma.
#
# Usage :  python ingest.py          (réindexe tout)
# ===================================================================
import pathlib

import frontmatter
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

import config

# On découpe sur les titres de niveau 1 à 3 : chaque section devient un fragment
# autonome (c'est justement la convention de rédaction des docs d'exploitation).
HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


def charger_fragments():
    """Lit tous les .md du dossier et renvoie une liste de Documents prêts à indexer."""
    racine = pathlib.Path(config.DOCS_DIR)
    fichiers = sorted(racine.rglob("*.md"))
    if not fichiers:
        raise SystemExit(f"Aucun .md trouvé dans {racine}. Vérifie DOCS_DIR / le montage du volume.")

    header_splitter = MarkdownHeaderTextSplitter(HEADERS, strip_headers=False)
    taille_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE, chunk_overlap=config.CHUNK_OVERLAP
    )

    fragments = []
    for chemin in fichiers:
        post = frontmatter.load(chemin)          # sépare l'en-tête YAML du corps
        meta_fichier = post.metadata or {}
        rel = chemin.relative_to(racine).as_posix()
        titre = meta_fichier.get("titre", rel)

        # 1) découpe par titres, 2) re-découpe les sections trop longues
        sections = header_splitter.split_text(post.content)
        morceaux = taille_splitter.split_documents(sections)

        for m in morceaux:
            # chemin de titres (h1 > h2 > h3) pour situer le fragment
            chemin_titres = " > ".join(
                m.metadata.get(k) for k in ("h1", "h2", "h3") if m.metadata.get(k)
            )
            fragments.append(
                Document(
                    page_content=m.page_content,
                    metadata={
                        "fichier": rel,
                        "titre": titre,
                        "section": chemin_titres or titre,
                        "type": str(meta_fichier.get("type", "")),
                        "domaine": ", ".join(meta_fichier.get("domaine", []) or []),
                    },
                )
            )
    print(f"{len(fragments)} fragments issus de {len(fichiers)} fichiers.")
    return fragments


def construire_index():
    """Construit (ou reconstruit) l'index Chroma à partir des fragments."""
    fragments = charger_fragments()
    embeddings = OllamaEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_BASE_URL)
    # from_documents (re)crée la collection persistée sur disque.
    Chroma.from_documents(
        documents=fragments,
        embedding=embeddings,
        collection_name=config.COLLECTION,
        persist_directory=config.PERSIST_DIR,
    )
    print(f"✅ Index construit dans {config.PERSIST_DIR} (collection {config.COLLECTION}).")


if __name__ == "__main__":
    construire_index()
