/**
 * Resolves dashboard/analytics data. `getDashboardOverview` calls the real
 * backend (GET /api/dashboard/summary) using the dynamically configured API
 * origin, and
 * its response is already shaped exactly like DashboardResponse - the
 * backend's Pydantic schemas mirror these TS types field-for-field, so no
 * reshaping happens here. Filters are real query params the backend
 * actually applies in SQL, not a client-side illusion.
 *
 * Unconfigured local development can use mock data. Production configuration,
 * network, rate-limit, and server errors throw BackendError so the UI never
 * silently substitutes unrelated demo data.
 *
 * getHotspots() is still 100% mock - the hotspots page's backend endpoint
 * hasn't been built yet (see PROJECT_STATUS.txt).
 */
import { backendFetch, BackendConfigurationError, BackendError } from '@/lib/backendFetch'
import { mockDashboard, mockHotspotsResponse } from '@/data/mock/dashboard'
import type { DashboardFilters, DashboardResponse, HotspotsResponse } from '@/types/analytics'

export async function getDashboardOverview(filters?: DashboardFilters): Promise<DashboardResponse> {
  const params = filters
    ? '?' + new URLSearchParams({
        time_range: filters.timeRange,
        area: filters.area,
        road_user: filters.roadUser,
        severity: filters.severity,
      }).toString()
    : ''

  try {
    const res = await backendFetch(`/api/dashboard/summary${params}`)
    return (await res.json()) as DashboardResponse
  } catch (err) {
    if (import.meta.env.DEV && err instanceof BackendConfigurationError) return mockDashboard
    if (err instanceof BackendError) throw err
    throw new BackendError(0, 'The live data service could not be reached. Please try again shortly.')
  }
}

export async function getHotspots(): Promise<HotspotsResponse> {
  return mockHotspotsResponse
}
