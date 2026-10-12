"""The evaluation harness's own grading logic, with no model involved.

A harness that grades wrongly is worse than none - it reports a broken agent
as fine. Outcomes here are constructed by hand so each rule is checked
against a case where the right verdict is not in doubt.
"""
from pathlib import Path

import pytest

from mocolens import evaluation
from mocolens.evaluation import Outcome, contains, score


@pytest.mark.parametrize("text, expected, found", [
    ("There were 1,324 crashes on Georgia Ave.", 1324, True),
    ("There were 1324 crashes.", 1324, True),
    # A different number that merely contains the digits is not a match.
    ("There were 11,324 crashes.", 1324, False),
    ("About 4.3% of crashes involved a pedestrian.", 4.34, True),
    ("About 4% of crashes involved a pedestrian.", 4.34, True),
    ("About 6% of crashes involved a pedestrian.", 4.34, False),
    ("The program brought in $12.9 million.", 12.9, True),
    # FY25 is a label, not the number 25.
    ("In FY25 the program grew.", 25, False),
    ("Most crashes were on GEORGIA AVE.", "Georgia", True),
    ("Rear-end collisions are the most common.", ["rear end", "rear-end"], True),
    ("Sideswipes are the most common.", ["rear end", "rear-end"], False),
])
def test_contains_matches_facts_the_way_a_reader_would(text, expected, found):
    assert contains(text, expected) is found


def _case(**fields) -> dict:
    return {"id": "t", "category": "structured", "question": "q", **fields}


def test_an_answer_stating_every_expected_fact_is_correct():
    result = score(_case(), Outcome(answer_text="447 crashes in 2025."), [447])
    assert result.correct and result.problems == []


def test_an_answer_missing_a_fact_is_wrong_and_says_which():
    result = score(_case(), Outcome(answer_text="About 450 crashes."), [447])
    assert not result.correct
    assert "447" in result.problems[0]


def test_an_error_is_never_correct_even_with_nothing_expected():
    assert not score(_case(), Outcome(error="RuntimeError: no credentials"), []).correct


def test_a_valid_question_stopped_by_the_gate_is_a_failure_not_a_pass():
    result = score(_case(), Outcome(answer_text="Please ask about traffic.", gate_rejected=True), [])
    assert not result.correct


def test_an_out_of_scope_question_passes_by_gate_or_by_a_tool_free_decline():
    case = _case(category="unsupported", decline=True)
    assert score(case, Outcome(gate_rejected=True)).correct
    assert score(case, Outcome(answer_text="MoCoLens only covers traffic safety.")).correct
    answered = Outcome(answer_text="Here you go.", tools_called=["query_analytics"])
    assert not score(case, answered).correct


def test_required_tools_accept_alternatives_and_report_what_was_skipped():
    case = _case(tools=["query_analytics", ["percent_change", "year_over_year"]])
    assert score(case, Outcome(tools_called=["query_analytics", "year_over_year"])).tools_ok
    skipped = score(case, Outcome(tools_called=["query_analytics"]))
    assert skipped.tools_ok is False
    assert "percent_change or year_over_year" in skipped.problems[0]


def test_forbidden_tools_fail_the_tool_check_without_touching_correctness():
    case = _case(no_tools=["query_analytics"])
    result = score(case, Outcome(answer_text="x", tools_called=["search_reports", "query_analytics"]))
    assert result.tools_ok is False
    assert result.correct  # the answer itself was not wrong


def test_a_case_that_says_nothing_about_tools_or_citations_is_not_scored_on_them():
    result = score(_case(), Outcome(answer_text="x"))
    assert result.tools_ok is None and result.citations_ok is None


def test_citation_relevance_is_the_share_of_cited_reports_that_hold_the_answer():
    case = _case(category="document", cite=["School Bus"])
    citations = [
        {"title": "2025 MontCo School Bus Monitoring System Report", "source_type": "report"},
        {"title": "FY25 Vision Zero Annual Report", "source_type": "report"},
        {"title": "Crash Incidents Dataset", "source_type": "dataset"},  # not a report: ignored
    ]
    result = score(case, Outcome(citations=citations))
    assert result.citations_ok is True
    assert result.citation_relevance == 0.5


