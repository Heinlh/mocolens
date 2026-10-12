"""query_analytics (architecture doc §14.1) - the one tool that lets an LLM
run SQL it wrote itself against real crash data. That makes it the tool
most worth being paranoid about, so the safety design here is layered and
each layer was verified empirically (see PROJECT_STATUS.txt), not assumed:

1. The query never touches the real analytics.duckdb file. A fresh
   in-memory connection loads ONLY the allow-listed tables, straight from
   their Parquet exports - there is no ATTACH, so there is no
   schema-qualified name (`src.other_table`) that could reach anything
   else. Confirmed empirically that ATTACH ... READ_ONLY + exposing one
   view is NOT enough on its own: the attached schema's other tables stay
   reachable by their qualified name regardless of which views exist.
2. Once the trusted tables are loaded, `enable_external_access = false`
   is set on the connection - this disables read_parquet/read_csv/COPY/
   ATTACH from inside SQL text entirely, and DuckDB refuses to let a
   later statement turn it back on. Without this, a crafted query could
   read (or even COPY out) any file on disk the process can see,
   regardless of which tables were "loaded" - confirmed empirically.
3. The query text is parsed with DuckDB's own parser
   (`extract_statements`), not regex - exactly one statement, and its
   type must be SELECT. A textual backstop additionally rejects a
   handful of keywords (pragma, attach, copy, ...) because at least one
   informational PRAGMA parses as StatementType.SELECT - confirmed
   empirically, not assumed safe.
4. The query is always wrapped in `SELECT * FROM (...) LIMIT n` - clamps
   row count regardless of what the inner query does.
5. A watchdog thread calls `connection.interrupt()` after a timeout -
   confirmed this actually aborts a running query, not just the wait.
6. The engine itself is capped (memory_limit, threads) and its
   configuration locked. The timeout alone does not bound memory: a query
   can allocate gigabytes well inside ten seconds.

Even if one of these had a gap, the others still hold - this is
defense in depth, not one clever trick.

The sandbox is built once per (domain, data directory) and reused. Loading
both fact tables costs ~63 MB, and rebuilding that for every single
LLM-issued query - up to 3 per question, on a 512 MB instance - was pure
waste. Each query still gets its own `.cursor()` off the shared database,
which is what keeps the reuse safe: a cursor inherits the locked-down
settings (verified: it can neither read files nor turn
enable_external_access back on) but owns its own interrupt, so one query
timing out cannot abort another running alongside it.
"""
import json
import logging
import re
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ..processing.curate import data_as_of as curated_data_as_of

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
AUDIT_LOG = Path("logs/retrieval/sql_queries.jsonl")

# Tables an LLM-generated query may reference, per domain. dim_date isn't
# listed here even though it's queryable - it's a view derived from
# fact_crashes at sandbox build time (see storage/duckdb_store), not a
# Parquet file of its own, so it doesn't need a row here to be usable.
ALLOWED_TABLES = {
    "vision_zero": ["fact_crashes", "fact_participants"],
}

# Whole-word, case-insensitive. Word boundaries matter here: a naive
# substring check on "load" would reject any query with "download" in it,
# and "set" would reject the perfectly legitimate SQL keyword OFFSET
# ("...offset..." contains "set") - both confirmed while testing this.
_DISALLOWED_KEYWORDS_RE = re.compile(
    r"\b(pragma|attach|detach|install|load|copy|export|import|call|vacuum)\b",
    re.IGNORECASE,
)

MAX_ROWS_DEFAULT = 500
TIMEOUT_SECONDS_DEFAULT = 10.0
# The loaded tables take ~57 MB of this; the rest is working memory for a
# query. Sized for the 512 MB instance: the rest of the serving path peaks
# near 250 MB, so this bounds the whole process around 410 MB. Ordinary
# agent queries run fine at 96 MB.
SANDBOX_MEMORY_LIMIT = "160MB"
SANDBOX_THREADS = 2

# Set by the API per request so an audit entry can be matched to the HTTP
# request that caused it. None outside a request (scripts, tests).
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# Keyed by data directory as well as domain: DATA_DIR is monkeypatched per
# test, and a sandbox built from a different directory holds different rows.
_sandboxes: dict[tuple[str, str], duckdb.DuckDBPyConnection] = {}
_sandbox_lock = threading.Lock()


class QueryRejected(Exception):
    """The submitted SQL failed validation before it was ever executed."""


