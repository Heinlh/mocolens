# MoCoLens

Public-facing agentic analytics for Montgomery County traffic safety. See
[MoCoLens_MVP_ARCHITECTURE.md](MoCoLens_MVP_ARCHITECTURE.md) for the full
system design.

## Current status

The **backend** (`src/mocolens/`) has a working extract layer: it pulls live
crash data from Montgomery County's Socrata API and downloads Vision Zero
report PDFs into a raw data lake (`data/raw/`), plus a processing layer that
parses those PDFs (Docling), chunks and embeds them (IBM Granite embeddings),
and indexes them in a local Chroma vector store. The agent, retrieval tools,
and FastAPI layer described in the architecture doc are not built yet.

The **frontend** (`frontend/`) is a standalone prototype UI built against
**mocked data only** - it does not call the Python backend. Every number,
chart, and answer shown in the app is fabricated for the prototype and is
**not verified Montgomery County data** (see `frontend/src/data/mock/`).

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

## Running the backend (extract + processing layers)

```bash
python -m pip install -e ".[dev]"
python scripts/ingest.py --domain vision_zero          # API + document extract
python scripts/rebuild_vector_index.py --domain vision_zero  # parse, chunk, embed, index
pytest
```

## Repository layout

```text
config/sources.yaml   # source registry (API + document sources per domain)
src/mocolens/          # Python backend: ingestion, processing, storage
scripts/               # backend CLI entry points
data/, logs/           # backend data lake + run logs (gitignored)
frontend/              # React/TypeScript prototype UI (mocked data)
```

## Frontend architecture

```text
pages/ -> services/ -> data/mock/*   (today)
pages/ -> services/ -> fetch("/api/...")   (once the backend API exists)
```

Pages never read mock data directly - they call a typed service function
(`analyticsService`, `queryService`, `sourceService`). Swapping a service's
body for a `fetch` call is the only change needed to connect a page to the
real backend; no page or component changes.

See [frontend/README.md](frontend/README.md) for frontend-specific detail.