def test_citing_only_the_wrong_report_fails():
    case = _case(category="document", cite=["School Bus"])
    result = score(case, Outcome(citations=[{"title": "FY25 Vision Zero Annual Report", "source_type": "report"}]))
    assert result.citations_ok is False and result.citation_relevance == 0.0


def test_a_data_only_question_must_not_cite_a_report_but_may_cite_a_dataset():
    case = _case(cite="none")
    assert score(case, Outcome(citations=[{"title": "Crash data", "source_type": "dataset"}])).citations_ok
    assert not score(case, Outcome(citations=[{"title": "A report", "source_type": "report"}])).citations_ok


def test_caveat_and_limitation_requirements_are_enforced():
    assert not score(_case(caveat=True), Outcome(answer_text="6,364 crashes."), []).correct
    assert score(_case(caveat=True), Outcome(answer_text="6,364.", caveats=["2026 is a partial year."]), []).correct
    assert not score(_case(limitation=True), Outcome(answer_text="There were 212 such crashes.")).correct
    assert score(_case(limitation=True), Outcome(answer_text="The data does not include driver age.")).correct


def test_summary_counts_only_cases_that_were_scored_on_a_dimension():
    results = [
        score(_case(id="a", tools=["query_analytics"]), Outcome(answer_text="1", tools_called=["query_analytics"], seconds=2.0), [1]),
        score(_case(id="b"), Outcome(answer_text="nothing", seconds=4.0), [1]),
    ]
    all_row = [line for line in evaluation.summarize(results).splitlines() if line.startswith("ALL")][0].split()
    assert all_row[1:4] == ["2", "1/2", "1/1"]  # n, correct, tools (b made no tool claim)


def test_run_scores_every_case_through_an_injected_ask():
    cases = [_case(id="a", expect=[5]), _case(id="b", expect=[7])]
    results = evaluation.run(cases, workers=2, ask=lambda question: Outcome(answer_text="5"))
    assert [(r.id, r.correct) for r in results] == [("a", True), ("b", False)]


# --- the shipped question file ---

def test_question_file_is_well_formed_and_covers_every_category():
    cases = evaluation.load_cases()
    assert 40 <= len(cases) <= 60
    assert {c["category"] for c in cases} == set(evaluation.CATEGORIES)
    known_tools = {t.name for t in __import__("mocolens.agent.tools", fromlist=["ALL_TOOLS"]).ALL_TOOLS}
    for case in cases:
        for tool in case.get("tools") or []:
            assert set(tool if isinstance(tool, list) else [tool]) <= known_tools, case["id"]
        # Something must be checked, or the case can never fail.
        assert any(
            case.get(k) for k in ("sql", "sql_any", "expect", "tools", "decline", "limitation", "caveat")
        ), case["id"]


@pytest.mark.skipif(
    not Path("data/curated/vision_zero/analytics.duckdb").exists(),
    reason="curated tables not built - run scripts/build_curated_tables.py first",
)
def test_every_reference_query_runs_and_returns_a_value():
    # A typo in reference SQL would otherwise surface as a failed question
    # in the middle of a paid run.
    for case in evaluation.load_cases():
        for sql in ([case["sql"]] if case.get("sql") else []) + (case.get("sql_any") or []):
            assert evaluation.reference_values(sql), case["id"]


def test_sql_any_accepts_whichever_reading_the_answer_took(monkeypatch):
    monkeypatch.setattr(evaluation, "reference_values", lambda sql: [{"narrow": 1222, "broad": 1238}[sql]])
    case = _case(sql_any=["narrow", "broad"])
    assert evaluation.run_case(case, ask=lambda q: Outcome(answer_text="1,238 crashes")).correct
    assert not evaluation.run_case(case, ask=lambda q: Outcome(answer_text="900 crashes")).correct
