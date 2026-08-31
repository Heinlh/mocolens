"""Chroma persistent vector store for document chunks (§12).

Embeddings are computed explicitly with the Granite model rather than via
Chroma's default embedding function, so the model choice is ours to control
and swap later, not Chroma's.
"""
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from ..processing.chunker import EMBEDDING_MODEL

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def get_collection(domain: str, persist_dir: Path = Path("data/curated")):
    client = chromadb.PersistentClient(path=str(persist_dir / domain / "chroma"))
    return client.get_or_create_collection(name=f"{domain}_reports")


def upsert_chunks(domain: str, chunks: list[dict]) -> None:
    """Embed and upsert chunk records into the domain's Chroma collection."""
    if not chunks:
        return
    collection = get_collection(domain)
    embeddings = _get_model().encode([c["text"] for c in chunks], show_progress_bar=False).tolist()

    collection.upsert(
        ids=[c["chunk_id"] for c in chunks],
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        # Chroma metadata values must be str/int/float/bool - drop Nones.
        metadatas=[
            {k: v for k, v in c.items() if k not in ("chunk_id", "text") and v is not None}
            for c in chunks
        ],
    )


def search(domain: str, query: str, top_k: int = 5, where: dict | None = None) -> list[dict]:
    """Semantic search over a domain's chunks (§14.2 search_reports tool)."""
    collection = get_collection(domain)
    query_embedding = _get_model().encode([query]).tolist()

    result = collection.query(query_embeddings=query_embedding, n_results=top_k, where=where)

    hits = []
    for doc, meta, dist, cid in zip(
        result["documents"][0], result["metadatas"][0], result["distances"][0], result["ids"][0]
    ):
        hits.append({"chunk_id": cid, "text": doc, "similarity": 1 - dist, **meta})
    return hits
