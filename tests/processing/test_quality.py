import duckdb
import pytest

from mocolens.processing.quality import QualityError, QualityReport, run_check


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def test_soft_check_passing_records_result(con):
    report = QualityReport()
    violations = run_check(con, report, name="no_bad_rows", sql="SELECT 0", severity="soft")
    assert violations == 0
    assert report.checks[0].passed is True
    assert report.ok is True


def test_soft_check_failing_does_not_raise(con):
    report = QualityReport()
    violations = run_check(con, report, name="some_bad_rows", sql="SELECT 5", severity="soft", max_allowed=0)
    assert violations == 5
    assert report.checks[0].passed is False
    assert report.ok is False  # a failed soft check still shows up as not-ok on the report


def test_hard_check_failing_raises(con):
    report = QualityReport()
    with pytest.raises(QualityError):
        run_check(con, report, name="critical", sql="SELECT 1", severity="hard", max_allowed=0)
    # the failure is still recorded before the raise, for the log
    assert report.checks[0].violations == 1
    assert report.checks[0].passed is False


def test_hard_check_passing_does_not_raise(con):
    report = QualityReport()
    violations = run_check(con, report, name="critical", sql="SELECT 0", severity="hard", max_allowed=0)
    assert violations == 0
    assert report.ok is True


def test_max_allowed_threshold_respected(con):
    report = QualityReport()
    # 3 violations with max_allowed=5 should still pass
    run_check(con, report, name="tolerable", sql="SELECT 3", severity="hard", max_allowed=5)
    assert report.checks[0].passed is True
