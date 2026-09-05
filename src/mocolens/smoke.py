"""Post-refresh smoke checks (architecture doc §24's final step).

A refresh replaces the artifacts the public app serves, so the question these
answer is narrow: after this run, can the app still answer questions from real
data? Each check reads a shipped artifact the way the serving path reads it -
the curated DuckDB, build_info.json, the .npz report index - rather than
re-deriving anything, so a check passes only if the thing the API will
actually open is sound.

They are not a substitute for the pipeline's own quality checks
(processing/quality.py), which run inside curation and can stop a bad build
before it is written. These run afterwards, across layers, and catch what no
single layer can see: a curated table that built cleanly but lost 90% of its
rows, an index whose documents no longer match the manifest, a build that
completed but left the API unable to start. Nothing here re-checks what
curation already checks - referential integrity between the fact tables, for
instance, is processing/quality.py's job and is a known-and-accepted soft
violation on this data, so repeating it here would block every refresh over
something the pipeline deliberately allows.

Severity mirrors processing/quality.py: a "hard" failure means the refresh
must not be published, a "soft" one is worth reporting but not blocking.
"""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from .ingestion.documents import manifest as doc_manifest
from .processing import curate
from .storage import vector_store

DATA_DIR = Path("data")

# A snapshot older than this means the scheduled refresh has silently stopped
# reaching the county's API - the tables would still be valid, just stale.
MAX_SNAPSHOT_AGE_DAYS = 45
# Socrata occasionally serves a partial response. A curated build that lost
# this much of the previous build's rows is treated as a bad extract rather
# than a real drop in crashes.
MAX_ROW_LOSS_FRACTION = 0.1


@dataclass
class SmokeResult:
    name: str
    severity: str  # "hard" | "soft"
    passed: bool
    detail: str

    def __str__(self) -> str:
        return f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}"


def _ok(name: str, detail: str, severity: str = "hard") -> SmokeResult:
    return SmokeResult(name=name, severity=severity, passed=True, detail=detail)


def _fail(name: str, detail: str, severity: str = "hard") -> SmokeResult:
    return SmokeResult(name=name, severity=severity, passed=False, detail=detail)


def _check_build_info(domain: str) -> SmokeResult:
    info = curate.build_info(domain)
    if info is None:
        return _fail("build_info", f"{curate.build_info_path(domain)} missing or unreadable")
    missing = [k for k in ("built_at", "snapshot_date", "row_counts") if not info.get(k)]
    if missing:
        return _fail("build_info", f"missing field(s): {', '.join(missing)}")
    return _ok("build_info", f"built {info['built_at']} from snapshot {info['snapshot_date']}")


def _check_snapshot_freshness(domain: str, today: date) -> SmokeResult:
    info = curate.build_info(domain) or {}
    snapshot_date = info.get("snapshot_date")
    if not snapshot_date:
        return _fail("snapshot_freshness", "no snapshot date recorded", severity="soft")
    try:
        age = (today - date.fromisoformat(snapshot_date)).days
    except ValueError:
        return _fail("snapshot_freshness", f"unparseable snapshot date {snapshot_date!r}", severity="soft")
    if age > MAX_SNAPSHOT_AGE_DAYS:
        return _fail(
            "snapshot_freshness",
            f"newest API snapshot is {age} days old (limit {MAX_SNAPSHOT_AGE_DAYS})",
            severity="soft",
        )
    return _ok("snapshot_freshness", f"newest API snapshot is {age} days old", severity="soft")


