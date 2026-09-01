"""Orchestrates document processing for one domain: parse -> chunk -> embed -> index.

Runs after the extract layer (ingestion/) has populated data/raw/documents/<domain>/.
Skips PDFs already chunked unless force=True (idempotent reruns).

Each document is processed in its own subprocess (see the __main__ entry
point below). Docling's layout/table models plus the Granite embedding
model don't reliably release memory between documents in one long-lived
process - a multi-document run was dying partway through with no traceback
(likely an OS-level kill on memory pressure). Isolating per document means
a heavy or broken PDF only fails that one document, the parent gets a real
stderr/traceback to log, and every document starts from a clean memory
slate.
"""
import json
import subprocess
import sys
from pathlib import Path

from ..ingestion.documents import manifest as doc_manifest

DATA_DIR = Path("data")
FAILURE_LOG = Path("logs/ingestion/processing_failures.jsonl")


def _guess_title(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip()


def _process_single_document(domain: str, doc_id: str, record: dict) -> None:
    """Parse, chunk, and embed exactly one document. Runs inside the worker subprocess."""
    from . import chunker, pdf_parser
    from ..storage import vector_store

    parsed_dir = DATA_DIR / "processed" / "documents" / domain / "parsed"
    chunks_dir = DATA_DIR / "processed" / "documents" / domain / "chunks"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    local_path = Path(record["local_path"])
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

    (chunks_dir / f"{doc_id}.jsonl").write_text(
        "\n".join(json.dumps(c) for c in doc_chunks) + ("\n" if doc_chunks else ""),
        encoding="utf-8",
    )
    vector_store.upsert_chunks(domain, doc_chunks)


def process_domain(domain: str, force: bool = False) -> dict:
    """Parse, chunk, and index every downloaded PDF for a domain."""
    manifest_path = DATA_DIR / "raw" / "documents" / domain / "manifest.jsonl"
    records = doc_manifest.load(manifest_path)
    chunks_dir = DATA_DIR / "processed" / "documents" / domain / "chunks"

    stats = {"documents_processed": 0, "documents_skipped": 0, "documents_failed": 0, "chunks_created": 0}

    for doc_id, record in records.items():
        chunks_path = chunks_dir / f"{doc_id}.jsonl"
        if chunks_path.exists() and not force:
            stats["documents_skipped"] += 1
            continue

        local_path = Path(record["local_path"])
        if not local_path.exists():
            stats["documents_skipped"] += 1
            continue

        result = subprocess.run(
            [sys.executable, "-m", "mocolens.processing.runner", domain, doc_id],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and chunks_path.exists():
            stats["documents_processed"] += 1
            with chunks_path.open(encoding="utf-8") as f:
                stats["chunks_created"] += sum(1 for _ in f)
        else:
            stats["documents_failed"] += 1
            FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
            with FAILURE_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "domain": domain,
                    "document_id": doc_id,
                    "local_path": str(local_path),
                    "returncode": result.returncode,
                    "stderr_tail": result.stderr[-4000:],
                }) + "\n")

    return stats


if __name__ == "__main__":
    # Internal single-document worker spawned by process_domain via subprocess.
    # Not a general CLI - scripts/rebuild_vector_index.py is the public entry point.
    _domain, _doc_id = sys.argv[1], sys.argv[2]
    _manifest_path = DATA_DIR / "raw" / "documents" / _domain / "manifest.jsonl"
    _record = doc_manifest.load(_manifest_path)[_doc_id]
    _process_single_document(_domain, _doc_id, _record)
