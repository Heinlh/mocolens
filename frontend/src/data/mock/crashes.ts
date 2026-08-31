/**
 * Prototype-only mock data.
 * These values are used to develop the frontend and are not verified
 * Montgomery County crash statistics.
 */
import type { Hotspot, RankedArea } from '@/types/analytics'

/** The five ranked crash hotspots shared by the Dashboard map and the Hotspots page. */
export const mockHotspots: Hotspot[] = [
  { id: 'silver-spring', area: 'Silver Spring', latitude: 38.9907, longitude: -77.0261, crashCount: 1248, trend: 12, intensity: 1 },
  { id: 'bethesda', area: 'Bethesda', latitude: 38.9847, longitude: -77.0947, crashCount: 1012, trend: 8, intensity: 0.81 },
  { id: 'wheaton', area: 'Wheaton', latitude: 39.0399, longitude: -77.0553, crashCount: 742, trend: 5, intensity: 0.59 },
  { id: 'rockville', area: 'Rockville', latitude: 39.084, longitude: -77.1528, crashCount: 698, trend: -3, intensity: 0.56 },
  { id: 'gaithersburg', area: 'Gaithersburg', latitude: 39.1434, longitude: -77.2014, crashCount: 603, trend: -2, intensity: 0.48 },
]

/** Geographic reference labels shown on the county map for orientation - not ranked crash data. */
export interface ReferenceLocation {
  id: string
  name: string
  latitude: number
  longitude: number
}

export const mockReferenceLocations: ReferenceLocation[] = [
  { id: 'clarksburg', name: 'Clarksburg', latitude: 39.2296, longitude: -77.2786 },
  { id: 'poolesville', name: 'Poolesville', latitude: 39.1454, longitude: -77.4166 },
  { id: 'olney', name: 'Olney', latitude: 39.1554, longitude: -77.0664 },
  { id: 'aspen-hill', name: 'Aspen Hill', latitude: 39.0762, longitude: -77.0741 },
  { id: 'north-bethesda', name: 'North Bethesda', latitude: 39.0398, longitude: -77.1147 },
  { id: 'takoma-park', name: 'Takoma Park', latitude: 38.9779, longitude: -77.0075 },
]

export function toRankedAreas(hotspots: Hotspot[]): RankedArea[] {
  return [...hotspots]
    .sort((a, b) => b.crashCount - a.crashCount)
    .map((h, i) => ({ rank: i + 1, name: h.area, crashCount: h.crashCount, trend: h.trend }))
}
