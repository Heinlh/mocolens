"""Agent evaluation harness: run a fixed question set through the same path
production uses (the API's scope gate, then the LangGraph agent) and record,
per question, whether the answer was correct, whether the right tools were
used, whether the citations point at the right documents, how long it took,
and what failed.

Every check is deterministic - no LLM grades another LLM's answer. That
keeps a run cheap and makes a changed score mean the agent changed, not the
judge. The cost is strictness: an answer that says "about 450" where the data
says 447 is marked wrong. For a tool whose whole claim is that its numbers
are the data's numbers, that is the right way to be wrong.

Expected numbers are not written into the question file. A structured
question carries reference SQL instead, run against the curated tables when
the evaluation runs - the county adds crashes every week, and a pinned count
would start failing the first refresh after it was written.

The question file (evals/questions.yaml) documents the fields a case takes.
"""
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb
import yaml
from langchain_core.messages import AIMessage, ToolMessage

QUESTIONS_PATH = Path("evals/questions.yaml")
RESULTS_DIR = Path("logs/evals")
DATA_DIR = Path("data")
DOMAIN = "vision_zero"
CATEGORIES = ("structured", "document", "hybrid", "ambiguous", "unsupported")

# How an answer admits the data cannot support the question. Matched as
# substrings of the lowercased answer, so each must be specific enough not to
# appear in an ordinary answer.
_LIMITATION_PHRASES = (
    "not available", "isn't available", "unavailable", "not include", "n't include",
    "not contain", "n't contain", "not record", "n't record", "not track", "n't track",
    "not have", "n't have", "cannot", "can't", "unable", "no data", "no information",
    "not possible", "lacks", "does not cover", "only covers", "no way to",
)

_NUMBER_RE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")


@dataclass
class Outcome:
    """What one question produced, before any scoring."""
    answer_text: str = ""
    caveats: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    tool_errors: int = 0
    gate_rejected: bool = False
    error: str | None = None
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Result:
    id: str
    category: str
    question: str
    correct: bool
    tools_ok: bool | None  # None = this case makes no claim about tools
    citations_ok: bool | None
    citation_relevance: float | None
    problems: list[str]
    outcome: Outcome


def load_cases(path: Path = QUESTIONS_PATH) -> list[dict]:
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))
    seen = set()
    for case in cases:
        if case["category"] not in CATEGORIES:
            raise ValueError(f"{case['id']}: unknown category {case['category']!r}")
        if case["id"] in seen:
            raise ValueError(f"duplicate case id {case['id']!r}")
        seen.add(case["id"])
    return cases


# --- matching ---

def numbers_in(text: str) -> list[float]:
    return [float(match.replace(",", "")) for match in _NUMBER_RE.findall(text)]


def contains(text: str, expected) -> bool:
    """Whether `text` states one expected fact.

    A list is alternatives (any one will do). A whole number must appear
    exactly; a fraction within half a unit, since answers round "4.34%" to
    "4.3%" or "4%". A string is a case-insensitive substring.
    """
    if isinstance(expected, list):
        return any(contains(text, alternative) for alternative in expected)
    if isinstance(expected, bool):
        raise TypeError("a boolean is not a fact an answer can state")
    if isinstance(expected, (int, float)):
        tolerance = 0 if float(expected).is_integer() else 0.51
        return any(abs(number - expected) <= tolerance for number in numbers_in(text))
    return str(expected).lower() in text.lower()


def reference_values(sql: str, domain: str = DOMAIN) -> list:
    """The first row of a case's reference query, against the curated tables."""
    con = duckdb.connect(str(DATA_DIR / "curated" / domain / "analytics.duckdb"), read_only=True)
    try:
        row = con.execute(sql).fetchone()
    finally:
        con.close()
    if row is None:
        raise ValueError(f"reference query returned no rows: {sql}")
    return [float(v) if isinstance(v, Decimal) else v for v in row if v is not None]


# --- scoring ---

