import type { Metric, TimeSeriesPoint } from './analytics'
import type { Citation } from './sources'

export interface CorridorStat {
  corridor: string
  crashCount: number
}

export interface SavedInsight {
  id: string
  title: string
  tag: string
  generatedAt: string
  summary: string
  metrics: Metric[]
  crashTrend: TimeSeriesPoint[]
  corridors: CorridorStat[]
  findings: string[]
  followUpPrompts: string[]
  citations: Citation[]
}
