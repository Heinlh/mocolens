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
from slowapi.util import get_ipaddr

from . import dashboard_service, query_service
from .dashboard_service import Filters
from .schemas import DashboardResponse, QueryResponse

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_ipaddr)

MAX_QUERY_CHARS = 400
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'-]*")
_DOMAIN_RE = re.compile(
    r"\b(crash(?:es)?|collision(?:s)?|pedestrian(?:s)?|cyclist(?:s)?|bicycl(?:e|es|ist|ists)|"
    r"driver(?:s)?|vehicle(?:s)?|road(?:s)?|street(?:s)?|avenue(?:s)?|highway(?:s)?|corridor(?:s)?|"
    r"intersection(?:s)?|traffic|transportation|transit|safety|fatal(?:ity|ities)?|injur(?:y|ies|ed)|"
    r"hotspot(?:s)?|speed(?:ing)?|vision zero|crosswalk(?:s)?|crossing(?:s)?|signal(?:s)?|"
    r"enforcement|county|montgomery|silver spring|bethesda|rockville|gaithersburg|wheaton|takoma)\b",
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
    if not _DOMAIN_RE.search(question):
        return "MoCoLens answers questions about Montgomery County roads, crashes, and traffic safety."
    return None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/dashboard/summary", response_model=DashboardResponse, response_model_by_alias=True)
@limiter.limit("60/minute")
def dashboard_summary(
    request: Request,
    time_range: str = "Last 12 months",
    area: str = "All areas",
    road_user: str = "All road users",
    severity: str = "All severity levels",
) -> DashboardResponse:
    try:
        return dashboard_service.get_dashboard_summary(
            Filters(time_range=time_range, area=area, road_user=road_user, severity=severity)
        )
    except FileNotFoundError as exc:
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
