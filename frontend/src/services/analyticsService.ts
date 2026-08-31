/**
 * Resolves dashboard/analytics data. Every export here is async on purpose:
 * callers already treat it as a network call, so swapping the mock
 * resolution below for `fetch("/api/dashboard/...")` won't touch any page.
 */
import { mockDashboard, mockHotspotsResponse } from '@/data/mock/dashboard'
import type { DashboardResponse, HotspotsResponse } from '@/types/analytics'

export async function getDashboardOverview(): Promise<DashboardResponse> {
  return mockDashboard
}

export async function getHotspots(): Promise<HotspotsResponse> {
  return mockHotspotsResponse
}
