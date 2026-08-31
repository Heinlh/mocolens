/**
 * Projects real-world lat/long onto the 0-100 coordinate space used by the
 * stylized county map illustration. This is a linear fit over Montgomery
 * County's approximate bounding box, not a real GIS projection - it exists
 * so the map keeps working if a backend later supplies true coordinates.
 */
const COUNTY_BOUNDS = {
  minLat: 38.93,
  maxLat: 39.35,
  minLong: -77.52,
  maxLong: -76.9,
}

export interface MapPoint {
  x: number
  y: number
}

export function projectToMapPoint(latitude: number, longitude: number): MapPoint {
  const x = ((longitude - COUNTY_BOUNDS.minLong) / (COUNTY_BOUNDS.maxLong - COUNTY_BOUNDS.minLong)) * 100
  const y = ((COUNTY_BOUNDS.maxLat - latitude) / (COUNTY_BOUNDS.maxLat - COUNTY_BOUNDS.minLat)) * 100
  return { x: clamp(x), y: clamp(y) }
}

function clamp(value: number): number {
  return Math.min(96, Math.max(4, value))
}
