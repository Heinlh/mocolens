"""Backend for GET /api/sources (architecture doc §21) - the provenance the
Sources & Methodology screen shows, matching frontend/src/types/sources.ts.

A thin composition over two existing pieces rather than a third view of the
data: retrieval/metadata_tool.py already resolves the source registry plus
raw-lake freshness for the agent, and storage/vector_store.index_info()
already knows which documents are actually searchable. This module only
maps them onto the frontend contract.

Freshness has a deployment wrinkle worth stating: data/raw/ and logs/ are
excluded from the container image, so metadata_tool's raw-lake signals are
None in production. Both fallbacks used here - build_info.json next to the
curated tables, and the index's own built_at stamp - ship inside the image,
so a deployed Sources page reports real dates instead of blanks. Nothing is
invented: a source with no signal at all reports None.
"""
from ..processing import curate
from ..retrieval import metadata_tool
from ..storage import vector_store
from . import schemas

DOMAIN = "vision_zero"

_FRONTEND_TYPE = {"dataset": "dataset", "report_collection": "report"}


def _date_part(timestamp: str | None) -> str | None:
    """The YYYY-MM-DD of an ISO timestamp - the card shows a day, not a time."""
    return timestamp.split("T")[0] if timestamp else None


def _page_range(document: dict) -> str | None:
    start, end = document.get("page_start"), document.get("page_end")
    if start is None:
        return None
    return str(start) if end is None or end == start else f"{start}-{end}"


def _data_sources(domain: str, index: dict | None) -> list[schemas.DataSource]:
    """Registry entries, each with the freshest real signal available."""
    curated = curate.build_info(domain) or {}
    index_built = _date_part(index["built_at"]) if index else None

    sources = []
    for source in metadata_tool.get_source_metadata(domain):
        source_type = _FRONTEND_TYPE.get(source["type"])
        if source_type is None:
            continue
        fallback = index_built if source_type == "report" else curated.get("snapshot_date")
        sources.append(schemas.DataSource(
            id=source["id"],
            title=source["title"],
            description=source["description"],
            source_type=source_type,
            refresh_cadence=source["refresh_cadence"],
            # Normalized to a day: the raw-lake signals are a snapshot date
            # for datasets but a full download timestamp for documents, and
            # the card shows one date format for both.
            last_updated=_date_part(source["last_updated"]) or fallback,
            url=source["source_url"],
        ))
    return sources


def _citations(index: dict | None) -> list[schemas.Citation]:
    """The county documents MoCoLens can actually quote - every document in
    the searchable index, not a curated highlight list, so the page cannot
    claim a source the agent has no access to.
    """
    if index is None:
        return []
    return [
        schemas.Citation(
            id=document["document_id"][:12],
            title=document["title"] or "Untitled document",
            source_type="report",
            url=document["source_url"],
            page=_page_range(document),
            # Only the publication year is known (inferred from the filename
            # during chunking), so the year is what gets published - a full
            # date here would invent a month the document never stated.
            published_at=str(document["year"]) if document["year"] else None,
        )
        for document in index["documents"]
    ]


def get_sources(domain: str = DOMAIN) -> schemas.SourcesResponse:
    index = vector_store.index_info(domain)
    return schemas.SourcesResponse(
        sources=_data_sources(domain, index),
        citations=_citations(index),
        indexed_chunk_count=index["chunk_count"] if index else 0,
    )
