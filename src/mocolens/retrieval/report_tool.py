"""search_reports (architecture doc §14.2): semantic search over county
documents, reshaped from the vector store's internal chunk metadata into
the citation fields §12 requires ("must return chunk text plus metadata
required for citations").
"""
from ..storage import vector_store


def search_reports(
    query: str,
    top_k: int = 5,
    year_at_least: int | None = None,
    *,
    domain: str = "vision_zero",
) -> list[dict]:
    """Semantic search over one domain's document chunks (§14.2).

    `year_at_least` keeps only chunks from reports published in or after
    that year, matching the doc's own example ("year >= 2023"). It is the
    only filter anything ever asked for; the store previously accepted a
    pass-through filter dict shaped for Chroma's query language, which
    nothing outside that store had a reason to know about.
    """
    return [
        {
            "text": h["text"],
            "document_title": h.get("title"),
            "page": _format_page(h.get("page_start"), h.get("page_end")),
            "publication_year": h.get("year"),
            "source_url": h.get("source_url"),
            "similarity_score": round(h["similarity"], 4),
            "section": h.get("section"),
        }
        for h in vector_store.search(domain, query, top_k=top_k, year_at_least=year_at_least)
    ]


def _format_page(start, end) -> str | None:
    if start is None:
        return None
    if end is None or end == start:
        return str(int(start))
    return f"{int(start)}-{int(end)}"
