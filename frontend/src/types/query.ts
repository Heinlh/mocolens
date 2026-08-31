import type { Hotspot, Metric, TimeSeriesPoint } from './analytics'
import type { Citation } from './sources'
import type { VisualizationSpec } from './visualization'

export interface QueryResponse {
  id: string
  question: string
  /** Short 1-2 sentence direct answer, shown as the main headline. */
  answer: string
  /** Plain-language summary of what the data shows. */
  summary: string
  metrics: Metric[]
  crashTrend: TimeSeriesPoint[]
  hotspots: Hotspot[]
  /** "What the data means" paragraph. */
  whatDataMeans: string
  /** "What county reports say" bullet points. */
  countyReportPoints: string[]
  visualizations: VisualizationSpec[]
  citations: Citation[]
  followUpPrompts: string[]
  limitations?: string[]
  dataAsOf?: string
}

export interface ConversationEntry {
  id: string
  question: string
  askedAt: string
}
