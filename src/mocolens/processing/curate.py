"""Orchestrates the structured transform: raw Socrata JSON -> curated
fact_crashes / fact_participants tables + Parquet + DuckDB (§10, §11).

One domain module per domain (currently just vision_zero), same pattern as
ingestion/runner.py's FETCHERS dict - adding a new domain means writing a
transforms/<domain>.py with a build(con, snapshot_dir) function and adding
one line here, not touching this orchestrator.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from ..storage import duckdb_store
from .transforms import vision_zero

DATA_DIR = Path("data")
LOG_PATH = Path("logs/curation/runs.jsonl")
BUILD_INFO_FILE = "build_info.json"

_BUILDERS = {"vision_zero": vision_zero.build}

CURATED_TABLES = ["fact_participants", "fact_crashes"]


def build_info_path(domain: str) -> Path:
    return DATA_DIR / "curated" / domain / BUILD_INFO_FILE


def build_info(domain: str) -> dict | None:
    """What the shipped curated artifacts say about their own build.

    Written next to the tables (not only to logs/curation/runs.jsonl) because
    logs/ is gitignored and excluded from the container image, so the log is
    unreadable in production - freshness read from it alone is always None
    once deployed.
    """
    path = build_info_path(domain)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def data_as_of(domain: str) -> str | None:
    """Freshness marker for a domain: when its curated tables were built.

    Prefers the shipped sidecar, falling back to the local run log for a
    working tree curated before the sidecar existed.
    """
    info = build_info(domain)
    if info and info.get("built_at"):
        return info["built_at"]
    return (latest_run_info(domain) or {}).get("ran_at")


def latest_run_info(domain: str) -> dict | None:
    """The most recent logged curation run for a domain, or None if it has
    never been run. The full run record, quality report included; callers
    that only want freshness should use data_as_of(), which also works in
    the container image where logs/ is absent.
    """
    if not LOG_PATH.exists():
        return None
    latest = None
    with LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("domain") == domain:
                latest = entry
    return latest


def _latest_snapshot_dir(domain: str) -> Path:
    """The most recent data/raw/api/<domain>/<date>/ snapshot directory."""
    api_dir = DATA_DIR / "raw" / "api" / domain
    if not api_dir.exists():
        raise FileNotFoundError(f"No raw API data for domain '{domain}' - run scripts/ingest.py first.")
    dated_dirs = sorted((p for p in api_dir.iterdir() if p.is_dir()), key=lambda p: p.name)
    if not dated_dirs:
        raise FileNotFoundError(f"{api_dir} has no dated snapshots - run scripts/ingest.py first.")
    return dated_dirs[-1]


def curate_domain(domain: str, snapshot_date: str | None = None) -> dict:
    """Build curated tables for one domain from its latest (or a specific) raw snapshot."""
    build = _BUILDERS.get(domain)
    if build is None:
        raise ValueError(f"No transform registered for domain '{domain}'")

    snapshot_dir = (
        DATA_DIR / "raw" / "api" / domain / snapshot_date
        if snapshot_date else _latest_snapshot_dir(domain)
    )

    con = duckdb_store.connect(domain)
    try:
        report = build(con, snapshot_dir)
        duckdb_store.create_dim_date_view(con)

        row_counts = {}
        for table in CURATED_TABLES:
            duckdb_store.export_parquet(con, table, domain)
            row_counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        coverage = con.execute("SELECT MIN(crash_date), MAX(crash_date) FROM fact_crashes").fetchone()
    finally:
        con.close()

    built_at = datetime.now(timezone.utc).isoformat()
    result = {
        "domain": domain,
        "snapshot_dir": str(snapshot_dir),
        "row_counts": row_counts,
        "quality_report": report.to_dict(),
    }

    build_info_path(domain).write_text(
        json.dumps({
            "domain": domain,
            "built_at": built_at,
            "snapshot_date": Path(snapshot_dir).name,
            "row_counts": row_counts,
            "coverage_start": coverage[0].isoformat() if coverage[0] else None,
            "coverage_end": coverage[1].isoformat() if coverage[1] else None,
        }, indent=2),
        encoding="utf-8",
    )

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "domain": domain,
            "ran_at": datetime.now(timezone.utc).isoformat(),
            **result,
        }) + "\n")

    return result
