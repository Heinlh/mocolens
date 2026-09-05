/**
 * Regression tests for the page services that talk to the real backend.
 *
 * The point of these is the rule the project cares about most: a page backed
 * by county data must never silently substitute prototype data for a
 * backend that is unreachable, rate-limited, or failing. Each service is
 * driven against a stubbed fetch so the whole request/parse/error path runs
 * without a live API.
 */
import assert from 'node:assert/strict'
import { createServer } from 'vite'

process.env.VITE_API_BASE_URL = 'https://api.test.invalid'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

const realFetch = globalThis.fetch

/** Runs `body` with fetch stubbed, returning the paths that were requested. */
async function withFetch(handler, body) {
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push(String(url))
    return handler(String(url), init)
  }
  try {
    await body(calls)
  } finally {
    globalThis.fetch = realFetch
  }
}

const jsonResponse = (payload, status = 200) =>
  new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } })

try {
  const { getSources } = await server.ssrLoadModule('/src/services/sourceService.ts')
  const { BackendError } = await server.ssrLoadModule('/src/lib/backendFetch.ts')

  const sourcesPayload = {
    sources: [{
      id: 'crash_incidents',
      title: 'Crash Incidents Dataset',
      description: 'Police-reported crashes.',
      sourceType: 'dataset',
      refreshCadence: 'weekly',
      lastUpdated: '2026-08-30',
      url: 'https://data.montgomerycountymd.gov/resource/bhju-22kf.json',
    }],
    citations: [{ id: 'c55a715ce88d', title: 'FY25 Vision Zero Annual Report', sourceType: 'report', page: '1-80', publishedAt: '2025' }],
    indexedChunkCount: 319,
  }

  // --- sources: the happy path returns exactly what the backend sent ---
  await withFetch(() => jsonResponse(sourcesPayload), async (calls) => {
    const result = await getSources()
    assert.equal(calls.length, 1)
    assert.match(calls[0], /\/api\/sources$/)
    assert.deepEqual(result, sourcesPayload)
  })

  // --- sources: failures surface as failures, never as prototype data ---
  await withFetch(() => jsonResponse({ detail: 'Rate limit exceeded' }, 429), async () => {
    const err = await getSources().then(() => null, (e) => e)
    assert.ok(err instanceof BackendError, 'a rate limit must reject, not resolve')
    assert.equal(err.status, 429)
    assert.equal(err.message, 'Rate limit exceeded')
  })

  await withFetch(() => { throw new TypeError('network down') }, async () => {
    const err = await getSources().then(() => null, (e) => e)
    assert.ok(err instanceof BackendError, 'an unreachable backend must reject, not resolve')
    assert.equal(err.status, 0)
  })

  await withFetch(() => jsonResponse({ detail: 'index missing' }, 503), async () => {
    const err = await getSources().then(() => null, (e) => e)
    assert.equal(err.status, 503)
  })

  // --- hotspots: calls the real map endpoint, and never falls back ---
  const { getHotspots } = await server.ssrLoadModule('/src/services/analyticsService.ts')

  const mapPayload = {
    hotspots: [{ id: '3899_-7702', area: 'Georgia Ave near Colesville Rd', latitude: 38.99, longitude: -77.02, crashCount: 146, trend: 15.9, intensity: 1 }],
    rankedAreas: [{ rank: 1, name: 'Georgia Ave near Colesville Rd', crashCount: 146, trend: 15.9 }],
    summaryCards: [{ label: 'Most affected location', primaryText: 'Georgia Ave near Colesville Rd', secondaryText: '146 crashes' }],
    countyFocus: [{ title: 'TOP PRIORITIES', excerpt: 'Refine the High Injury Network', documentTitle: 'VZ Assessment', page: '5-6', url: 'https://example.gov/vz.pdf' }],
    dataAsOf: '2026-08-31T22:57:43+00:00',
  }

  await withFetch(() => jsonResponse(mapPayload), async (calls) => {
    const result = await getHotspots()
    assert.match(calls[0], /\/api\/dashboard\/map$/)
    assert.deepEqual(result, mapPayload)
  })

  await withFetch(() => jsonResponse(mapPayload), async (calls) => {
    await getHotspots({ timeRange: 'Last 6 months', area: 'All areas', roadUser: 'Cyclists', severity: 'Fatal' })
    assert.match(calls[0], /time_range=Last\+6\+months/)
    assert.match(calls[0], /road_user=Cyclists/)
    assert.match(calls[0], /severity=Fatal/)
  })

  // The Hotspots page is entirely about real geography, so there is no mock
  // fallback even in dev - an unreachable backend must reject.
  await withFetch(() => { throw new TypeError('network down') }, async () => {
    const err = await getHotspots().then(() => null, (e) => e)
    assert.ok(err instanceof BackendError, 'hotspots must never resolve to prototype coordinates')
    assert.equal(err.status, 0)
  })

  await withFetch(() => jsonResponse({ detail: 'curated db missing' }, 503), async () => {
    const err = await getHotspots().then(() => null, (e) => e)
    assert.equal(err.status, 503)
    assert.equal(err.message, 'curated db missing')
  })

  console.log('Page service regression tests passed.')
} finally {
  await server.close()
}
