/**
 * Prototype-only mock data.
 * These values are used to develop the frontend and are not verified
 * Montgomery County crash statistics.
 */
import type { DashboardResponse, HotspotsResponse } from '@/types/analytics'
import { mockHotspots, toRankedAreas } from './crashes'

export const mockDashboard: DashboardResponse = {
  dataAsOf: '2026-06-30',
  metrics: [
    { label: 'Total crashes', value: 8742, change: -6, changeDirection: 'down', changeIsPositive: true, description: 'from last year' },
    { label: 'Pedestrian crashes', value: 935, change: -5, changeDirection: 'down', changeIsPositive: true, description: 'from last year' },
    { label: 'Cyclist crashes', value: 412, change: 8, changeDirection: 'up', changeIsPositive: false, description: 'from last year' },
    { label: 'Serious or fatal crashes', value: 308, change: 4, changeDirection: 'up', changeIsPositive: false, description: 'from last year' },
  ],
  crashTrend: [
    { label: "Jun '23", value: 650 },
    { label: "Aug '23", value: 780 },
    { label: "Oct '23", value: 820 },
    { label: "Dec '23", value: 680 },
    { label: "Feb '24", value: 750 },
    { label: "Apr '24", value: 900 },
    { label: "Jun '24", value: 800 },
  ],
  severityBreakdown: [
    { label: 'Property Damage Only', value: 6021 },
    { label: 'Possible Injury', value: 1986 },
    { label: 'Suspected Serious Injury', value: 427 },
    { label: 'Fatal', value: 308 },
  ],
  roadUserBreakdown: [
    { label: 'Drivers', value: 74.5, color: 'var(--color-accent)' },
    { label: 'Pedestrians', value: 10.7, color: 'var(--color-danger)' },
    { label: 'Cyclists', value: 4.7, color: 'var(--color-chart-cyclist)' },
    { label: 'Passengers', value: 10.1, color: 'var(--color-chart-passenger)' },
  ],
  hotspots: mockHotspots,
  insights: [
    { id: 'i1', text: 'Pedestrian crashes are concentrated along major corridors and in downtown areas.' },
    { id: 'i2', text: 'Cyclist crashes have increased 8% compared to last year.' },
    { id: 'i3', text: 'Serious or fatal crashes make up 3.5% of all crashes but account for most life-changing impacts.' },
  ],
}

export const mockHotspotsResponse: HotspotsResponse = {
  hotspots: mockHotspots,
  rankedAreas: toRankedAreas(mockHotspots),
  summaryCards: [
    { label: 'Most affected area', primaryText: 'Silver Spring', secondaryText: '1,248 crashes · 18% of all county crashes' },
    { label: 'Fastest increase', primaryText: 'Silver Spring', secondaryText: '+12% vs. Jan 2020 – Dec 2021' },
    { label: 'Common crash type', primaryText: 'Rear-end crashes', secondaryText: '36% of all crashes in the county' },
  ],
  countyFocusAreas: [
    'Upgrading crosswalks in high-crash areas',
    'Reducing speeds on major roads with more severe crashes',
    'Improving corridors with the highest crash increases',
  ],
  dataAsOf: 'Jan 2022 – Apr 2024',
}
