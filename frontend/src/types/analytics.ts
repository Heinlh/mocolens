/** Arithmetic direction of a metric's change, independent of whether that change is good or bad. */
export type TrendDirection = 'up' | 'down' | 'neutral'

export interface Metric {
  label: string
  value: number | string
  /** Signed percentage, e.g. -6 or 8. Omit for metrics with no comparison period. */
  change?: number
  changeDirection?: TrendDirection
  /** True = this change is good for safety (styled positive), false = concerning (styled danger). */
  changeIsPositive?: boolean
  /** Short trailing text, e.g. "from last year". */
  description?: string
}

export interface TimeSeriesPoint {
  label: string
  value: number
}

export interface CategoryValue {
  label: string
  value: number
  /** Optional explicit color (CSS color or var()); charts fall back to a default palette. */
  color?: string
}

/**
 * A geographic crash cluster. latitude/longitude are real-world coordinates
 * (WGS84) - the map components project them onto the stylized illustration,
 * so a future backend can supply true coordinates without a UI change.
 */
export interface Hotspot {
  id: string
  area: string
  latitude: number
  longitude: number
  crashCount: number
  /** Signed percentage change vs. the comparison period. */
  trend: number
  /** 0-1, normalized crash density used to size/color the map marker. */
  intensity: number
}

export interface RankedArea {
  rank: number
  name: string
  crashCount: number
  trend: number
}

export interface Insight {
  id: string
  text: string
}

export interface DashboardFilters {
  timeRange: string
  area: string
  roadUser: string
  severity: string
}

export interface DashboardResponse {
  metrics: Metric[]
  crashTrend: TimeSeriesPoint[]
  severityBreakdown: CategoryValue[]
  roadUserBreakdown: CategoryValue[]
  hotspots: Hotspot[]
  insights: Insight[]
  dataAsOf?: string
}

export interface HotspotSummaryCard {
  label: string
  primaryText: string
  secondaryText: string
}

export interface HotspotsResponse {
  hotspots: Hotspot[]
  rankedAreas: RankedArea[]
  summaryCards: HotspotSummaryCard[]
  countyFocusAreas: string[]
  dataAsOf?: string
}
