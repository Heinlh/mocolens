"""Vector index over document chunks (§12).

Two deliberate departures from the obvious stack, both driven by fitting a
512 MB Render instance:

1. The model runs under onnxruntime, not sentence-transformers/PyTorch.
   Importing torch alone measured +390 MB RSS, and serving only ever needs
   one short question embedded per report search. The exported artifact
   lives in MODEL_DIR (scripts/export_embedding_onnx.py writes it) and
   reproduces the PyTorch build's output to 7 decimal places, so an index
   embedded with either is searchable by the other.
2. The index is a flat float32 array in one .npz file, not Chroma. This
   corpus is ~300 chunks of county reports; a brute-force dot product over
   a 300x384 matrix is well under a millisecond and needs no index
   structure at all, while importing Chroma and opening its collection
   measured ~85 MB of RSS. Chroma earns its keep at a scale this corpus is
   nowhere near - if the document set grows by two orders of magnitude,
   that is the point to reach for it again.

Embeddings are computed explicitly rather than by an embedding function the
store owns, so the model choice stays ours.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

# Defined here, not in processing/chunker.py: this module is needed at API
# serve time (search_reports embeds the query with the same model), and
# chunker.py imports Docling at module level - pulling EMBEDDING_MODEL from
# there would drag Docling (and its multi-GB GPU torch build) into the
# serving process for a constant that has nothing to do with chunking.
# chunker.py imports it from here instead.
EMBEDDING_MODEL = "ibm-granite/granite-embedding-30m-english"

# Working-directory relative, like DATA_DIR elsewhere: the package is
# pip-installed into site-packages in the container, so a path resolved
# from __file__ would point outside the app directory entirely.
MODEL_DIR = Path("models") / "granite-embedding-30m"
PERSIST_DIR = Path("data/curated")
INDEX_FILE = "reports_index.npz"
MAX_TOKENS = 512
_BATCH = 32

_session: Any | None = None
_tokenizer: Any | None = None
_index_cache: dict[Path, tuple[np.ndarray, list[dict]]] = {}


def _get_encoder():
    """(tokenizer, onnx session), loaded once per process."""
    global _session, _tokenizer
    if _session is None:
        import onnxruntime
        from tokenizers import Tokenizer

        model_path = MODEL_DIR / "model.onnx"
        if not model_path.exists():
            raise FileNotFoundError(
                f"{model_path} missing - run scripts/export_embedding_onnx.py first."
            )
        options = onnxruntime.SessionOptions()
        # One thread and no arena: this runs one short query at a time on a
        # small shared instance, where a thread pool and a growing allocator
        # arena cost more memory than they save in latency.
        options.intra_op_num_threads = 1
        options.enable_cpu_mem_arena = False
        _tokenizer = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
        _tokenizer.enable_truncation(max_length=MAX_TOKENS)
        _tokenizer.enable_padding()
        _session = onnxruntime.InferenceSession(
            str(model_path), options, providers=["CPUExecutionProvider"]
        )
    return _tokenizer, _session


def encode(texts: list[str]) -> np.ndarray:
    """CLS-pooled, L2-normalized embeddings - the same three stages
    sentence-transformers applies for this model (Transformer -> CLS
    pooling -> Normalize, per its modules.json). Normalizing here is what
    lets search() treat a dot product as cosine similarity.
    """
    tokenizer, session = _get_encoder()
    batches = []
    for start in range(0, len(texts), _BATCH):
        encodings = tokenizer.encode_batch(texts[start:start + _BATCH])
        feeds = {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
        }
        cls = session.run(None, feeds)[0][:, 0].astype(np.float32)
        batches.append(cls / np.linalg.norm(cls, axis=1, keepdims=True))
    if not batches:
        return np.zeros((0, 384), dtype=np.float32)
    return np.vstack(batches)


def index_path(domain: str, persist_dir: Path | None = None) -> Path:
    return (persist_dir or PERSIST_DIR) / domain / INDEX_FILE


def load_index(domain: str, persist_dir: Path | None = None) -> tuple[np.ndarray, list[dict]]:
    """(embeddings, records) for a domain, read once per process.

    Records carry the chunk text and every metadata field a citation needs,
    in the same row order as the embedding matrix.
    """
    path = index_path(domain, persist_dir)
    cached = _index_cache.get(path)
    if cached is not None:
        return cached

    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing - run scripts/rebuild_vector_index.py --domain {domain} first."
        )
    # allow_pickle stays off: records travel as a JSON string, so a corrupt
    # or swapped index file can never execute anything on load.
    with np.load(path, allow_pickle=False) as data:
        index = (data["embeddings"].astype(np.float32), json.loads(str(data["records"])))
    _index_cache[path] = index
    return index


def save_index(
    domain: str, embeddings: np.ndarray, records: list[dict], persist_dir: Path | None = None
) -> Path:
    """Write a domain's index, stamped with its build time.

    The stamp travels inside the .npz because the index file is what ships
    in the container image - logs/ and data/raw/ do not, so a build time
    recorded anywhere else is unreadable in production (the same reason
    processing/curate.py writes build_info.json next to the curated tables).
    """
    path = index_path(domain, persist_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        embeddings=embeddings.astype(np.float32),
        records=np.array(json.dumps(records)),
        built_at=np.array(datetime.now(timezone.utc).isoformat()),
    )
    _index_cache.pop(path, None)
    return path


def index_info(domain: str, persist_dir: Path | None = None) -> dict | None:
    """Document-level summary of a domain's index, or None if none exists.

    One entry per indexed document (not per chunk), so callers that need to
    describe the corpus - GET /api/sources, refresh smoke tests - do not
    have to know the chunk record layout.
    """
    path = index_path(domain, persist_dir)
    if not path.exists():
        return None

    with np.load(path, allow_pickle=False) as data:
        built_at = str(data["built_at"]) if "built_at" in data.files else None

    _, records = load_index(domain, persist_dir)
    documents: dict[str, dict] = {}
    for record in records:
        document = documents.setdefault(record["document_id"], {
            "document_id": record["document_id"],
            "title": record.get("title"),
            "source_url": record.get("source_url"),
            "year": record.get("year"),
            "chunk_count": 0,
            "page_start": None,
            "page_end": None,
        })
        document["chunk_count"] += 1
        for key, pick in (("page_start", min), ("page_end", max)):
            page = record.get(key)
            if isinstance(page, int):
                current = document[key]
                document[key] = page if current is None else pick(current, page)

    return {
        "built_at": built_at,
        "chunk_count": len(records),
        "documents": sorted(
            documents.values(),
            key=lambda d: (-(d["year"] or 0), d["title"] or ""),
        ),
    }


def replace_document(
    domain: str, document_id: str, chunks: list[dict], persist_dir: Path | None = None
) -> int:
    """Make a domain's index hold exactly `chunks` for one document.

    Rows belonging to other documents are untouched, so a refresh re-embeds
    only what changed rather than rebuilding the whole index (§24: "Do not
    rebuild the entire vector database if only one document changed").

    Replace, not upsert, because chunk ids are positional -
    sha256("<document_id>:<i>") - so a revised PDF that yields fewer chunks
    than the version before it would otherwise leave the tail of the old text
    searchable forever, still cited with its old page numbers. Passing an
    empty `chunks` list therefore removes the document from the index.

    Read-modify-write of the whole file, which is the right trade at this
    size: the index is a few hundred rows, and the alternative is running a
    mutable store just to avoid rewriting a megabyte during ingestion.

    Returns the number of chunks now indexed for the document.
    """
    if index_path(domain, persist_dir).exists():
        stored, records = load_index(domain, persist_dir)
        keep = [i for i, record in enumerate(records) if record.get("document_id") != document_id]
        embeddings = stored[keep] if keep else np.zeros((0, stored.shape[1]), dtype=np.float32)
        records = [records[i] for i in keep]
    else:
        embeddings, records = np.zeros((0, 384), dtype=np.float32), []

    if chunks:
        added = [{k: v for k, v in chunk.items() if v is not None} for chunk in chunks]
        embeddings = np.vstack([embeddings, encode([chunk["text"] for chunk in chunks])])
        records.extend(added)

    save_index(domain, embeddings, records, persist_dir)
    return len(chunks)


def search(
    domain: str,
    query: str,
    top_k: int = 5,
    year_at_least: int | None = None,
    persist_dir: Path | None = None,
) -> list[dict]:
    """Semantic search over a domain's chunks (§14.2 search_reports tool).

    `similarity` is cosine similarity, which for these unit-length vectors
    is just the dot product.
    """
    embeddings, records = load_index(domain, persist_dir)
    rows = np.arange(len(records))
    if year_at_least is not None:
        rows = rows[[
            isinstance(records[i].get("year"), int) and records[i]["year"] >= year_at_least
            for i in rows
        ]]
    if rows.size == 0:
        return []

    scores = embeddings[rows] @ encode([query])[0]
    order = np.argsort(-scores)[:top_k]
    return [{**records[rows[i]], "similarity": float(scores[i])} for i in order]
