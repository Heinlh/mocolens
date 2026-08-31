"""Document manifest (§8.2/§8.3): dedup and change detection for the crawler."""
import hashlib
import json
from pathlib import Path


def load(manifest_path: Path) -> dict[str, dict]:
    """Load manifest.jsonl into {document_id: record}."""
    if not manifest_path.exists():
        return {}
    records = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            records[rec["document_id"]] = rec
    return records


def save(manifest_path: Path, records: dict[str, dict]) -> None:
    """Persist {document_id: record} back to manifest.jsonl."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(rec, sort_keys=True) for rec in records.values()]
    manifest_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def document_id(url: str) -> str:
    """Stable id for a document, derived from its source URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def has_changed(existing: dict | None, *, etag: str | None, last_modified: str | None, new_hash: str) -> bool:
    """True if a document is new, or differs from the manifest's last-known state."""
    if existing is None:
        return True
    if etag and existing.get("http_etag") == etag:
        return False
    if last_modified and existing.get("last_modified") == last_modified:
        return False
    return existing.get("content_hash") != new_hash
