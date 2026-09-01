"""Persistent DuckDB store for curated analytical tables (architecture doc §11).

One analytics.duckdb file per domain, at data/curated/<domain>/analytics.duckdb -
the same file both holds the tables and is queried directly by the future
query_analytics tool. Parquet exports alongside it are the lake's curated
artifact per §6, not a separate source of truth.
"""
from pathlib import Path

import duckdb

DATA_DIR = Path("data")


def connect(domain: str) -> duckdb.DuckDBPyConnection:
    db_path = DATA_DIR / "curated" / domain / "analytics.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def export_parquet(con: duckdb.DuckDBPyConnection, table: str, domain: str) -> Path:
    """Write one table to data/curated/<domain>/<table>.parquet."""
    out_path = DATA_DIR / "curated" / domain / f"{table}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY {table} TO '{out_path.as_posix()}' (FORMAT PARQUET)")
    return out_path


def create_dim_date_view(con: duckdb.DuckDBPyConnection) -> None:
    """A view, not a materialized table - date arithmetic on crash_date is
    cheap in DuckDB and this way it can never drift out of sync with
    fact_crashes. dim_location isn't built at all: the real Socrata data has
    no municipality/community field to populate it with (see
    PROJECT_STATUS.txt), and fact_crashes already carries road_name/lat/lon
    inline - a separate dimension table would be speculative modeling with
    no consumer yet (architecture doc §11: "Do not model every possible
    field before there is a user-facing need for it").
    """
    con.execute("""
        CREATE OR REPLACE VIEW dim_date AS
        SELECT DISTINCT
            crash_date AS date,
            EXTRACT(year FROM crash_date) AS year,
            EXTRACT(quarter FROM crash_date) AS quarter,
            EXTRACT(month FROM crash_date) AS month,
            dayname(crash_date) AS day_of_week
        FROM fact_crashes
        WHERE crash_date IS NOT NULL
    """)
