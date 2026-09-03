# MoCoLens Frontend

## Current status

The Dashboard Overview screen and the Ask flow call the real Python backend
(FastAPI + a LangGraph agent) when `VITE_API_BASE_URL` is set and the
backend is reachable, and fall back to mock data automatically otherwise -
so this app runs standalone with nothing else running. The Hotspots and
Sources pages are still mock-only (their backend endpoints aren't built yet).

## Running locally

```bash
npm install
npm run dev
```

Copy `.env.example` to `.env` and set `VITE_API_BASE_URL` to the origin of
the backend you want to use. The fetch helper reads this value dynamically;
no local or deployed server URL is hardcoded in the application source. See
the repo root README for how to run the backend.

Other scripts: `npm run build` (typecheck + production build), `npm run
lint` (oxlint), `npm run preview` (serve the production build locally).

## Architecture

```text
pages/ -> services/ -> mocked responses           (always available)
pages/ -> services/ -> fetch(VITE_API_BASE_URL)   (when configured and reachable)
```

- **`types/`** - the data contracts (`Metric`, `QueryResponse`,
  `DashboardResponse`, `Hotspot`, `Citation`, ...). The backend's Pydantic
  response models mirror these field-for-field (camelCase via an alias
  generator), so a real API response needs zero reshaping on this side.
- **`data/mock/`** - centralized mock data implementing those types. Every
  file carries a comment that its values are prototype-only, not verified
  Montgomery County statistics.
- **`services/`** (`analyticsService`, `queryService`, `sourceService`) -
  the only place pages read data from. `analyticsService.getDashboardOverview()`
  and `queryService.ask()` call the real backend when `VITE_API_BASE_URL`
  is set, catching any failure and falling back to mock data. The others
  still resolve mock data directly. No page or component reads mock data
  or calls `fetch` on its own.
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

## Deployment

Deploys to Vercel with root directory set to `frontend/`; `vercel.json`
handles SPA routing (all paths rewrite to `index.html`). Set
`VITE_API_BASE_URL` in the Vercel project's environment variables to point
at a deployed backend - omit it (or leave the backend unreachable) and the
site runs entirely on mock data, which is a safe default, not a broken state.
