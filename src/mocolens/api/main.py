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
import json
import logging
import os
import re
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from ..processing import curate
from ..retrieval import sql_tool
from . import dashboard_service, query_service, sources_service
from .dashboard_service import Filters
from .schemas import DashboardResponse, MapResponse, QueryResponse, SourcesResponse, TrendsResponse

# Uvicorn configures only its own loggers, so without this every
# logger.info() in the app - the request log below included - is dropped.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# How many proxies in front of this app append to X-Forwarded-For. 0 keeps
# the left-most entry, which is right only if the edge discards whatever the
# client sent. Render's edge is reported to append instead, which makes the
# left-most entry client-controlled - so set this to the number of trusted
# hops once it is known. The request log prints `xff_hops` for an ordinary
# request; that number is the value to use.
TRUSTED_PROXY_HOPS = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))

# Ceilings on the one endpoint that spends money, neither of which depends on
# knowing who the caller is. The per-IP limits below are only as good as the
# IP, and a forged X-Forwarded-For buys a fresh bucket per request.
# ponytail: the budget is counted in this process's memory, so a restart
# resets it. It bounds sustained abuse, which keeps the instance awake; the
# hard backstop is the tokens-per-minute quota on the Azure deployment.
DAILY_QUERY_BUDGET = int(os.environ.get("DAILY_QUERY_BUDGET", "200"))
# An agent run holds a worker thread for 6-40s. Uncapped, forty of them fill
# Starlette's whole thread pool and the dashboard stops answering too. Two,
# because three in flight was enough to hit the Azure deployment's token rate
# limit during an evaluation run; raise it together with that quota.
MAX_CONCURRENT_QUERIES = int(os.environ.get("MAX_CONCURRENT_QUERIES", "2"))
_BUSY_MESSAGE = "MoCoLens is answering as many questions as it can right now. Please try again in a moment."
_query_slots = threading.BoundedSemaphore(MAX_CONCURRENT_QUERIES)


def _forwarded_chain(request: Request) -> list[str]:
    return [hop.strip() for hop in request.headers.get("X-Forwarded-For", "").split(",") if hop.strip()]


def _client_ip(request: Request) -> str:
    """The caller's IP, read through Render's proxy.

    Not slowapi's get_ipaddr: that one looks up a header named
    "X_FORWARDED_FOR" with underscores, which no proxy ever sends, so it
    silently falls through to the socket address. Behind Render that is the
    proxy's own IP - identical for every visitor - which collapsed all
    users into a single shared 10/minute + 40/hour bucket.

    Each trusted proxy appends the address it received the request from, so
    with N trusted hops the real client is the Nth entry from the right and
    everything left of it is whatever the client chose to send. With
    TRUSTED_PROXY_HOPS unset this falls back to the left-most entry: still
    forgeable, but per-visitor, and one shared bucket is worse. The global
    budget on /api/query is what holds if this is forged.
    """
    chain = _forwarded_chain(request)
    if chain:
        if 0 < TRUSTED_PROXY_HOPS <= len(chain):
            return chain[-TRUSTED_PROXY_HOPS]
        return chain[0]
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
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def trace_request(request: Request, call_next):
    """One JSON log line per request, and an id that ties it together.

    The id is returned as X-Request-ID and carried into the SQL audit log, so
    a slow or failed question can be followed from the HTTP request to the
    queries it ran. duration_ms on every line is also the latency record:
    percentiles come from these lines (scripts/loadtest.py prints them for a
    run), not from a metrics service this deployment does not have.

    Registered last so it is the outermost layer and sees rate-limit and
    CORS responses too.
    """
    request_id = uuid.uuid4().hex[:12]
    sql_tool.request_id.set(request_id)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.info("request %s", json.dumps({
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            # A count, not the addresses: enough to set TRUSTED_PROXY_HOPS
            # without writing visitors' IPs into the log.
            "xff_hops": len(_forwarded_chain(request)),
        }))


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
    """Liveness plus what data this instance is serving.

    build_info.json is written by curation and published only when a refresh
    passes its checks, so `lastRefresh` is the last *successful* refresh - a
    monitor can alarm on it going stale without credentials for anything.
    """
    info = curate.build_info(dashboard_service.DOMAIN) or {}
    return {
        "status": "ok",
        "lastRefresh": info.get("built_at"),
        "snapshotDate": info.get("snapshot_date"),
        "dataThrough": info.get("coverage_end"),
    }


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
@limiter.limit(f"{DAILY_QUERY_BUDGET}/day", key_func=lambda request: "everyone")
@limiter.limit("40/hour")
@limiter.limit("10/minute")
def query(request: Request, body: QueryRequest) -> QueryResponse:
    question = body.question.strip()
    invalid_reason = _invalid_question_reason(question)
    if invalid_reason:
        raise HTTPException(status_code=400, detail=invalid_reason)

    # Refuse rather than queue: a queued question would sit on "Thinking..."
    # behind others for minutes, and the client gives up at 120s anyway.
    if not _query_slots.acquire(blocking=False):
        raise HTTPException(status_code=503, detail=_BUSY_MESSAGE, headers={"Retry-After": "15"})
    try:
        return query_service.ask(question)
    except RuntimeError as exc:
        # e.g. missing Azure OpenAI credentials - a deployment/config
        # problem, not something the client did wrong.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # The model provider throttling us is "busy", not "broken": the same
        # question will work in a moment, and the client should be told so.
        if getattr(exc, "status_code", None) == 429:
            logger.warning("Model provider rate limit hit for question: %s", question)
            raise HTTPException(status_code=503, detail=_BUSY_MESSAGE, headers={"Retry-After": "30"}) from exc
        # Never leak internals (stack traces, tool SQL, credentials) to the
        # client for an unexpected failure - log it server-side, return a
        # generic message.
        logger.exception("Agent run failed for question: %s", question)
        raise HTTPException(status_code=500, detail="The agent failed to answer this question.") from exc
    finally:
        _query_slots.release()
