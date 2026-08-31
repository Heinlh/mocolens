"""Orchestrates extraction (API + documents) for one domain, per config/sources.yaml.

Scope: fetch + save-raw only (§10 steps 1-3, §8.1). Schema validation,
normalization, and Parquet/DuckDB writes belong to the processing/ stage,
not here.
"""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import yaml

from .api import socrata
from .documents import crawler, downloader

DATA_DIR = Path("data")
LOG_PATH = Path("logs/ingestion/runs.jsonl")

FETCHERS = {"socrata": socrata.fetch_all}


def load_config(path: Path = Path("config/sources.yaml")) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def extract_api(domain: str, sources: list[dict]) -> dict:
    """Fetch each API source and write it as-is to the raw data lake."""
    today = date.today().isoformat()
    out_dir = DATA_DIR / "raw" / "api" / domain / today
    stats = {"sources_checked": 0, "records_downloaded": 0}

    for source in sources:
        fetch = FETCHERS.get(source["type"])
        if fetch is None:
            raise ValueError(f"Unknown API source type: {source['type']}")

        stats["sources_checked"] += 1
        started = datetime.now(timezone.utc).isoformat()
        try:
            records = fetch(source)
        except httpx.HTTPError as exc:
            _log_run(domain, source["id"], "api", started, 0, False, str(exc))
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{source['id']}.json").write_text(json.dumps(records), encoding="utf-8")
        stats["records_downloaded"] += len(records)
        _log_run(domain, source["id"], "api", started, len(records), True, None)

    return stats


def extract_documents(domain: str, sources: list[dict], force: bool = False) -> dict:
    """Discover and download documents for each configured source."""
    stats = {"discovered": 0, "new": 0, "changed": 0, "skipped": 0}

    for source in sources:
        if source["type"] != "webpage":
            raise ValueError(f"Unknown document source type: {source['type']}")

        urls = crawler.discover(source)
        dest_dir = DATA_DIR / "raw" / "documents" / domain / "PDFs"
        manifest_path = DATA_DIR / "raw" / "documents" / domain / "manifest.jsonl"

        run_stats = downloader.sync(domain, urls, dest_dir, manifest_path, force=force)
        for key in stats:
            stats[key] += run_stats[key]

    return stats


def _log_run(domain: str, source_id: str, kind: str, started_at: str,
             record_count: int, success: bool, error: str | None) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "domain": domain,
        "source_id": source_id,
        "kind": kind,
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "record_count": record_count,
        "success": success,
        "error": error,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run(domain: str, api_only: bool = False, documents_only: bool = False, force: bool = False) -> dict:
    config = load_config()
    domain_config = config["domains"][domain]
    result: dict = {"domain": domain}

    if not documents_only:
        result["api"] = extract_api(domain, domain_config.get("api_sources", []))
    if not api_only:
        result["documents"] = extract_documents(domain, domain_config.get("document_sources", []), force=force)

    return result
