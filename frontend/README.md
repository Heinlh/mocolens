# MoCoLens Frontend

## Current status

The current application is a frontend prototype. Data shown throughout the
application is mocked while the ingestion, analytics, and agentic retrieval
backend is under development. No page in this app calls the Python backend
or any LLM - every answer, chart, and metric comes from `src/data/mock/`.

## Running locally

```bash
npm install
npm run dev
```

Other scripts: `npm run build` (typecheck + production build), `npm run
lint` (oxlint), `npm run preview` (serve the production build locally).

## Architecture

```text
pages/ -> services/ -> mocked responses          (today)
pages/ -> services/ -> FastAPI backend           (later)
```

- **`types/`** - the data contracts (`Metric`, `QueryResponse`,
  `DashboardResponse`, `Hotspot`, `Citation`, ...). These are written as if
  a backend already returns them.
- **`data/mock/`** - centralized mock data implementing those types. Every
  file carries a comment that its values are prototype-only, not verified
  Montgomery County statistics.
- **`services/`** (`analyticsService`, `queryService`, `sourceService`) -
  the only place pages read data from. Each exported function is `async`
  and currently resolves a mock; swapping its body for a `fetch("/api/...")`
  call is the entire integration step once the backend exists. No page or
  component needs to change.
- **`components/`** - shared UI split by concern: `layout/` (shell, sidebar,
  page header), `common/` (cards, chips, badges), `chat/` (Ask flow),
  `charts/` (Recharts wrappers), `maps/` (SVG hotspot map, no GIS
  dependency), `sources/` (citation/source cards).
- **`pages/`** - one file per route, composed from the above. Routes are
  wired in `app/routes.tsx`.

## Notes on the map

The crash hotspot map is a stylized SVG illustration, not a real GIS layer.
`components/maps/mapProjection.ts` linearly projects real lat/long onto the
illustration's coordinate space, so real backend coordinates can be dropped
in later without changing the map components.
