"""get_source_metadata (architecture doc §14.3): source freshness, dataset
descriptions, report dates, and provenance - combines the static registry
(config/sources.yaml) with real freshness signals pulled from the raw lake
and manifest, so "last_updated" reflects an actual run, not a guess.
"""
import json
from pathlib import Path

import yaml

DATA_DIR = Path("data")
CONFIG_PATH = Path("config/sources.yaml")


def _load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _latest_api_snapshot_date(domain: str) -> str | None:
    api_dir = DATA_DIR / "raw" / "api" / domain
    if not api_dir.exists():
        return None
    dated = sorted(p.name for p in api_dir.iterdir() if p.is_dir())
    return dated[-1] if dated else None


def _api_source_metadata(domain: str, source: dict) -> dict:
    snapshot_date = _latest_api_snapshot_date(domain)
    record_count = None
    if snapshot_date:
        snapshot_path = DATA_DIR / "raw" / "api" / domain / snapshot_date / f"{source['id']}.json"
        if snapshot_path.exists():
            record_count = len(json.loads(snapshot_path.read_text(encoding="utf-8")))
    return {
        "id": source["id"],
        "type": "dataset",
        "title": source.get("title", source["id"]),
        "description": source.get("description", ""),
        "source_url": source.get("url"),
        "refresh_cadence": source.get("refresh"),
        "last_updated": snapshot_date,
        "record_count": record_count,
    }


def _document_source_metadata(domain: str, source: dict) -> dict:
    manifest_path = DATA_DIR / "raw" / "documents" / domain / "manifest.jsonl"
    document_count = 0
    last_downloaded = None
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            document_count += 1
            downloaded_at = rec.get("downloaded_at")
            if downloaded_at and (last_downloaded is None or downloaded_at > last_downloaded):
                last_downloaded = downloaded_at
    return {
        "id": source["id"],
        "type": "report_collection",
        "title": source.get("title", source["id"]),
        "description": source.get("description", ""),
        "source_url": source.get("url"),
        "refresh_cadence": source.get("refresh"),
        "last_updated": last_downloaded,
        "record_count": document_count,
    }


def get_source_metadata(domain: str = "vision_zero") -> list[dict]:
    """All configured sources for a domain, each with real freshness/
    provenance info where it's available (None/0 if nothing has been
    ingested yet - never fabricated).
    """
    config = _load_config()
    domain_config = config.get("domains", {}).get(domain)
    if domain_config is None:
        raise ValueError(f"No source registry entry for domain '{domain}'")

    sources = []
    for source in domain_config.get("api_sources", []):
        sources.append(_api_source_metadata(domain, source))
    for source in domain_config.get("document_sources", []):
        sources.append(_document_source_metadata(domain, source))
    return sources
