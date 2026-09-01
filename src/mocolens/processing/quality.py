"""Data quality checks for curated crash tables (architecture doc §26).

Each check is a SQL query against an in-progress DuckDB connection that
returns a violation count. "hard" checks raise immediately - the doc's
"fail clearly rather than silently producing incorrect analytics." "soft"
checks are recorded and counted but don't stop the run: real crash data
always has some bad rows (a handful of out-of-bounds coordinates, a
missing injury severity), and refusing to build any curated table over
that would be worse than flagging it.
"""
from dataclasses import dataclass, field

import duckdb


class QualityError(Exception):
    """Raised when a hard data-quality check fails."""


@dataclass
class CheckResult:
    name: str
    severity: str  # "hard" | "soft"
    violations: int
    max_allowed: int
    passed: bool
    detail: str = ""


@dataclass
class QualityReport:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": [vars(c) for c in self.checks]}


def run_check(
    con: duckdb.DuckDBPyConnection,
    report: QualityReport,
    *,
    name: str,
    sql: str,
    severity: str = "soft",
    max_allowed: int = 0,
    detail: str = "",
) -> int:
    """Run a violation-count query (`sql` must return exactly one integer),
    record the result on `report`, and raise QualityError if a hard check
    fails. Returns the violation count either way, so callers can log it.
    """
    violations = con.execute(sql).fetchone()[0]
    passed = violations <= max_allowed
    report.add(CheckResult(
        name=name, severity=severity, violations=violations,
        max_allowed=max_allowed, passed=passed, detail=detail,
    ))
    if severity == "hard" and not passed:
        raise QualityError(
            f"{name}: {violations} violation(s) exceeds max_allowed={max_allowed}. {detail}"
        )
    return violations
