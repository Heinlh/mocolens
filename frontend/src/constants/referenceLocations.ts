/** Geographic labels drawn on the county map for orientation.
 *
 * Real place coordinates, not prototype data - they are here rather than in
 * data/mock/ because live screens draw them, and nothing on a live screen
 * should come from a file named mock. They carry no crash statistics: their
 * only job is to give a reader landmarks to locate a hotspot against.
 */
export interface ReferenceLocation {
  id: string
  name: string
  latitude: number
  longitude: number
}

export const COUNTY_REFERENCE_LOCATIONS: ReferenceLocation[] = [
  { id: 'clarksburg', name: 'Clarksburg', latitude: 39.2296, longitude: -77.2786 },
  { id: 'poolesville', name: 'Poolesville', latitude: 39.1454, longitude: -77.4166 },
  { id: 'olney', name: 'Olney', latitude: 39.1554, longitude: -77.0664 },
  { id: 'aspen-hill', name: 'Aspen Hill', latitude: 39.0762, longitude: -77.0741 },
  { id: 'north-bethesda', name: 'North Bethesda', latitude: 39.0398, longitude: -77.1147 },
  { id: 'takoma-park', name: 'Takoma Park', latitude: 38.9779, longitude: -77.0075 },
]
