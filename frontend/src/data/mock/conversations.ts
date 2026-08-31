/**
 * Prototype-only mock data.
 * These values are used to develop the frontend and are not verified
 * Montgomery County crash statistics.
 */
import type { Hotspot } from '@/types/analytics'
import type { ConversationEntry, QueryResponse } from '@/types/query'

/** Sidebar "Recent questions" list. askedAt is a display-ready relative label for this prototype. */
export const mockRecentQuestions: ConversationEntry[] = [
  { id: 'q1', question: 'Have pedestrian crashes increased in Silver Spring since 2022?', askedAt: 'Just now' },
  { id: 'q2', question: 'Pedestrian crashes in Silver Spring vs. Bethesda', askedAt: '2h ago' },
  { id: 'q3', question: 'Crash hotspots in the county', askedAt: '1d ago' },
  { id: 'q4', question: 'What is the county doing about dangerous roads?', askedAt: '2d ago' },
  { id: 'q5', question: 'Cyclists vs pedestrians in severe crashes', askedAt: '5d ago' },
]

/** Illustrative intersection-level clusters within Silver Spring for the zoomed mini map. */
export const mockSilverSpringFocusHotspots: Hotspot[] = [
  { id: 'ss-1', area: 'Georgia Ave & Colesville Rd', latitude: 38.9968, longitude: -77.0261, crashCount: 62, trend: 14, intensity: 1 },
  { id: 'ss-2', area: 'University Blvd & 16th St', latitude: 38.9903, longitude: -77.0158, crashCount: 41, trend: 9, intensity: 0.7 },
  { id: 'ss-3', area: 'Fenton St & Wayne Ave', latitude: 38.9932, longitude: -77.0301, crashCount: 33, trend: 6, intensity: 0.55 },
  { id: 'ss-4', area: 'East-West Hwy & 16th St', latitude: 38.9861, longitude: -77.021, crashCount: 27, trend: -4, intensity: 0.42 },
  { id: 'ss-5', area: 'Piney Branch Rd & Flower Ave', latitude: 38.9847, longitude: -77.0084, crashCount: 19, trend: 2, intensity: 0.3 },
]

export const mockQueryResponse: QueryResponse = {
  id: 'silver-spring-pedestrian-trend',
  question: 'Have pedestrian crashes increased in Silver Spring since 2022?',
  answer: 'Yes — pedestrian crashes in Silver Spring have gone up since 2022.',
  summary: 'The data shows a clear increase in pedestrian crashes over the past four years.',
  metrics: [
    { label: '2022: Pedestrian crashes', value: 94 },
    { label: '2025: Pedestrian crashes', value: 126 },
    { label: 'Change 2022 → 2025', value: '+34%', change: 34, changeDirection: 'up', changeIsPositive: false, description: 'increase' },
  ],
  crashTrend: [
    { label: '2022', value: 94 },
    { label: '2023', value: 102 },
    { label: '2024', value: 115 },
    { label: '2025', value: 126 },
  ],
  hotspots: mockSilverSpringFocusHotspots,
  whatDataMeans:
    'Pedestrian crashes in Silver Spring have been rising each year, with the biggest jump from 2024 to 2025. More people walking, busier roads, and fast-moving traffic all play a role. We can reverse this trend with safer streets and strong follow-through.',
  countyReportPoints: [
    "We're improving safety at high-crash crossings with better signals, lighting, and shorter crossing distances.",
    'Corridor improvements and speed management are underway on key streets in and around Silver Spring.',
  ],
  visualizations: [
    { id: 'v1', type: 'line', title: 'Pedestrian crashes over time' },
    { id: 'v2', type: 'map', title: 'Where crashes are concentrated' },
  ],
  citations: [
    { id: 'cite-crash-incidents', title: 'Crash incidents dataset', sourceType: 'dataset' },
    { id: 'cite-vz-annual-2025', title: 'Vision Zero Annual Report FY2025', sourceType: 'report' },
    { id: 'cite-vz-action-plan', title: 'Vision Zero Action Plan', sourceType: 'report' },
  ],
  followUpPrompts: ['Show me the worst corridors', 'Are severe crashes also rising?', 'What is the county doing next?'],
  limitations: ['Counts are not rates, and do not account for how many people were walking in each period.'],
  dataAsOf: '2025-12-31',
}
