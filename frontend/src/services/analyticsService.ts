/**
 * Resolves dashboard/analytics data. `getDashboardOverview` calls the real
 * backend (GET /api/dashboard/summary) when VITE_API_BASE_URL is set, and
 * its response is already shaped exactly like DashboardResponse - the
 * backend's Pydantic schemas mirror these TS types field-for-field, so no
 * reshaping happens here. Filters are real query params the backend
 * actually applies in SQL, not a client-side illusion.
 *
 * Falls back to mock data only when the backend is unreachable/unconfigured
 * (the standalone-demo case). A reachable backend that rejects the request
 * (rate limited, real error) throws BackendError instead - the caller
 * should show that to the user, not silently substitute fake data for it.
 *
 * getHotspots() is still 100% mock - the hotspots page's backend endpoint
 * hasn't been built yet (see PROJECT_STATUS.txt).
 */
import { backendFetch, isBackendConfigured, BackendError } from '@/lib/backendFetch'
import { mockDashboard, mockHotspotsResponse } from '@/data/mock/dashboard'
import type { DashboardFilters, DashboardResponse, HotspotsResponse } from '@/types/analytics'

export async function getDashboardOverview(filters?: DashboardFilters): Promise<DashboardResponse> {
  if (!isBackendConfigured()) return mockDashboard

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
    if (err instanceof BackendError) throw err
    console.error('Backend unreachable, falling back to mock dashboard data:', err)
    return mockDashboard
  }
}

export async function getHotspots(): Promise<HotspotsResponse> {
  return mockHotspotsResponse
}
