/**
 * Resolves dashboard/analytics data. `getDashboardOverview` calls the real
 * backend (GET /api/dashboard/summary) when VITE_API_BASE_URL is set, and
 * its response is already shaped exactly like DashboardResponse - the
 * backend's Pydantic schemas mirror these TS types field-for-field, so no
 * reshaping happens here. Falls back to mock data if the backend is
 * unreachable or unconfigured, so the frontend still runs standalone.
 *
 * getHotspots() is still 100% mock - the hotspots page's backend endpoint
 * hasn't been built yet (see PROJECT_STATUS.txt).
 */
import { mockDashboard, mockHotspotsResponse } from '@/data/mock/dashboard'
import type { DashboardResponse, HotspotsResponse } from '@/types/analytics'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined

export async function getDashboardOverview(): Promise<DashboardResponse> {
  if (!API_BASE_URL) return mockDashboard

  try {
    const res = await fetch(`${API_BASE_URL}/api/dashboard/summary`)
    if (!res.ok) throw new Error(`dashboard summary request failed: ${res.status}`)
    return (await res.json()) as DashboardResponse
  } catch (err) {
    console.error('Falling back to mock dashboard data:', err)
    return mockDashboard
  }
}

export async function getHotspots(): Promise<HotspotsResponse> {
  return mockHotspotsResponse
}
