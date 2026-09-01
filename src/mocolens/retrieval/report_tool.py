"""search_reports (architecture doc §14.2): semantic search over county
documents, reshaped from the vector store's internal chunk metadata into
the citation fields §12 requires ("must return chunk text plus metadata
required for citations").
"""
from ..storage import vector_store

# Metadata fields a caller may filter on. Anything else is dropped rather
# than passed through - Chroma raises on a filter field that was never
# indexed, and a dropped filter is a much better failure mode for an
# agent tool than a stack trace.
_ALLOWED_FILTER_FIELDS = {"year", "domain", "section"}


def search_reports(query: str, filters: dict | None = None, top_k: int = 5, *, domain: str = "vision_zero") -> list[dict]:
    """Semantic search over one domain's document chunks (§14.2).

    `filters` values are forwarded to Chroma as-is per field, so both plain
    equality ({"year": 2025}) and Chroma operator filters
    ({"year": {"$gte": 2023}}) work, matching the doc's own example
    ("year >= 2023").
    """
    where = _build_where(filters)
    hits = vector_store.search(domain, query, top_k=top_k, where=where)
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
        for h in hits
    ]


def _format_page(start, end) -> str | None:
    if start is None:
        return None
    if end is None or end == start:
        return str(int(start))
    return f"{int(start)}-{int(end)}"


def _build_where(filters: dict | None) -> dict | None:
    if not filters:
        return None
    where = {k: v for k, v in filters.items() if k in _ALLOWED_FILTER_FIELDS}
    if not where:
        return None
    if len(where) == 1:
        return where
    return {"$and": [{k: v} for k, v in where.items()]}
