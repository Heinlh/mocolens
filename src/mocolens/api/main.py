"""FastAPI app (architecture doc §21). Two real endpoints -
GET /api/dashboard/summary and POST /api/query - proving the vertical
slice end to end before/after the agent. More endpoints (§21's full list)
land as the pieces behind them are built.

Rate limits (slowapi, in-memory - no Redis needed at this scale, and the
whole app is one process): POST /api/query is capped tighter than the
dashboard endpoint on purpose - it's the one that calls a real, billed LLM
and runs for 10-40s, so it's both the most expensive to abuse and the
easiest to accidentally hammer by refreshing while "Thinking..." sits on
screen. GET /api/dashboard/summary just runs local DuckDB queries, so its
limit exists to stop scripted abuse, not to constrain a person clicking
through filters.
"""
import logging
import os
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import dashboard_service, query_service, sources_service
from .dashboard_service import Filters
from .schemas import DashboardResponse, MapResponse, QueryResponse, SourcesResponse, TrendsResponse

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    """The caller's IP, read through Render's proxy.

    Not slowapi's get_ipaddr: that one looks up a header named
    "X_FORWARDED_FOR" with underscores, which no proxy ever sends, so it
    silently falls through to the socket address. Behind Render that is the
    proxy's own IP - identical for every visitor - which collapsed all
    users into a single shared 10/minute + 40/hour bucket.

    A determined client can forge this header to get a fresh bucket. That
    is the same trade every X-Forwarded-For rate limiter makes, and it is
    strictly better than the alternative here: one shared bucket means the
    first ten questions of the hour lock everyone else out.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Left-most entry is the original client; the rest are proxy hops.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(key_func=_client_ip)

MAX_QUERY_CHARS = 400
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'-]*")
# Scope gate, inverted on purpose. The obvious design - "reject unless the
# question contains a traffic word" - cannot work: an allowlist has to
# anticipate every way a person phrases a traffic question, and it never
# does. The version that shipped rejected "Where should I avoid?", "What
# changed last year?", "Tell me about Georgia Ave" and "is moco safe to
# drive in?" - ordinary questions with no listed word in them - and each
# live failure only bought one more round of adding synonyms.
#
# So this asks the opposite question: is the text obviously about something
# else? That flips the failure direction to the cheap one. A miss costs one
# LLM call, already capped by the rate limits above, and the agent declines
# it properly (see agent/prompts.py, last rule). A false reject makes the
# app look broken to someone asking a perfectly reasonable question.
# Patterns are kept specific enough not to collide with traffic language -
# "python", not "code", since "traffic code" is a fair question.
_OFF_TOPIC_RE = re.compile(
    r"\b(?:recipe|recipes|cook|bake|baking|ingredient(?:s)?|"
    r"poem|poetry|haiku|sonnet|essay|screenplay|novel|lyrics|"
    r"joke(?:s)?|riddle(?:s)?|horoscope|"
    r"python|javascript|typescript|regex|html|css|leetcode|"
    r"homework|calculus|algebra|trigonometry|"
    r"weather|forecast|horoscope|"
    r"stock(?:s)?|crypto|bitcoin|ethereum|"
    r"translate|translation)\b|"
    r"\bwrite\s+(?:me\s+)?(?:a|some|an)\s+(?:code|program|script|story)\b",
    re.IGNORECASE,
)

_INJECTION_RE = re.compile(
    r"(ignore|disregard|forget).{0,30}(previous|prior|system|developer|instruction)|"
    r"(reveal|show|print|repeat).{0,30}(system prompt|developer message|hidden instruction)|"
    r"\b(jailbreak|prompt injection)\b",
    re.IGNORECASE,
)

app = FastAPI(title="MoCoLens API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Vite's dev server default, plus every mocolens*.vercel.app origin (covers
# both the production domain and Vercel's per-branch/per-PR preview URLs
# without needing a new env var for each one), plus whatever's set in
# FRONTEND_ORIGIN for anything else (a custom domain, say).
_default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_configured_origin = os.environ.get("FRONTEND_ORIGIN")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + ([_configured_origin] if _configured_origin else []),
    allow_origin_regex=r"https://mocolens.*\.vercel\.app",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


def _invalid_question_reason(question: str) -> str | None:
    """Reject obvious abuse before it can consume an LLM request."""
    if not question:
        return "Please enter a traffic-safety question."
    if len(question) > MAX_QUERY_CHARS:
        return f"Please keep the question under {MAX_QUERY_CHARS} characters."
    if "http://" in question.lower() or "https://" in question.lower():
        return "Please ask the question directly without links."
    if _INJECTION_RE.search(question):
        return "Please ask a Montgomery County traffic-safety question."
    if re.search(r"(.)\1{7,}", question, re.IGNORECASE):
        return "Please enter a clear traffic-safety question."

    words = [word.lower() for word in _WORD_RE.findall(question)]
    if len(words) < 2:
        return "Please enter a complete traffic-safety question."
    if len(words) >= 5 and len(set(words)) / len(words) < 0.4:
        return "Please avoid repeated or spam-like text."
    if _OFF_TOPIC_RE.search(question):
        return (
            "MoCoLens answers questions about Montgomery County roads, crashes, and traffic "
            "safety - try \"Which roads have the most pedestrian crashes?\""
        )
    return None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


def _dashboard(build, time_range: str, area: str, road_user: str, severity: str):
    """Run one dashboard query, turning a missing curated database into a 503.

    The three dashboard endpoints take the same filters and differ only in
    which slice of the curated tables they build, so the filter plumbing and
    the not-yet-built-here failure live in one place.
    """
    try:
        return build(Filters(time_range=time_range, area=area, road_user=road_user, severity=severity))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/dashboard/summary", response_model=DashboardResponse, response_model_by_alias=True)
@limiter.limit("60/minute")
def dashboard_summary(
    request: Request,
    time_range: str = "Last 12 months",
    area: str = "All areas",
    road_user: str = "All road users",
    severity: str = "All severity levels",
) -> DashboardResponse:
    return _dashboard(
        dashboard_service.get_dashboard_summary, time_range, area, road_user, severity
    )


@app.get("/api/dashboard/trends", response_model=TrendsResponse, response_model_by_alias=True)
@limiter.limit("60/minute")
def dashboard_trends(
    request: Request,
    time_range: str = "Last 12 months",
    area: str = "All areas",
    road_user: str = "All road users",
    severity: str = "All severity levels",
) -> TrendsResponse:
    return _dashboard(
        dashboard_service.get_dashboard_trends, time_range, area, road_user, severity
    )


@app.get("/api/dashboard/map", response_model=MapResponse, response_model_by_alias=True)
@limiter.limit("60/minute")
def dashboard_map(
    request: Request,
    time_range: str = "Last 12 months",
    area: str = "All areas",
    road_user: str = "All road users",
    severity: str = "All severity levels",
) -> MapResponse:
    return _dashboard(
        dashboard_service.get_dashboard_map, time_range, area, road_user, severity
    )


@app.get("/api/sources", response_model=SourcesResponse, response_model_by_alias=True)
@limiter.limit("60/minute")
def sources(request: Request) -> SourcesResponse:
    """Provenance for the Sources & Methodology screen. Local files only, so
    it shares the dashboard's looser limit rather than the query limit.
    """
    try:
        return sources_service.get_sources()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/query", response_model=QueryResponse, response_model_by_alias=True)
@limiter.limit("40/hour")
@limiter.limit("10/minute")
def query(request: Request, body: QueryRequest) -> QueryResponse:
    question = body.question.strip()
    invalid_reason = _invalid_question_reason(question)
    if invalid_reason:
        raise HTTPException(status_code=400, detail=invalid_reason)

    try:
        return query_service.ask(question)
    except RuntimeError as exc:
        # e.g. missing Azure OpenAI credentials - a deployment/config
        # problem, not something the client did wrong.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # Never leak internals (stack traces, tool SQL, credentials) to the
        # client for an unexpected failure - log it server-side, return a
        # generic message.
        logger.exception("Agent run failed for question: %s", question)
        raise HTTPException(status_code=500, detail="The agent failed to answer this question.") from exc
