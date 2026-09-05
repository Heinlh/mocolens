/**
 * Prototype-only mock data.
 * These values are used to develop the frontend and are not verified
 * Montgomery County crash statistics.
 */
import type { Hotspot } from '@/types/analytics'

/** Stand-in hotspots for mockDashboard, the Dashboard's local-dev fallback.
 * The Hotspots page has no mock fallback - it calls GET /api/dashboard/map. */
export const mockHotspots: Hotspot[] = [
  { id: 'silver-spring', area: 'Silver Spring', latitude: 38.9907, longitude: -77.0261, crashCount: 1248, trend: 12, intensity: 1 },
  { id: 'bethesda', area: 'Bethesda', latitude: 38.9847, longitude: -77.0947, crashCount: 1012, trend: 8, intensity: 0.81 },
  { id: 'wheaton', area: 'Wheaton', latitude: 39.0399, longitude: -77.0553, crashCount: 742, trend: 5, intensity: 0.59 },
  { id: 'rockville', area: 'Rockville', latitude: 39.084, longitude: -77.1528, crashCount: 698, trend: -3, intensity: 0.56 },
  { id: 'gaithersburg', area: 'Gaithersburg', latitude: 39.1434, longitude: -77.2014, crashCount: 603, trend: -2, intensity: 0.48 },
]