def _check_curated_tables(domain: str, previous_counts: dict | None) -> list[SmokeResult]:
    db_path = DATA_DIR / "curated" / domain / "analytics.duckdb"
    if not db_path.exists():
        return [_fail("curated_tables", f"{db_path} missing")]

    results = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for table in curate.CURATED_TABLES:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count == 0:
                results.append(_fail(f"rows_{table}", "table is empty"))
                continue

            before = (previous_counts or {}).get(table)
            if before and count < before * (1 - MAX_ROW_LOSS_FRACTION):
                results.append(_fail(
                    f"rows_{table}",
                    f"{count:,} rows, down from {before:,} - more than "
                    f"{int(MAX_ROW_LOSS_FRACTION * 100)}% of the previous build is missing",
                ))
            else:
                results.append(_ok(f"rows_{table}", f"{count:,} rows"))

        # The dashboard windows everything back from this date, so a null one
        # means every KPI, chart, and hotspot comes back empty.
        latest = con.execute("SELECT MAX(crash_date) FROM fact_crashes").fetchone()[0]
        results.append(
            _ok("crash_coverage", f"crashes through {latest}") if latest
            else _fail("crash_coverage", "fact_crashes has no dated rows")
        )
    finally:
        con.close()
    return results


def _check_report_index(domain: str) -> list[SmokeResult]:
    info = vector_store.index_info(domain)
    if info is None:
        return [_fail("report_index", f"{vector_store.index_path(domain)} missing")]
    if info["chunk_count"] == 0:
        return [_fail("report_index", "index holds no chunks")]

    results = [_ok(
        "report_index",
        f"{info['chunk_count']:,} chunks across {len(info['documents'])} documents",
    )]

    # Every indexed document should still be one the raw manifest knows about.
    # A mismatch means a document was removed or re-keyed without its chunks
    # being cleaned up, and the agent could cite text no source backs.
    manifest_path = DATA_DIR / "raw" / "documents" / domain / "manifest.jsonl"
    known = set(doc_manifest.load(manifest_path))
    if known:
        unknown = [d["document_id"] for d in info["documents"] if d["document_id"] not in known]
        results.append(
            _ok("index_matches_manifest", "every indexed document is in the manifest") if not unknown
            else _fail("index_matches_manifest", f"{len(unknown)} indexed document(s) not in the manifest")
        )
    return results


def _check_report_search(domain: str) -> SmokeResult:
    """The whole retrieval path end to end: load the index, run the ONNX query
    encoder, and score. Cheap, and it is the piece with the most moving parts.
    """
    from .retrieval.report_tool import search_reports

    try:
        hits = search_reports("Vision Zero safety priorities", top_k=3, domain=domain)
    except FileNotFoundError as exc:
        return _fail("report_search", str(exc))
    if not hits:
        return _fail("report_search", "a plainly on-topic query returned nothing")
    return _ok("report_search", f"top hit {hits[0]['document_title']!r} at {hits[0]['similarity_score']}")


def _check_dashboard_builds(domain: str) -> SmokeResult:
    """The public dashboard, built from the artifacts this run produced."""
    from .api import dashboard_service

    try:
        summary = dashboard_service.get_dashboard_summary()
    except Exception as exc:  # noqa: BLE001 - any failure here is a failed refresh
        return _fail("dashboard_builds", f"{type(exc).__name__}: {exc}")
    if not summary.metrics or not summary.crash_trend:
        return _fail("dashboard_builds", "dashboard built but returned no metrics or trend")
    return _ok("dashboard_builds", f"{len(summary.metrics)} KPIs, {len(summary.crash_trend)} trend points")


def run_smoke_checks(
    domain: str, previous_counts: dict | None = None, today: date | None = None
) -> list[SmokeResult]:
    """Every post-refresh check for one domain, in dependency order.

    `previous_counts` is the row_counts of the build this run replaced, used
    to catch a partial extract that still produced a valid-looking table.
    """
    today = today or date.today()
    results = [_check_build_info(domain), _check_snapshot_freshness(domain, today)]
    results += _check_curated_tables(domain, previous_counts)
    results += _check_report_index(domain)
    results.append(_check_report_search(domain))
    results.append(_check_dashboard_builds(domain))
    return results


def failures(results: list[SmokeResult], severity: str = "hard") -> list[SmokeResult]:
    return [r for r in results if not r.passed and r.severity == severity]


def summarize(results: list[SmokeResult]) -> str:
    passed = sum(1 for r in results if r.passed)
    return f"{passed}/{len(results)} smoke checks passed"
