"""Orchestrates document processing for one domain: parse -> chunk -> embed -> index.

Runs after the extract layer (ingestion/) has populated data/raw/documents/<domain>/.

Change detection (§8.3, §24): a document is reprocessed only when the content
hash the manifest recorded for its latest download differs from the hash it
was last processed at, tracked in processed.json. "Already chunked" is not a
sufficient test on its own - a county report republished at the same URL
leaves a chunk file on disk that no longer matches the PDF beside it, and
skipping on file existence alone would keep the superseded text searchable
indefinitely. A document with no processed.json entry is reprocessed, so a
tree that predates this state file repairs itself on the next run rather than
assuming its chunks are current.

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
from datetime import datetime, timezone
from pathlib import Path

from ..ingestion.documents import manifest as doc_manifest

DATA_DIR = Path("data")
FAILURE_LOG = Path("logs/ingestion/processing_failures.jsonl")
STATE_FILE = "processed.json"


def _domain_dir(domain: str) -> Path:
    return DATA_DIR / "processed" / "documents" / domain


def load_state(domain: str) -> dict[str, dict]:
    """What each document was last processed from: {document_id: {content_hash, ...}}."""
    path = _domain_dir(domain) / STATE_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Unreadable state means "nothing is known to be current", which
        # reprocesses everything - slow, but correct and self-repairing.
        return {}


def save_state(domain: str, state: dict[str, dict]) -> None:
    path = _domain_dir(domain) / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _guess_title(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip()


def _process_single_document(domain: str, doc_id: str, record: dict) -> None:
    """Parse, chunk, and embed exactly one document. Runs inside the worker subprocess."""
    from . import chunker, pdf_parser
    from ..storage import vector_store

    parsed_dir = _domain_dir(domain) / "parsed"
    chunks_dir = _domain_dir(domain) / "chunks"
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
    # replace_document, not an append: this document's previous chunks have to
    # leave the index, or a shortened revision keeps its old tail searchable.
    vector_store.replace_document(domain, doc_id, doc_chunks)


def _is_current(record: dict, processed: dict | None, chunks_path: Path) -> bool:
    """True if this document's chunks were built from the file now on disk."""
    if processed is None or not chunks_path.exists():
        return False
    return processed.get("content_hash") == record.get("content_hash")


def _log_failure(domain: str, doc_id: str, local_path: Path, result) -> None:
    FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FAILURE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "domain": domain,
            "document_id": doc_id,
            "local_path": str(local_path),
            "returncode": result.returncode,
            "stderr_tail": result.stderr[-4000:],
        }) + "\n")


def process_domain(domain: str, force: bool = False) -> dict:
    """Parse, chunk, and index every new or changed downloaded PDF for a domain.

    `force` reprocesses every document regardless of change detection.
    """
    manifest_path = DATA_DIR / "raw" / "documents" / domain / "manifest.jsonl"
    records = doc_manifest.load(manifest_path)
    chunks_dir = _domain_dir(domain) / "chunks"
    state = load_state(domain)

    stats = {"documents_processed": 0, "documents_skipped": 0, "documents_failed": 0, "chunks_created": 0}

    for doc_id, record in records.items():
        local_path = Path(record["local_path"])
        if not local_path.exists():
            stats["documents_skipped"] += 1
            continue

        chunks_path = chunks_dir / f"{doc_id}.jsonl"
        if not force and _is_current(record, state.get(doc_id), chunks_path):
            stats["documents_skipped"] += 1
            continue

        result = subprocess.run(
            [sys.executable, "-m", "mocolens.processing.runner", domain, doc_id],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and chunks_path.exists():
            with chunks_path.open(encoding="utf-8") as f:
                chunk_count = sum(1 for _ in f)
            stats["documents_processed"] += 1
            stats["chunks_created"] += chunk_count
            state[doc_id] = {
                "content_hash": record.get("content_hash"),
                "chunk_count": chunk_count,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
            # Saved per document, not once at the end: a run killed partway
            # through must not redo the documents it already finished.
            save_state(domain, state)
        else:
            stats["documents_failed"] += 1
            _log_failure(domain, doc_id, local_path, result)

    return stats


if __name__ == "__main__":
    # Internal single-document worker spawned by process_domain via subprocess.
    # Not a general CLI - scripts/rebuild_vector_index.py is the public entry point.
    _domain, _doc_id = sys.argv[1], sys.argv[2]
    _manifest_path = DATA_DIR / "raw" / "documents" / _domain / "manifest.jsonl"
    _record = doc_manifest.load(_manifest_path)[_doc_id]
    _process_single_document(_domain, _doc_id, _record)
