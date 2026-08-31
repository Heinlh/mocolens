"""Downloads new/changed documents into the raw lake and updates the manifest."""
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import manifest as manifest_mod


def sync(
    domain: str,
    urls: list[str],
    dest_dir: Path,
    manifest_path: Path,
    client: httpx.Client | None = None,
    force: bool = False,
) -> dict:
    """Download new/changed URLs into dest_dir, updating the manifest.

    Returns counts: discovered/new/changed/skipped.
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True)
    records = manifest_mod.load(manifest_path)
    stats = {"discovered": len(urls), "new": 0, "changed": 0, "skipped": 0}

    try:
        for url in urls:
            doc_id = manifest_mod.document_id(url)
            existing = records.get(doc_id)

            head = client.head(url)
            etag = head.headers.get("etag")
            last_modified = head.headers.get("last-modified")

            if not force and existing and etag and existing.get("http_etag") == etag:
                stats["skipped"] += 1
                continue

            resp = client.get(url)
            resp.raise_for_status()
            new_hash = manifest_mod.content_hash(resp.content)

            if not force and not manifest_mod.has_changed(
                existing, etag=etag, last_modified=last_modified, new_hash=new_hash
            ):
                stats["skipped"] += 1
                continue

            dest_dir.mkdir(parents=True, exist_ok=True)
            filename = url.rstrip("/").rsplit("/", 1)[-1] or f"{doc_id}.pdf"
            local_path = dest_dir / filename
            local_path.write_bytes(resp.content)

            stats["new" if existing is None else "changed"] += 1
            records[doc_id] = {
                "document_id": doc_id,
                "source_url": url,
                "domain": domain,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": new_hash,
                "http_etag": etag,
                "last_modified": last_modified,
                "local_path": str(local_path),
                "status": "downloaded",
            }
    finally:
        if owns_client:
            client.close()

    manifest_mod.save(manifest_path, records)
    return stats
