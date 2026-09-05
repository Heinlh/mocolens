"""Extensive tests for query_analytics - the tool that runs LLM-generated
SQL, so both correctness and every adversarial rejection path are covered.
Uses a small isolated fixture database (not the real curated data) so
these run fast and don't depend on the pipeline having been run first.
"""
import duckdb
import pytest

from mocolens.retrieval import sql_tool


@pytest.fixture(autouse=True)
def fixture_curated_dir(tmp_path, monkeypatch):
    """Point sql_tool at a tiny throwaway curated dataset + a tmp audit log."""
    curated_dir = tmp_path / "data" / "curated" / "vision_zero"
    curated_dir.mkdir(parents=True)

    con = duckdb.connect(":memory:")
    con.execute("""
        CREATE TABLE fact_crashes AS SELECT * FROM (VALUES
            ('C1', DATE '2023-01-01', 39.05, -77.10, 'injury', true, false, 0, 1),
            ('C2', DATE '2023-06-01', 39.10, -77.20, 'fatal', false, true, 1, 2),
            ('C3', DATE '2024-01-01', NULL, NULL, 'property_damage', false, false, 0, 0)
        ) AS t(crash_id, crash_date, latitude, longitude, severity,
               pedestrian_involved, cyclist_involved, fatality_count, injury_count)
    """)
    con.execute("""
        CREATE TABLE fact_participants AS SELECT * FROM (VALUES
            ('P1', 'C1', 'driver', 'no_apparent_injury'),
            ('P2', 'C2', 'cyclist', 'fatal_injury')
        ) AS t(participant_id, crash_id, participant_type, injury_severity)
    """)
    con.execute(f"COPY fact_crashes TO '{(curated_dir / 'fact_crashes.parquet').as_posix()}'")
    con.execute(f"COPY fact_participants TO '{(curated_dir / 'fact_participants.parquet').as_posix()}'")
    con.close()

    monkeypatch.setattr(sql_tool, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(sql_tool, "AUDIT_LOG", tmp_path / "logs" / "sql_queries.jsonl")
    # Point the curation layer at the same empty tmp tree, so data_as_of
    # resolves through its real code path and finds no build here.
    monkeypatch.setattr("mocolens.processing.curate.DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("mocolens.processing.curate.LOG_PATH", tmp_path / "logs" / "curation.jsonl")
    yield


def test_valid_select_returns_real_rows():
    r = sql_tool.query_analytics(
        question="how many crashes", sql="SELECT COUNT(*) FROM fact_crashes", reason="test",
    )
    assert r["error"] is None
    assert r["row_count"] == 1
    assert r["rows"] == [[3]]


def test_valid_select_with_filter_and_group_by():
    r = sql_tool.query_analytics(
        question="pedestrian crashes", reason="test",
        sql="SELECT severity, COUNT(*) FROM fact_crashes WHERE pedestrian_involved GROUP BY severity",
    )
    assert r["error"] is None
    assert r["rows"] == [["injury", 1]]


@pytest.mark.parametrize("sql,expected_fragment", [
    ("SELECT 1; DROP TABLE fact_crashes;", "one SQL statement"),
    ("DROP TABLE fact_crashes", "only SELECT"),
    ("INSERT INTO fact_crashes VALUES ('x')", "only SELECT"),
    ("UPDATE fact_crashes SET severity = 'x'", "only SELECT"),
    ("DELETE FROM fact_crashes", "only SELECT"),
    ("CREATE TABLE evil AS SELECT 1", "only SELECT"),
    ("ALTER TABLE fact_crashes ADD COLUMN x INT", "only SELECT"),
    ("ATTACH 'evil.db'", "disallowed keyword"),
    ("PRAGMA database_list", "disallowed keyword"),
    ("COPY fact_crashes TO 'exfil.csv'", "disallowed keyword"),
    ("CALL pragma_version()", "disallowed keyword"),
    ("", "empty query"),
    ("   ", "empty query"),
    ("this is not sql", "failed to parse"),
])
def test_rejected_queries(sql, expected_fragment):
    r = sql_tool.query_analytics(question="x", sql=sql, reason="attack test")
    assert r["error"] is not None
    assert expected_fragment.lower() in r["error"].lower()
    assert r["rows"] == []
    assert r["row_count"] == 0


def test_read_parquet_filesystem_escape_blocked():
    # even if the keyword filter somehow missed it, enable_external_access=false
    # makes this fail at the engine level
    r = sql_tool.query_analytics(
        question="x", reason="attack test",
        sql="SELECT * FROM read_csv_auto('/etc/passwd')",
    )
    assert r["error"] is not None


def test_offset_is_not_falsely_rejected():
    """Regression: an early version's keyword filter matched 'set ' as a
    substring of 'offset ', which would have rejected any query using
    SQL's OFFSET clause. Whole-word regex fixed this.
    """
    r = sql_tool.query_analytics(
        question="x", reason="test",
        sql="SELECT * FROM fact_crashes ORDER BY crash_id LIMIT 1 OFFSET 1",
    )
    assert r["error"] is None
    assert r["row_count"] == 1


def test_column_named_like_a_keyword_fragment_is_not_rejected():
    # 'road_name' etc. contain no whole disallowed keyword, but this guards
    # against a future overbroad keyword regex catching legitimate schema terms.
    r = sql_tool.query_analytics(
        question="x", reason="test",
        sql="SELECT crash_id FROM fact_crashes WHERE crash_id = 'C1'",
    )
    assert r["error"] is None


def test_row_limit_is_enforced_even_without_explicit_limit():
    r = sql_tool.query_analytics(question="x", sql="SELECT * FROM fact_crashes", reason="test", max_rows=2)
    assert r["row_count"] == 2


def test_query_result_is_wrapped_and_clamped_in_returned_query_text():
    r = sql_tool.query_analytics(question="x", sql="SELECT * FROM fact_crashes", reason="test", max_rows=2)
    assert "LIMIT 2" in r["query"]


def test_out_of_bounds_coordinates_already_null_pass_through():
    r = sql_tool.query_analytics(
        question="x", reason="test",
        sql="SELECT latitude, longitude FROM fact_crashes WHERE crash_id = 'C3'",
    )
    assert r["rows"] == [[None, None]]


def test_unknown_domain_raises_not_silently_empty():
    with pytest.raises(ValueError, match="No curated tables registered"):
        sql_tool.query_analytics(question="x", sql="SELECT 1", reason="test", domain="nonexistent")


def test_missing_curated_parquet_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sql_tool, "DATA_DIR", tmp_path / "empty")
    with pytest.raises(FileNotFoundError, match="build_curated_tables"):
        sql_tool.query_analytics(question="x", sql="SELECT 1", reason="test")


def test_timeout_interrupts_a_slow_query():
    # A cross join over the tiny fixture tables finishes instantly regardless
    # of timeout - range() generates real work independent of fixture size.
    r = sql_tool.query_analytics(
        question="x", reason="test", timeout_seconds=0.3,
        sql="SELECT COUNT(*) FROM range(500000000) a, range(10) b",
    )
    assert r["error"] is not None


def test_audit_log_records_both_success_and_rejection(tmp_path):
    sql_tool.query_analytics(question="q1", sql="SELECT 1", reason="r1")
    sql_tool.query_analytics(question="q2", sql="DROP TABLE fact_crashes", reason="r2")

    lines = sql_tool.AUDIT_LOG.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    import json
    entries = [json.loads(line) for line in lines]
    assert entries[0]["error"] is None
    assert entries[1]["error"] is not None


# --- the shared sandbox ---

def test_sandbox_is_built_once_and_reused_across_queries():
    # Loading both fact tables costs ~63 MB against the real curated data;
    # rebuilding that per query was the single largest avoidable allocation
    # in the request path.
    sql_tool.query_analytics(question="q1", sql="SELECT 1", reason="r")
    first = sql_tool._sandbox("vision_zero")
    sql_tool.query_analytics(question="q2", sql="SELECT 2", reason="r")
    assert sql_tool._sandbox("vision_zero") is first


def test_reused_sandbox_still_refuses_file_access():
    # Reuse must not weaken the sandbox: each query runs on a cursor off the
    # shared connection, and a cursor inherits enable_external_access=false.
    r = sql_tool.query_analytics(
        question="x", reason="test",
        sql="SELECT * FROM read_csv('/etc/passwd')",
    )
    assert r["error"] is not None
    assert r["rows"] == []


def test_reused_sandbox_cannot_be_unlocked_by_a_later_query():
    sql_tool.query_analytics(question="x", sql="SET enable_external_access = true", reason="r")
    r = sql_tool.query_analytics(
        question="x", sql="SELECT * FROM read_parquet('/tmp/anything.parquet')", reason="r",
    )
    assert r["error"] is not None