def _build_sandbox(domain: str) -> duckdb.DuckDBPyConnection:
    """A fresh in-memory connection holding only this domain's allow-listed
    tables, loaded from their Parquet exports - never the real database file.
    """
    tables = ALLOWED_TABLES.get(domain)
    if tables is None:
        raise ValueError(f"No curated tables registered for domain '{domain}'")

    con = duckdb.connect(":memory:")
    curated_dir = DATA_DIR / "curated" / domain
    for table in tables:
        parquet_path = curated_dir / f"{table}.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(
                f"{parquet_path} missing - run scripts/build_curated_tables.py --domain {domain} first."
            )
        escaped = str(parquet_path).replace("'", "''")
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_parquet('{escaped}')")

    if "fact_crashes" in tables:
        from ..storage.duckdb_store import create_dim_date_view
        create_dim_date_view(con)

    # DuckDB's defaults are 80% of the host's RAM and every core. Measured
    # without a limit: one valid SELECT (a cross join feeding a GROUP BY)
    # took this process from 88 MB to 4.2 GB before the 10s watchdog fired -
    # an OOM kill on a 512 MB instance, from a query that passes every check
    # below. With the limit the same query fails in ~2s as an ordinary
    # "query failed" result and the sandbox stays usable.
    con.execute(f"SET memory_limit = '{SANDBOX_MEMORY_LIMIT}'")
    con.execute(f"SET threads = {SANDBOX_THREADS}")
    # From here on the connection cannot read or write any file, attach any
    # database, or have any of these settings changed by a later statement -
    # lock_configuration covers the two limits above (verified: a cursor
    # could otherwise SET memory_limit back up).
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def _sandbox(domain: str) -> duckdb.DuckDBPyConnection:
    """The shared, already-locked-down connection for this domain."""
    key = (domain, str(DATA_DIR))
    with _sandbox_lock:
        con = _sandboxes.get(key)
        if con is None:
            con = _sandboxes[key] = _build_sandbox(domain)
        return con


def _validate(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Raises QueryRejected with a human-readable reason, or returns silently."""
    stripped = sql.strip()
    if not stripped:
        raise QueryRejected("empty query")

    match = _DISALLOWED_KEYWORDS_RE.search(stripped)
    if match:
        raise QueryRejected(f"query contains a disallowed keyword: '{match.group(1)}'")

    try:
        statements = con.extract_statements(sql)
    except duckdb.Error as exc:
        raise QueryRejected(f"SQL failed to parse: {exc}") from exc

    if len(statements) != 1:
        raise QueryRejected(f"exactly one SQL statement is allowed, got {len(statements)}")
    if statements[0].type.name != "SELECT":
        raise QueryRejected(f"only SELECT statements are allowed, got {statements[0].type.name}")


def _run_with_timeout(con: duckdb.DuckDBPyConnection, sql: str, timeout_seconds: float):
    stop = threading.Event()

    def watchdog():
        if not stop.wait(timeout_seconds):
            con.interrupt()

    t = threading.Thread(target=watchdog, daemon=True)
    t.start()
    try:
        result = con.execute(sql)
        columns = [d[0] for d in result.description]
        rows = result.fetchall()
        return columns, rows
    finally:
        stop.set()


def _log(entry: dict) -> None:
    line = json.dumps(entry)
    # Also to the process log: the file below lives on the container's
    # ephemeral disk, which nobody can read on the deployed instance.
    logger.info("sql_audit %s", line)
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def query_analytics(
    question: str,
    sql: str,
    reason: str,
    *,
    domain: str = "vision_zero",
    max_rows: int = MAX_ROWS_DEFAULT,
    timeout_seconds: float = TIMEOUT_SECONDS_DEFAULT,
) -> dict:
    """Run one read-only, allow-listed SQL query against curated crash data (§14.1).

    Never raises for a bad or malicious query - returns {"error": "..."} instead,
    since this is meant to be called by an agent that should see why its query
    was rejected and try a different one, not crash on it. Raises only for
    programmer errors (unknown domain, curated tables not built yet).
    """
    audit_entry = {
        "request_id": request_id.get(),
        "domain": domain, "question": question, "sql": sql, "reason": reason,
        "asked_at": datetime.now(timezone.utc).isoformat(),
    }

    con = _sandbox(domain).cursor()
    try:
        _validate(con, sql)
        clamped_sql = f"SELECT * FROM ({sql.strip().rstrip(';')}) AS _q LIMIT {int(max_rows)}"
        columns, rows = _run_with_timeout(con, clamped_sql, timeout_seconds)
    except QueryRejected as exc:
        audit_entry["error"] = str(exc)
        _log(audit_entry)
        return {
            "columns": [], "rows": [], "row_count": 0,
            "query": sql, "data_as_of": None, "error": str(exc),
        }
    except duckdb.Error as exc:
        audit_entry["error"] = str(exc)
        _log(audit_entry)
        return {
            "columns": [], "rows": [], "row_count": 0,
            "query": sql, "data_as_of": None, "error": f"query failed: {exc}",
        }
    finally:
        # Closes this cursor only - the shared sandbox stays loaded.
        con.close()

    data_as_of = curated_data_as_of(domain)

    audit_entry["row_count"] = len(rows)
    audit_entry["error"] = None
    _log(audit_entry)

    return {
        "columns": columns,
        "rows": [list(r) for r in rows],
        "row_count": len(rows),
        "query": clamped_sql,
        "data_as_of": data_as_of,
        "error": None,
    }
