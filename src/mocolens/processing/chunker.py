"""Structure-aware chunking via Docling's HybridChunker (§9), tokenized
against the Granite embedding model so chunk sizes match what actually gets
embedded rather than an approximate word count.
"""
import hashlib
import re

from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

EMBEDDING_MODEL = "ibm-granite/granite-embedding-30m-english"
MAX_TOKENS = 800  # top of the doc's 500-900 token target (§9)

_tokenizer = HuggingFaceTokenizer.from_pretrained(model_name=EMBEDDING_MODEL, max_tokens=MAX_TOKENS)
_chunker = HybridChunker(tokenizer=_tokenizer, merge_peers=True)

# ponytail: filename regex heuristic for publication year, not PDF content
# inspection. Upgrade to reading the report's title page if this starts
# missing real reports.
_FY_RE = re.compile(r"FY(\d{2})(?!\d)", re.IGNORECASE)
_YEAR_RE = re.compile(r"(20\d{2})")


def guess_year(filename: str) -> int | None:
    """Best-effort publication year from a filename (e.g. FY25_..._Report.pdf)."""
    fy_match = _FY_RE.search(filename)
    if fy_match:
        return 2000 + int(fy_match.group(1))
    year_match = _YEAR_RE.search(filename)
    return int(year_match.group(1)) if year_match else None


def chunk_document(doc, *, document_id: str, title: str, domain: str,
                    source_url: str, year: int | None) -> list[dict]:
    """Chunk a parsed Docling document into records matching the §9 chunk schema."""
    records = []
    for i, chunk in enumerate(_chunker.chunk(doc)):
        pages = [prov.page_no for item in chunk.meta.doc_items for prov in item.prov]
        section = " > ".join(chunk.meta.headings) if chunk.meta.headings else None

        records.append({
            "chunk_id": hashlib.sha256(f"{document_id}:{i}".encode()).hexdigest(),
            "document_id": document_id,
            "title": title,
            "page_start": min(pages) if pages else None,
            "page_end": max(pages) if pages else None,
            "section": section,
            "year": year,
            "domain": domain,
            "source_url": source_url,
            # contextualize() prepends heading context, which is what actually
            # gets embedded - keeps a chunk meaningful in isolation.
            "text": _chunker.contextualize(chunk),
        })
    return records