def _tools_ok(case: dict, called: set[str]) -> tuple[bool | None, list[str]]:
    required, forbidden = case.get("tools"), case.get("no_tools")
    if required is None and forbidden is None:
        return None, []
    problems = []
    for tool in required or []:
        alternatives = tool if isinstance(tool, list) else [tool]
        if not called & set(alternatives):
            problems.append(f"did not call {' or '.join(alternatives)}")
    banned = called if forbidden == "all" else called & set(forbidden or [])
    if banned:
        problems.append(f"called {', '.join(sorted(banned))} when it should not have")
    return not problems, problems


def _citations_ok(case: dict, citations: list[dict]) -> tuple[bool | None, float | None, list[str]]:
    """`cite` is "none" (no report may be cited), "any" (at least one report),
    or a list of title fragments naming the documents that actually hold the
    answer. Relevance is the share of cited reports that are among them.
    """
    expected = case.get("cite")
    if expected is None:
        return None, None, []
    reports = [c for c in citations if c.get("source_type") == "report"]
    if expected == "none":
        return (not reports), None, (["cited a report for a question no report answers"] if reports else [])
    if not reports:
        return False, 0.0, ["cited no report"]
    if expected == "any":
        return True, 1.0, []
    relevant = [c for c in reports if contains(c.get("title") or "", list(expected))]
    relevance = len(relevant) / len(reports)
    return bool(relevant), relevance, ([] if relevant else [f"cited none of: {', '.join(expected)}"])


def score(case: dict, outcome: Outcome, expected_facts: list | None = None) -> Result:
    """Grade one outcome. `expected_facts` is the case's `expect` list plus
    whatever its reference SQL returned.
    """
    problems: list[str] = []
    called = set(outcome.tools_called)
    tools_ok, tool_problems = _tools_ok(case, called)
    citations_ok, relevance, citation_problems = _citations_ok(case, outcome.citations)

    if outcome.error:
        correct = False
        problems.append(f"error: {outcome.error}")
    elif case.get("decline"):
        # Out of scope: stopped at the gate, or declined without spending a
        # tool call or inventing a source.
        correct = outcome.gate_rejected or (not called and not outcome.citations)
        if not correct:
            problems.append("answered a question it should have declined")
    elif outcome.gate_rejected:
        correct = False
        problems.append(f"rejected by the scope gate: {outcome.answer_text}")
    else:
        missing = [fact for fact in expected_facts or [] if not contains(outcome.answer_text, fact)]
        problems += [f"answer does not state {fact!r}" for fact in missing]
        if case.get("caveat") and not outcome.caveats:
            problems.append("no caveat given")
        if case.get("limitation") and not contains(outcome.answer_text, list(_LIMITATION_PHRASES)):
            problems.append("did not say the data cannot answer this")
        correct = not problems

    return Result(
        id=case["id"], category=case["category"], question=case["question"],
        correct=correct, tools_ok=tools_ok, citations_ok=citations_ok,
        citation_relevance=relevance,
        problems=problems + tool_problems + citation_problems, outcome=outcome,
    )


# --- running ---

def _outcome_from_state(state: dict) -> Outcome:
    answer = state["final"]
    outcome = Outcome(
        # Every narrative field: a correct number in the summary counts even
        # if the one-line headline rounds it away.
        answer_text="\n".join([
            answer.answer, answer.summary, answer.what_data_means,
            *answer.county_report_points, *answer.caveats,
        ]),
        caveats=list(answer.caveats),
        citations=[c.model_dump() for c in answer.citations],
    )
    for message in state["messages"]:
        if isinstance(message, AIMessage):
            outcome.tools_called += [call["name"] for call in message.tool_calls]
        elif isinstance(message, ToolMessage):
            try:
                payload = json.loads(message.content) if isinstance(message.content, str) else message.content
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("error"):
                outcome.tool_errors += 1
    return outcome


