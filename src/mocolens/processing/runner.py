"""Orchestrates document processing for one domain: parse -> chunk -> embed -> index.

Runs after the extract layer (ingestion/) has populated data/raw/documents/<domain>/.
Skips PDFs already chunked unless force=True (idempotent reruns).
"""
import json
from pathlib import Path

from ..ingestion.documents import manifest as doc_manifest
from ..storage import vector_store
from . import chunker, pdf_parser

DATA_DIR = Path("data")


def _guess_title(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip()


def process_domain(domain: str, force: bool = False) -> dict:
    """Parse, chunk, and index every downloaded PDF for a domain."""
    manifest_path = DATA_DIR / "raw" / "documents" / domain / "manifest.jsonl"
    records = doc_manifest.load(manifest_path)

    parsed_dir = DATA_DIR / "processed" / "documents" / domain / "parsed"
    chunks_dir = DATA_DIR / "processed" / "documents" / domain / "chunks"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    stats = {"documents_processed": 0, "documents_skipped": 0, "chunks_created": 0}

    for doc_id, record in records.items():
        chunks_path = chunks_dir / f"{doc_id}.jsonl"
        if chunks_path.exists() and not force:
            stats["documents_skipped"] += 1
            continue

        local_path = Path(record["local_path"])
        if not local_path.exists():
            stats["documents_skipped"] += 1
            continue

        doc = pdf_parser.parse(local_path)
        (parsed_dir / f"{doc_id}.md").write_text(doc.export_to_markdown(), encoding="utf-8")

        doc_chunks = chunker.chunk_document(
            doc,
            document_id=doc_id,
            title=_guess_title(local_path.name),
            domain=domain,
            source_url=record["source_url"],
            year=chunker.guess_year(local_path.name),
        )

        chunks_path.write_text(
            "\n".join(json.dumps(c) for c in doc_chunks) + ("\n" if doc_chunks else ""),
            encoding="utf-8",
        )
        vector_store.upsert_chunks(domain, doc_chunks)

        stats["documents_processed"] += 1
        stats["chunks_created"] += len(doc_chunks)

    return stats
