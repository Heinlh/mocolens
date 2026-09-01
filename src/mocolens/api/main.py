"""FastAPI app (architecture doc §21). Two real endpoints -
GET /api/dashboard/summary and POST /api/query - proving the vertical
slice end to end before/after the agent. More endpoints (§21's full list)
land as the pieces behind them are built.
"""
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import dashboard_service, query_service
from .schemas import DashboardResponse, QueryResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="MoCoLens API")

# Vite's dev server default, plus whatever the deployed frontend origin is
# (set FRONTEND_ORIGIN when that's known - see PROJECT_STATUS.txt's
# deployment notes).
_default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_configured_origin = os.environ.get("FRONTEND_ORIGIN")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + ([_configured_origin] if _configured_origin else []),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/dashboard/summary", response_model=DashboardResponse, response_model_by_alias=True)
def dashboard_summary() -> DashboardResponse:
    try:
        return dashboard_service.get_dashboard_summary()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/query", response_model=QueryResponse, response_model_by_alias=True)
def query(request: QueryRequest) -> QueryResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

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