def ask_agent(question: str) -> Outcome:
    """One question through the production path: scope gate, then the agent."""
    from langchain_core.callbacks import get_usage_metadata_callback

    from .agent import graph
    from .api.main import _invalid_question_reason

    started = time.perf_counter()
    rejection = _invalid_question_reason(question.strip())
    if rejection:
        return Outcome(answer_text=rejection, gate_rejected=True, seconds=time.perf_counter() - started)
    try:
        with get_usage_metadata_callback() as usage:
            outcome = _outcome_from_state(graph.run(question))
        outcome.input_tokens = sum(u.get("input_tokens", 0) for u in usage.usage_metadata.values())
        outcome.output_tokens = sum(u.get("output_tokens", 0) for u in usage.usage_metadata.values())
    except Exception as exc:  # noqa: BLE001 - any failure is this question's result, not the run's
        outcome = Outcome(error=f"{type(exc).__name__}: {exc}")
    outcome.seconds = time.perf_counter() - started
    return outcome


def run_case(case: dict, ask=ask_agent) -> Result:
    facts = list(case.get("expect") or [])
    if case.get("sql"):
        facts += reference_values(case["sql"])
    if case.get("sql_any"):
        # Several defensible readings of one question: the first value of
        # each query, any one of which is a right answer.
        facts.append([reference_values(sql)[0] for sql in case["sql_any"]])
    return score(case, ask(case["question"]), facts)


def run(cases: list[dict], workers: int = 3, ask=ask_agent) -> list[Result]:
    if ask is ask_agent:
        # Paid for here, once, so the first question's time is the agent's
        # and not several seconds of importing LangGraph.
        from .agent import graph  # noqa: F401
        from .api import main  # noqa: F401
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda case: run_case(case, ask), cases))


# --- reporting ---

def _rate(values: list[bool | None]) -> str:
    scored = [v for v in values if v is not None]
    return f"{sum(scored)}/{len(scored)}" if scored else "-"


def _percentile(values: list[float], q: int) -> float:
    if len(values) < 2:
        return values[0] if values else 0.0
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def summarize(results: list[Result]) -> str:
    lines = [f"{'category':<12} {'n':>3} {'correct':>8} {'tools':>7} {'cites':>7} {'errors':>6} {'p50 s':>6} {'p95 s':>6}"]
    groups = [(c, [r for r in results if r.category == c]) for c in CATEGORIES] + [("ALL", results)]
    for name, group in groups:
        if not group:
            continue
        seconds = [r.outcome.seconds for r in group]
        lines.append(
            f"{name:<12} {len(group):>3} {_rate([r.correct for r in group]):>8} "
            f"{_rate([r.tools_ok for r in group]):>7} {_rate([r.citations_ok for r in group]):>7} "
            f"{sum(1 for r in group if r.outcome.error):>6} "
            f"{_percentile(seconds, 50):>6.1f} {_percentile(seconds, 95):>6.1f}"
        )
    answered = [r for r in results if r.outcome.input_tokens]
    if answered:
        lines.append(
            f"\ntokens per answered question: "
            f"{statistics.mean(r.outcome.input_tokens for r in answered):,.0f} in, "
            f"{statistics.mean(r.outcome.output_tokens for r in answered):,.0f} out "
            f"({sum(r.outcome.input_tokens for r in answered):,} in / "
            f"{sum(r.outcome.output_tokens for r in answered):,} out for the run)"
        )
    relevance = [r.citation_relevance for r in results if r.citation_relevance is not None]
    if relevance:
        lines.append(f"citation relevance (share of cited reports that hold the answer): {statistics.mean(relevance):.0%}")
    failed = [r for r in results if r.problems]
    if failed:
        lines.append(f"\n{len(failed)} case(s) with problems:")
        lines += [f"  {r.id}: {'; '.join(r.problems)}" for r in failed]
    return "\n".join(lines)


def save(results: list[Result], directory: Path = RESULTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ran_at = datetime.now(timezone.utc)
    path = directory / f"{ran_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps({
        "ran_at": ran_at.isoformat(),
        "results": [asdict(r) for r in results],
    }, indent=2), encoding="utf-8")
    return path
